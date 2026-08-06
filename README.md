# ApplyKit

ApplyKit is a local, private workspace for building and tracking tailored job
applications. It uses FastAPI and SQLite, stores reusable source documents, and
can ask a locally running LM Studio model to tailor a CV or cover letter.

## Run

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## LM Studio

Start LM Studio's local server and load a model. In ApplyKit, open **Settings**,
keep the default URL (`http://localhost:1234/v1`) or enter your server URL, then
use **Test connection**. Save an application before generating its tailored
documents.

## Included

- `.tex` upload and storage for the base CV and cover letter
- Job description, status, notes, and tailored document storage
- Personal details stored locally for browser autofill
- Firefox autofill extension mockup in `firefox-extension/`
- Searchable application history
- Local SQLite database at `data/cv_builder.db`
- Versioned SQLite migrations applied automatically at startup
- Public job-page import with stored HTML
- Indeed `window._initialData` extraction when present
- LM Studio's OpenAI-compatible chat completions endpoint

## Firefox autofill mockup

Save your profile under **Settings → Personal details**, then follow the setup
steps in [`firefox-extension/README.md`](firefox-extension/README.md). The
extension fills only empty fields and never submits a form.

## Database migrations

Schema updates are versioned in `app/db_migrations/` and recorded in the
database's `schema_migrations` table. See
[`app/db_migrations/README.md`](app/db_migrations/README.md) before making a
schema change.

Run the automated checks with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```
