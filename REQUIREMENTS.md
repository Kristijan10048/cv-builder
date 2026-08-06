# ApplyKit Software Requirements Specification

**Document version:** 1.0  
**Application version:** 0.1.0  
**Status:** As-built baseline  
**Last updated:** 2026-08-06

## 1. Purpose

ApplyKit is a local, private workspace for preparing and tracking tailored job applications. It stores reusable source documents, job details, application status, notes, and tailored documents in a local SQLite database. It can import public job pages and use an LM Studio model to draft a tailored CV or cover letter.

This document defines the requirements represented by the current application. It is intended to guide development, testing, maintenance, and future changes.

## 2. Product scope

### 2.1 In scope

- Local, single-user web application
- Dashboard and application pipeline overview
- Creation, viewing, editing, searching, filtering, and deletion of applications
- Storage of a base CV and base cover letter as LaTeX source
- Import of job information from a public URL or supplied HTML
- Generation of tailored documents through LM Studio's OpenAI-compatible API
- Local persistence in SQLite
- Responsive desktop and mobile browser interface

### 2.2 Out of scope for version 0.1.0

- User accounts, authentication, and multi-user access
- Cloud synchronization or remote application hosting
- Automatic submission of job applications
- Email or calendar integration
- PDF or DOCX generation
- LaTeX compilation and preview
- File attachments other than the two base `.tex` documents
- Application reminders, analytics, or workflow automation
- Backup, restore, and database encryption

## 3. Users and operating assumptions

### 3.1 Primary user

The primary user is a job applicant who wants to organize job opportunities and prepare truthful, role-specific application documents on their own computer.

### 3.2 Assumptions

- The application runs on a trusted local computer.
- One person uses a given database at a time.
- Python and the dependencies in `requirements.txt` are installed in a virtual environment.
- JavaScript is enabled in the browser.
- Internet access is available when importing a public job page or loading remote web fonts.
- LM Studio is installed, running, and has a model loaded when AI drafting is used.
- The user is responsible for reviewing generated content before using it.

## 4. Functional requirements

### 4.1 Application startup and navigation

- **FR-001:** The system shall initialize its database schema when the FastAPI application starts.
- **FR-002:** The system shall serve the main user interface at `/`.
- **FR-003:** The interface shall provide views for Overview, New application/Application builder, Applications, Base documents, and Settings.
- **FR-004:** The interface shall support navigation without a full browser-page reload.
- **FR-005:** The interface shall provide a collapsible navigation menu on narrow screens.

### 4.2 Overview dashboard

- **FR-010:** The system shall display the total number of saved applications.
- **FR-011:** The system shall display the number of applications with the `Draft` status.
- **FR-012:** The system shall display the active pipeline count as the sum of applications with `Ready`, `Applied`, `Interview`, or `Offer` status.
- **FR-013:** The system shall display up to five recently updated applications, ordered by update time and then ID in descending order.
- **FR-014:** Selecting a recent application shall open it in the Application builder.

### 4.3 Application management

- **FR-020:** The user shall be able to create an application with a company and job title.
- **FR-021:** The company and job title shall each contain between 1 and 250 characters.
- **FR-022:** An application shall support the following data: company, job title, source URL, job description, tailored CV, tailored cover letter, status, notes, raw imported HTML, and extracted imported data.
- **FR-023:** A new application's default status shall be `Draft`.
- **FR-024:** The interface shall offer the statuses `Draft`, `Ready`, `Applied`, `Interview`, `Offer`, and `Closed`.
- **FR-025:** The user shall be able to open and edit an existing application.
- **FR-026:** Saving an existing application shall update its `updated_at` timestamp.
- **FR-027:** The user shall be able to delete an existing application after confirming the destructive action.
- **FR-028:** A request for a nonexistent application shall return an HTTP 404 response.
- **FR-029:** Application lists shall be ordered by update time and then ID in descending order.

### 4.4 Application search and filtering

- **FR-030:** The user shall be able to search applications by company, job title, or job description.
- **FR-031:** Text search shall support partial matches.
- **FR-032:** The user shall be able to filter applications by exact status.
- **FR-033:** Search and status filters shall be usable together.
- **FR-034:** The interface shall display an empty state when no applications match.

### 4.5 Base documents

