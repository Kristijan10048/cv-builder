# ApplyKit Autofill for Firefox

This is a development mockup of a Firefox Manifest V3 extension. It retrieves personal details from ApplyKit running at `http://127.0.0.1:8000` and fills matching empty fields on job-application pages.

It never submits a form and never overwrites a nonempty field.

## Try the extension locally

1. Start ApplyKit:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

2. Open ApplyKit at `http://127.0.0.1:8000`.
3. Open **Settings**, complete **Personal details**, and save the form.
4. In Firefox, open `about:debugging#/runtime/this-firefox`.
5. Select **Load Temporary Add-on**.
6. Select `firefox-extension/manifest.json` from this project.
7. Open a job-application form.
8. Select the ApplyKit toolbar button and choose **Fill empty fields**.

You can also use `Alt+Shift+A` on a page after interacting with the extension.

## Optional automatic filling

The popup contains **Fill automatically on websites**. Enabling it requests access to HTTP and HTTPS pages because Firefox must inject the content script when a page loads. This access is optional; manual filling uses the narrower `activeTab` permission.

Automatic filling can be turned off at any time. The extension still never submits a form or replaces existing values.

## Supported fields

- First and last name
- Full name
- Email and phone
- Address lines, postal code, city, state/region, and country
- LinkedIn and portfolio URLs
- Current company and job title
- Work authorization
- Notice period / availability
- Salary expectation

Matching uses standard HTML `autocomplete` values first, followed by English and German field-name and label patterns. Websites with custom widgets, closed shadow DOM, cross-origin embedded forms, or nonstandard controls may require site-specific adapters.

## Development notes

- Personal details are read from `GET /api/personal-details`.
- The background script performs localhost requests because Manifest V3 content scripts do not receive extension cross-origin privileges.
- The localhost origin is declared explicitly in `host_permissions` and the extension content security policy.
- Persistent site-wide access is requested only when automatic filling is enabled.
- This mockup is not packaged or signed for distribution through Mozilla Add-ons.

Official references:

- [Firefox `scripting` API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/scripting)
- [Firefox `activeTab` permission](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions#activetab_permission)
- [Firefox host permissions](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/host_permissions)
- [Firefox content scripts](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Content_scripts)

