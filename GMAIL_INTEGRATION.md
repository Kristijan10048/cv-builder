# ApplyKit Gmail Integration

**Document version:** 1.0  
**Target application version:** 0.2.0  
**Status:** Proposed design  
**Last updated:** 2026-08-06

## 1. Purpose

This document describes how ApplyKit can connect to a user's Gmail account, retrieve email messages, identify likely job opportunities, extract job information, and create reviewable application candidates.

The recommended first version uses the Gmail API with OAuth 2.0 and read-only mailbox access. Gmail messages are never modified or deleted.

## 2. Goals

- Allow the user to connect and disconnect a Gmail account.
- Retrieve recent Gmail messages on demand.
- Search for messages that may contain job offers, recruiter contacts, vacancies, or interview invitations.
- Extract the sender, subject, date, message body, company, role, job description, and relevant job link.
- Prevent the same Gmail message from being imported more than once.
- Let the user review detected opportunities before creating an ApplyKit application.
- Reuse ApplyKit's existing job-page importer for public links found in messages.
- Optionally use the configured LM Studio model for structured job-information extraction.
- Keep credentials, tokens, messages, and extracted information local.

## 3. Non-goals for the first version

- Sending email
- Replying to recruiters
- Deleting, archiving, moving, or marking messages as read
- Adding or removing Gmail labels
- Downloading every mailbox message
- Automatically creating applications without user review
- Automatically opening every link found in an email
- Cloud Pub/Sub push notifications
- Multiple Gmail accounts
- Gmail attachment processing

## 4. Recommended architecture

ApplyKit should use the Gmail REST API through Google's Python client libraries.

The initial integration should use manual synchronization:

1. The user connects Gmail from ApplyKit Settings.
2. Google completes OAuth authorization and returns the user to ApplyKit.
3. The user selects **Sync Gmail**.
4. ApplyKit searches Gmail using a configurable query.
5. ApplyKit retrieves full content only for matching messages it has not processed previously.
6. ApplyKit converts each message into normalized plain text.
7. Rules and, optionally, LM Studio classify and extract job information.
8. Likely opportunities appear in a Gmail candidates review screen.
9. The user accepts or rejects each candidate.
10. Accepted candidates are converted into normal ApplyKit applications.

Manual polling is preferred for the local version because Gmail push notifications require Google Cloud Pub/Sub and additional infrastructure. Google's Gmail API documentation recommends poll-based synchronization for applications running on user-owned devices.

## 5. Google Cloud setup

### 5.1 Create the Google Cloud project

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project named `ApplyKit` or select an existing project.
3. Enable the **Gmail API** for the project.
4. Configure the OAuth consent screen.
5. While the application remains in testing mode, add the Gmail account that will use ApplyKit as a test user.

### 5.2 Create the OAuth client

1. Open **APIs & Services → Credentials**.
2. Create an **OAuth client ID**.
3. Select **Web application** as the application type.
4. Add the following authorized redirect URI:

   ```text
   http://127.0.0.1:8000/api/gmail/callback
   ```

5. Download the OAuth client configuration JSON.
6. Store the file outside source control.

The redirect URI configured in Google Cloud must exactly match the URI used by ApplyKit.