- **FR-040:** The system shall maintain one base CV and one base cover-letter template.
- **FR-041:** The user shall be able to upload the CV, the cover letter, or both in one request.
- **FR-042:** Each uploaded document shall use a `.tex` filename extension.
- **FR-043:** Each uploaded document shall be valid UTF-8 text, shall not be empty, and shall not exceed 2 MB.
- **FR-044:** The system shall store the sanitized filename, complete source content, and update timestamp for each document.
- **FR-045:** Uploading a document of the same kind shall replace the previously stored filename and content.
- **FR-046:** The interface shall display the filename of the currently stored document.
- **FR-047:** The API shall allow the text contents of both templates to be retrieved and updated.

### 4.6 Job-page import

- **FR-050:** The import service shall accept either a public job-page URL or supplied HTML.
- **FR-051:** When both URL and HTML are absent, the service shall return HTTP 400.
- **FR-052:** URL import shall accept only HTTP and HTTPS URLs with a hostname and without embedded credentials.
- **FR-053:** URL import shall reject hosts resolving to private, loopback, link-local, reserved, or otherwise non-global IP addresses.
- **FR-054:** URL downloads shall follow redirects, use a 15-second timeout, and identify the client with an ApplyKit user agent.
- **FR-055:** A downloaded resource shall be HTML and shall not exceed 5 MB.
- **FR-056:** The parser shall attempt to extract the job title from Open Graph metadata, Twitter metadata, or the HTML title.
- **FR-057:** The parser shall attempt to extract the company from `og:site_name` metadata.
- **FR-058:** The parser shall attempt to extract the job description from metadata and known job-description containers, preferring the longer available value.
- **FR-059:** The parser shall remove script, style, `noscript`, and SVG elements before extracting visible description text.
- **FR-060:** The parser shall extract and preserve valid Indeed `window._initialData` JSON when present.
- **FR-061:** The import result shall include the source URL, raw HTML, extracted fields, and serialized imported data.
- **FR-062:** Imported company and job-title values shall not overwrite nonempty values already entered in the interface.
- **FR-063:** An imported job description may replace the description currently shown in the editor.

### 4.7 LM Studio configuration

- **FR-070:** The system shall store an LM Studio server URL and optional model identifier.
- **FR-071:** The default LM Studio server URL shall be `http://localhost:1234/v1`.
- **FR-072:** The LM Studio URL shall begin with `http://` or `https://` and shall be stored without trailing slashes.
- **FR-073:** The user shall be able to test the connection by requesting the server's `/models` endpoint.
- **FR-074:** The connection test shall use a 5-second timeout and report either the number of models returned or an understandable connection error.

### 4.8 AI-assisted document drafting

- **FR-080:** AI drafting shall be available for a tailored CV and a tailored cover letter.
- **FR-081:** An application shall be saved before AI drafting can start.
- **FR-082:** The generation request shall use the selected application, the corresponding base document, and optional user instructions.
- **FR-083:** If no model is configured, the system shall use the first model returned by LM Studio's `/models` endpoint.
- **FR-084:** The `LM_STUDIO_MODEL` environment variable may provide a model when no model is saved in Settings.
- **FR-085:** The system shall call LM Studio's `/chat/completions` endpoint with a maximum wait of 120 seconds and a temperature of `0.35`.
- **FR-086:** The generation prompt shall instruct the model to return only the finished document, preserve factual details, and not invent experience, skills, dates, or credentials.
- **FR-087:** The generated content shall be placed in the appropriate editor but shall not be persisted until the user saves the application.
- **FR-088:** A successful generation response shall include the generated content and the model identifier.
- **FR-089:** Connection failures or unusable model responses shall return HTTP 502 with a user-readable message.

## 5. Data requirements

### 5.1 Storage

- **DR-001:** Persistent data shall be stored in `data/cv_builder.db` using SQLite.
- **DR-002:** The data directory shall be created automatically when required.
- **DR-003:** SQLite foreign-key checking shall be enabled for each connection.
- **DR-004:** Database initialization shall be idempotent and preserve existing records.

### 5.2 Data entities

#### Document template

| Field | Type | Rules |
|---|---|---|
| `kind` | Text, primary key | `cv` or `cover_letter` |
| `filename` | Text | Defaults to empty text |
| `content` | Text | Required; defaults to empty text |
| `updated_at` | Text timestamp | Required; defaults to current timestamp |

#### Application