Official reference: [OAuth 2.0 for web-server applications](https://developers.google.com/identity/protocols/oauth2/web-server)

### 5.3 Authorization scope

ApplyKit should request only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

This scope allows ApplyKit to view messages and Gmail settings but does not allow it to modify or delete messages.

Google classifies `gmail.readonly` as a restricted scope. A publicly distributed application can require Google's OAuth verification and, depending on how restricted data is stored or transmitted, an additional security assessment. A personal local installation can initially use an OAuth application in testing mode with the user's account registered as a test user.

Official reference: [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

## 6. Python dependencies

Add the following packages to `requirements.txt`, using versions selected and tested during implementation:

```text
google-api-python-client
google-auth
google-auth-oauthlib
google-auth-httplib2
```

An optional operating-system credential-store implementation may also require:

```text
keyring
```

## 7. Configuration and secret storage

### 7.1 Required configuration

ApplyKit needs:

- Google OAuth client ID
- Google OAuth client secret
- OAuth redirect URI
- Gmail search query
- Gmail synchronization window or last synchronization marker
- Whether LM Studio extraction is enabled

### 7.2 Storage rules

- OAuth client secrets and user tokens must not be committed to Git.
- `.gitignore` must exclude local OAuth configuration and token files.
- OAuth access and refresh tokens should be stored in Windows Credential Manager or another encrypted operating-system credential store.
- If encrypted credential storage is not available in the first prototype, token storage must be clearly documented as local sensitive data and restricted to the current operating-system user.
- ApplyKit must not log OAuth tokens, message bodies, or complete Gmail API responses.
- Disconnecting Gmail must remove locally stored OAuth tokens.

## 8. Gmail search and synchronization

### 8.1 Initial search

The Gmail API's `users.messages.list` method supports the same search syntax as the Gmail search box. A configurable initial query could be:

```text
newer_than:30d (job OR vacancy OR recruiter OR interview OR application) -in:spam -in:trash
```

The user should be allowed to adjust this query in Settings.

Additional searches may target known recruiting services or sender domains. Search results should be treated as possible candidates, not confirmed job offers.

The list operation returns message IDs and thread IDs. ApplyKit must call `users.messages.get` for the complete content of each new matching message.

Official reference: [List Gmail messages](https://developers.google.com/workspace/gmail/api/guides/list-messages)

### 8.2 Incremental synchronization

The first implementation may combine:

- A configurable recent-message query
- A locally stored last-synchronization timestamp
- Deduplication by Gmail message ID

A more reliable later implementation should store Gmail's `historyId` and use `users.history.list` for incremental mailbox synchronization.

### 8.3 Synchronization behavior

- Synchronization must be initiated explicitly by the user in the first release.
- A later release may offer periodic synchronization while ApplyKit is running.
- A synchronization operation must expose an in-progress state.
- Repeated clicks must not start overlapping synchronization jobs.
- Pagination must be supported when Gmail returns a `nextPageToken`.
- The user must be able to cancel or safely retry after an error.
- Partial progress should be retained when one message fails.
- Gmail rate-limit responses should cause bounded retry with exponential backoff.
- A failure must produce a readable error without disconnecting the account unnecessarily.

## 9. Message retrieval and normalization

For each unprocessed message, ApplyKit should request the message using `format=full` and perform the following steps:

1. Store the Gmail message ID and thread ID.
2. Read selected headers:
   - `From`
   - `To`
   - `Subject`
   - `Date`
   - `Message-ID`
3. Recursively inspect MIME parts.
4. Prefer a `text/plain` part when it contains meaningful content.
5. Otherwise, convert a `text/html` part to sanitized plain text.
6. Decode Gmail body data using Base64URL decoding.
7. Normalize whitespace without destroying useful job-description structure.
8. Extract HTTP and HTTPS links.
9. Exclude tracking, unsubscribe, image, preference, and authentication links where possible.
10. Retain only the minimum message data required for review and application creation.

Remote images embedded in HTML email must not be loaded during parsing or display.

## 10. Job-opportunity detection

Detection should use two stages.

### 10.1 Deterministic classification

ApplyKit should first score each message using transparent signals such as:

- Known recruiting sender or domain
- Job-related words in the subject
- Phrases such as `job opportunity`, `position`, `vacancy`, `interview`, `recruiter`, or `application`
- The presence of a likely job-page URL
- Company and role patterns in the subject or body
- Negative signals such as newsletters, generic marketing, invoices, or unrelated account notifications

Messages below a configurable threshold may be ignored or shown in a low-confidence section.

### 10.2 Optional LM Studio extraction

If enabled, ApplyKit may send normalized email text to the locally configured LM Studio model. The model must return a strict JSON object such as:

```json
{
  "is_job_opportunity": true,
  "opportunity_type": "job_offer",
  "company": "Example GmbH",
  "job_title": "Python Developer",
  "job_description": "Design and maintain backend services...",
  "source_url": "https://example.com/jobs/123",
  "confidence": 0.91
}
```

Recommended `opportunity_type` values are:

- `job_offer`
- `recruiter_outreach`
- `job_alert`
- `application_update`
- `interview_invitation`
- `rejection`
- `unrelated`

The model prompt must state that email contents are untrusted data. Instructions found inside an email must never override the extraction task. The result must be schema-validated before storage.

## 11. Job-link processing

When an email contains a likely public job link:

1. Display the link to the user as part of the candidate.
2. Do not open or download it automatically during initial Gmail synchronization.
3. When the user requests job-page import, pass the URL through ApplyKit's existing public-URL validation.
4. Reuse `download_page` and `parse_job_page` from the existing importer.
5. Compare the page extraction with information extracted from the email.
6. Prefer the most complete trustworthy description while allowing the user to edit it.

This preserves the existing protections against credential-bearing URLs, local/private addresses, non-HTML responses, oversized pages, and request timeouts.

## 12. Proposed database changes

### 12.1 Gmail connection state

Sensitive tokens should remain outside SQLite. Non-secret synchronization state may use a table similar to:

```sql
CREATE TABLE gmail_sync_state (
    account_email TEXT PRIMARY KEY,
    last_history_id TEXT NOT NULL DEFAULT '',
    last_synced_at TEXT NOT NULL DEFAULT '',
    search_query TEXT NOT NULL DEFAULT '',
    extraction_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 12.2 Gmail candidates

```sql
CREATE TABLE gmail_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL UNIQUE,
    gmail_thread_id TEXT NOT NULL DEFAULT '',
    message_id_header TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    opportunity_type TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    job_title TEXT NOT NULL DEFAULT '',
    job_description TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'new',
    application_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(application_id) REFERENCES applications(id)
);
```

Recommended candidate states:

- `new`
- `reviewed`
- `accepted`
- `rejected`
- `duplicate`

The unique `gmail_message_id` constraint prevents the same Gmail message from being processed more than once.

## 13. Proposed API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/gmail/status` | Return connection and last-sync status without exposing tokens |
| `GET` | `/api/gmail/connect` | Start OAuth authorization |
| `GET` | `/api/gmail/callback` | Validate OAuth state and complete authorization |
| `DELETE` | `/api/gmail/disconnect` | Revoke or remove local authorization data |
| `POST` | `/api/gmail/sync` | Search and process new matching Gmail messages |
| `GET` | `/api/gmail/candidates` | List candidates with state and confidence filters |
| `GET` | `/api/gmail/candidates/{id}` | Return one normalized candidate |
| `PUT` | `/api/gmail/candidates/{id}` | Correct extracted candidate fields or change state |
| `POST` | `/api/gmail/candidates/{id}/refresh-link` | Import a selected public job page and refresh extracted fields |
| `POST` | `/api/gmail/candidates/{id}/create-application` | Create an ApplyKit application from an accepted candidate |
| `DELETE` | `/api/gmail/candidates/{id}` | Remove locally stored candidate data |

The OAuth callback should return the user to the Gmail Settings or candidates view rather than expose token data in its response.

## 14. User-interface changes

### 14.1 Settings

Add a **Gmail integration** section containing:

- Connection status
- Connected account address
- **Connect Gmail** button
- **Disconnect Gmail** button
- Search-query field
- Recent-message window setting
- Toggle for LM Studio extraction
- Last successful synchronization time
- **Sync Gmail now** button

### 14.2 Navigation

Add a **Gmail candidates** or **Opportunities** view under the Workspace section.

### 14.3 Candidate review

Each candidate should display:

- Sender
- Subject
- Received date
- Detected opportunity type
- Company
- Role
- Confidence indicator
- Extracted job description
- Source job link
- Link to open the original message in Gmail when available
- **Create application** action
- **Reject** action

The user must be able to edit the extracted company, role, description, and URL before creating an application.

## 15. Security and privacy requirements

- **GMAIL-SEC-001:** ApplyKit shall request only `gmail.readonly` for the initial integration.
- **GMAIL-SEC-002:** OAuth authorization shall use and validate a cryptographically random `state` value.
- **GMAIL-SEC-003:** OAuth tokens shall never be included in URLs, browser storage, logs, API responses, or Git-tracked files.
- **GMAIL-SEC-004:** Email HTML shall be sanitized and converted to safe text before display.
- **GMAIL-SEC-005:** Remote email images and active content shall not be loaded.
- **GMAIL-SEC-006:** Email contents shall be treated as untrusted input and possible prompt-injection content.
- **GMAIL-SEC-007:** Links shall not be fetched until explicitly selected by the user and validated by the existing public-URL guard.
- **GMAIL-SEC-008:** The integration shall not execute email attachments, scripts, commands, or instructions.
- **GMAIL-SEC-009:** Disconnecting Gmail shall remove local authorization tokens and connection metadata.
- **GMAIL-SEC-010:** The application shall clearly disclose what mailbox data is read and what information is stored locally.
- **GMAIL-SEC-011:** The application shall allow locally stored candidate data to be deleted independently of the Gmail message.
- **GMAIL-SEC-012:** Gmail API errors shall be sanitized before being shown in the browser.

## 16. Functional requirements

- **GMAIL-FR-001:** The user shall be able to connect one Gmail account using OAuth 2.0.
- **GMAIL-FR-002:** The user shall be able to disconnect the Gmail account.
- **GMAIL-FR-003:** ApplyKit shall display whether Gmail is connected without exposing credentials.
- **GMAIL-FR-004:** The user shall be able to configure the Gmail search query.
- **GMAIL-FR-005:** The user shall be able to start synchronization manually.
- **GMAIL-FR-006:** ApplyKit shall retrieve every page of message IDs returned for the configured search within its configured limits.
- **GMAIL-FR-007:** ApplyKit shall skip Gmail message IDs already present in `gmail_candidates`.
- **GMAIL-FR-008:** ApplyKit shall retrieve and normalize the full body of each new matching message.
- **GMAIL-FR-009:** ApplyKit shall classify messages and extract available job information.
- **GMAIL-FR-010:** ApplyKit shall store likely opportunities as review candidates.
- **GMAIL-FR-011:** ApplyKit shall not automatically create an application from an email.
- **GMAIL-FR-012:** The user shall be able to correct extracted candidate information.
- **GMAIL-FR-013:** The user shall be able to accept, reject, or delete a candidate.
- **GMAIL-FR-014:** Accepting a candidate shall create an ApplyKit application and link it to the candidate.
- **GMAIL-FR-015:** A candidate's company, role, description, and source URL shall populate the corresponding application fields.
- **GMAIL-FR-016:** ApplyKit shall display synchronization progress and a final processed/new/skipped/error summary.
- **GMAIL-FR-017:** A failure processing one message shall not discard other successfully processed messages.
- **GMAIL-FR-018:** ApplyKit shall record the last successful synchronization time.
- **GMAIL-FR-019:** The user shall be able to open the original Gmail message through a Gmail web link when sufficient identifiers are available.
- **GMAIL-FR-020:** The user shall be able to request import of a selected public job link through the existing job-page importer.

## 17. Acceptance criteria

### GMAIL-AC-01: Connect Gmail

**Given** a valid Google OAuth client configuration,  
**when** the user selects **Connect Gmail** and grants read-only access,  
**then** Google returns the user to ApplyKit, ApplyKit stores the authorization securely, and Settings displays the connected account without exposing tokens.

### GMAIL-AC-02: Cancelled or invalid authorization

**Given** an OAuth request,  
**when** the user cancels or the returned state is invalid,  
**then** ApplyKit rejects the callback, stores no credentials, and displays a readable error.

### GMAIL-AC-03: Synchronize messages

**Given** a connected Gmail account and configured search query,  
**when** the user selects **Sync Gmail now**,  
**then** ApplyKit retrieves matching message IDs, fetches new messages, normalizes their content, and displays a synchronization summary.

### GMAIL-AC-04: Prevent duplicates

**Given** a Gmail message that was processed previously,  
**when** a later synchronization returns the same message ID,  
**then** ApplyKit skips it and does not create a duplicate candidate.

### GMAIL-AC-05: Detect a job opportunity

**Given** a message containing recognizable company, role, and job-description information,  
**when** ApplyKit processes it,  
**then** it creates a review candidate containing the available extracted fields, source message metadata, and confidence value.

### GMAIL-AC-06: Human review

**Given** a detected candidate,  
**when** the user edits and accepts it,  
**then** ApplyKit creates a standard application using the reviewed values and links the candidate to the new application.

### GMAIL-AC-07: Reject a candidate

**Given** an irrelevant or unwanted candidate,  
**when** the user rejects it,  
**then** its state changes to `rejected`, no application is created, and future synchronization does not re-create it.

### GMAIL-AC-08: Job link

**Given** a candidate containing a public job-page URL,  
**when** the user explicitly requests page import,  
**then** ApplyKit validates the URL using its existing public-address restrictions and imports the page only if validation succeeds.

### GMAIL-AC-09: Disconnect

**Given** a connected Gmail account,  
**when** the user confirms **Disconnect Gmail**,  
**then** ApplyKit removes its local tokens, stops future synchronization, and retains or deletes previously extracted candidates according to the user's selected option.

## 18. Implementation phases

### Phase 1: OAuth foundation

- Add Google client dependencies.
- Add secure configuration loading.
- Implement connect, callback, status, and disconnect endpoints.
- Add the Gmail Settings interface.
- Verify read-only authorization with a test account.

### Phase 2: Manual synchronization

- Implement Gmail search and pagination.
- Retrieve full messages.
- Normalize plain-text and HTML bodies.
- Add database migration and deduplication.
- Display synchronization status and errors.

### Phase 3: Candidate detection and review

- Implement deterministic scoring.
- Add candidate list and editor.
- Add accept, reject, delete, and create-application operations.
- Reuse the existing job-page importer for user-selected links.

### Phase 4: Optional LM Studio extraction

- Add strict extraction schema and prompt.
- Validate model output.
- Add prompt-injection safeguards.
- Display extraction confidence and source information.

### Phase 5: Reliability improvements

- Add incremental synchronization using Gmail history IDs.
- Add bounded retry and rate-limit handling.
- Add optional periodic polling while ApplyKit is running.
- Add credential-store integration and token revocation.

Push notifications should be considered only if ApplyKit later runs with suitable Google Cloud Pub/Sub infrastructure and a secure reachable endpoint. Gmail mailbox watches must be renewed at least every seven days; Google recommends renewing them daily.

Official reference: [Configure Gmail API push notifications](https://developers.google.com/workspace/gmail/api/guides/push)

## 19. Test plan

The integration should include automated tests for:

- OAuth callback success, cancellation, state mismatch, and missing configuration
- Token refresh and expired/revoked authorization
- Gmail search pagination
- Empty search results
- Duplicate message IDs
- Plain-text messages
- HTML-only messages
- Nested multipart MIME messages
- Invalid Base64URL data
- Messages with no useful body
- Rule-based job classification
- Strict LM Studio JSON validation
- Prompt-injection text inside an email
- Valid and blocked job-page links
- Gmail API timeouts, rate limits, and upstream errors
- Candidate editing, rejection, deletion, and application creation
- Disconnect behavior and removal of locally stored tokens

Integration tests should mock the Gmail API. Manual verification should use a dedicated test Gmail account rather than a primary mailbox.

## 20. Official references

- [Gmail API overview](https://developers.google.com/workspace/gmail/api/guides)
- [List Gmail messages](https://developers.google.com/workspace/gmail/api/guides/list-messages)
- [Gmail messages.list reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [OAuth 2.0 for web-server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Configure Gmail API push notifications](https://developers.google.com/workspace/gmail/api/guides/push)