| Field | Type | Rules |
|---|---|---|
| `id` | Integer, primary key | Auto-incremented |
| `company` | Text | Required; 1-250 characters through the API |
| `job_title` | Text | Required; 1-250 characters through the API |
| `source_url` | Text | Maximum 2,000 characters |
| `job_description` | Text | Maximum 100,000 characters |
| `adjusted_cv` | Text | Maximum 200,000 characters |
| `adjusted_cover_letter` | Text | Maximum 200,000 characters |
| `status` | Text | Defaults to `Draft`; maximum 50 characters |
| `notes` | Text | Maximum 20,000 characters |
| `raw_html` | Text | Maximum 5,000,000 characters |
| `imported_data` | Text | Maximum 5,000,000 characters |
| `created_at` | Text timestamp | Required; defaults to current timestamp |
| `updated_at` | Text timestamp | Required; defaults to current timestamp |

#### Setting

| Field | Type | Rules |
|---|---|---|
| `key` | Text, primary key | Setting identifier |
| `value` | Text | Required |

The initial setting keys are `lm_studio_url` and `lm_studio_model`.

## 6. API requirements

| Method | Path | Purpose | Success response |
|---|---|---|---|
| `GET` | `/` | Render the application interface | `200` HTML |
| `GET` | `/api/overview` | Return dashboard counts and recent items | `200` JSON |
| `GET` | `/api/templates` | Return both base documents | `200` JSON |
| `PUT` | `/api/templates` | Replace base-document text | `200` JSON |
| `POST` | `/api/templates/upload` | Upload one or both `.tex` documents | `200` JSON |
| `GET` | `/api/applications` | List, search, and filter applications | `200` JSON array |
| `GET` | `/api/applications/{id}` | Return one application | `200` JSON |
| `POST` | `/api/applications` | Create an application | `201` JSON |
| `PUT` | `/api/applications/{id}` | Replace an application's editable data | `200` JSON |
| `DELETE` | `/api/applications/{id}` | Delete an application | `204` empty body |
| `POST` | `/api/import` | Download or parse a job page | `200` JSON |
| `GET` | `/api/settings` | Return LM Studio settings | `200` JSON |
| `PUT` | `/api/settings` | Save LM Studio settings | `200` JSON |
| `GET` | `/api/lm-studio/models` | Proxy LM Studio's model list | `200` JSON or `502` |
| `POST` | `/api/generate` | Generate a tailored document | `200` JSON or `502` |

FastAPI's default validation response (`422`) applies when a request body or parameter does not satisfy its declared schema. Expected user or resource errors use `400` or `404`; upstream LM Studio failures use `502`.

## 7. Non-functional requirements

### 7.1 Privacy and security

- **NFR-001:** Application records, settings, uploaded source text, and generated documents shall remain in the local SQLite database unless the user explicitly invokes a network-backed feature.
- **NFR-002:** AI prompts and source documents shall be sent only to the LM Studio URL configured by the user.
- **NFR-003:** Remote job-page import shall mitigate server-side request forgery by rejecting non-public resolved IP addresses and credential-bearing URLs.
- **NFR-004:** Uploaded filenames shall be reduced to their final path component before storage.
- **NFR-005:** User-derived values inserted into dynamic HTML by the interface shall be HTML-escaped.
- **NFR-006:** Version 0.1.0 assumes trusted local access and does not provide authentication or authorization.

### 7.2 Usability and accessibility

- **NFR-010:** The interface shall be usable on desktop and mobile viewport sizes.
- **NFR-011:** Application rows shall be operable by pointer and by the Enter or Space key.
- **NFR-012:** Form controls shall have visible labels or accessible labels.
- **NFR-013:** Success and error messages shall be shown as transient status notifications and exposed through an ARIA live region.
- **NFR-014:** Empty application lists shall display an explanatory empty state.
- **NFR-015:** Long-running import, upload, connection-test, and generation operations shall expose an in-progress state and prevent duplicate activation where implemented.

### 7.3 Reliability and maintainability

- **NFR-020:** The application shall preserve existing database data across restarts and idempotent schema initialization.
- **NFR-021:** Database operations shall use parameterized values for user-supplied data.
- **NFR-022:** The application shall present user-readable errors for import, validation, and LM Studio failures.
- **NFR-023:** Core create/list/delete, HTML import, and upload-validation workflows shall be covered by automated tests.
- **NFR-024:** Runtime package versions shall be declared in `requirements.txt`.

### 7.4 Performance

- **NFR-030:** Search input shall be debounced by approximately 250 milliseconds in the interface.
- **NFR-031:** The dashboard shall return no more than five recent application records.
- **NFR-032:** Job-page downloads shall time out after 15 seconds.
- **NFR-033:** LM Studio model-list requests shall time out after 5 seconds.
- **NFR-034:** LM Studio generation requests shall time out after 120 seconds.

## 8. Validation limits

| Input | Limit |
|---|---:|
| Company | 1-250 characters |
| Job title | 1-250 characters |
| Source URL | 2,000 characters |
| Job description | 100,000 characters |
| Tailored CV | 200,000 characters |
| Tailored cover letter | 200,000 characters |
| Status | 50 characters |
| Notes | 20,000 characters |
| Stored raw HTML | 5,000,000 characters |
| Stored imported data | 5,000,000 characters |
| LM Studio URL | 500 characters |
| LM Studio model identifier | 200 characters |
| Uploaded `.tex` document | Less than or equal to 2,000,000 bytes |
| Downloaded job page | Less than or equal to 5,000,000 bytes |

## 9. Acceptance criteria

### AC-01: First startup

**Given** no database exists,  
**when** ApplyKit starts,  
**then** it creates the database, initializes both document-template records and default LM Studio settings, and serves the Overview page.

### AC-02: Base-document upload

**Given** valid, nonempty UTF-8 `.tex` files no larger than 2 MB,  
**when** the user uploads a CV and/or cover letter,  
**then** the system stores the filename and content and displays the current filename.

Invalid extension, encoding, size, or empty content shall produce HTTP 400 without replacing the stored document.

### AC-03: Application lifecycle

**Given** a company and job title,  
**when** the user saves a new application,  
**then** the system returns HTTP 201 and the application appears in the Overview and Applications views.

**When** the user edits and saves it,  
**then** all editable fields and the update timestamp are refreshed.

**When** the user confirms deletion,  
**then** the application is removed and subsequent retrieval returns HTTP 404.

### AC-04: Search and status filtering

**Given** multiple saved applications,  
**when** the user enters partial company, role, or description text and/or selects a status,  
**then** only matching applications are displayed in most-recently-updated order.

### AC-05: HTML import

**Given** supplied HTML containing a page title and a job description in a supported container,  
**when** the user imports it,  
**then** the service returns the extracted title and description together with the raw HTML.

### AC-06: Public URL safeguards

**Given** a malformed URL, credential-bearing URL, non-HTTP(S) URL, local/private address, non-HTML response, oversized page, or failed download,  
**when** import is requested,  
**then** the service rejects the request with HTTP 400 and a readable reason.

### AC-07: LM Studio connection

**Given** a valid LM Studio server URL,  
**when** the user tests the connection,  
**then** the interface reports the number of available models.

If the server is unavailable or returns an error, the interface shall show a connection error.

### AC-08: AI drafting

**Given** a saved application, an uploaded source document, and an available LM Studio model,  
**when** the user requests a CV or cover-letter draft,  
**then** the system sends the role, job description, source document, and optional instructions to LM Studio and places the returned content in the correct editor.

The user must save the application to persist the generated content.

### AC-09: Responsive interface

**Given** a viewport width of 900 pixels or less,  
**when** the interface is displayed,  
**then** the fixed sidebar is replaced by an overlay navigation menu and the editor uses a single-column layout.

**Given** a viewport width of 650 pixels or less,  
**then** metrics, template cards, form field rows, filters, and generation controls stack vertically where defined.

## 10. Known constraints and implementation gaps

- The API accepts any status text up to 50 characters even though the interface exposes six predefined statuses.
- URL safety is checked before the initial request; redirect destinations rely on the HTTP client's redirect handling and are not independently validated by application code.
- The application has no authentication and should not be exposed directly to an untrusted network.
- SQLite timestamps are stored as text using SQLite's current timestamp behavior.
- AI output is probabilistic and may still contain inaccuracies despite the prompt; human review is required.
- Base documents and generated documents are stored as text only; the application does not compile or validate LaTeX syntax.
- The UI uses Google Fonts, which causes an external request when the main page loads unless the fonts are already cached or blocked.

## 11. Verification approach

Requirements should be verified through a combination of:

- Automated API tests using FastAPI's `TestClient`
- Unit tests for URL validation and HTML parsing
- Mocked integration tests for LM Studio success, timeout, malformed response, and upstream error cases
- Database migration and persistence tests
- Manual responsive-layout checks at desktop, 900-pixel, and 650-pixel breakpoints
- Keyboard and screen-reader-oriented accessibility checks
- Security tests covering private addresses, credential-bearing URLs, redirects, oversized content, and malicious filenames

