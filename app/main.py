import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from .database import BASE_DIR, connect, init_db, row_to_dict
from .importer import download_page, parse_job_page

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="ApplyKit", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


class TemplateUpdate(BaseModel):
    cv: str = ""
    cover_letter: str = ""


class ApplicationInput(BaseModel):
    company: str = Field(min_length=1, max_length=250)
    job_title: str = Field(min_length=1, max_length=250)
    source_url: str = Field(default="", max_length=2000)
    job_description: str = Field(default="", max_length=100_000)
    adjusted_cv: str = Field(default="", max_length=200_000)
    adjusted_cover_letter: str = Field(default="", max_length=200_000)
    status: str = Field(default="Draft", max_length=50)
    notes: str = Field(default="", max_length=20_000)
    raw_html: str = Field(default="", max_length=5_000_000)
    imported_data: str = Field(default="", max_length=5_000_000)


class ImportInput(BaseModel):
    url: str = ""
    html: str = ""


class SettingsInput(BaseModel):
    lm_studio_url: str = Field(default="http://localhost:1234/v1", max_length=500)
    lm_studio_model: str = Field(default="", max_length=200)


class PersonalDetailsInput(BaseModel):
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=50)
    address_line1: str = Field(default="", max_length=250)
    address_line2: str = Field(default="", max_length=250)
    postal_code: str = Field(default="", max_length=30)
    city: str = Field(default="", max_length=120)
    state_region: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    nationality: str = Field(default="", max_length=120)
    date_of_birth: str = Field(default="", max_length=10)
    linkedin_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=500)
    current_company: str = Field(default="", max_length=250)
    current_job_title: str = Field(default="", max_length=250)
    work_authorization: str = Field(default="", max_length=250)
    notice_period: str = Field(default="", max_length=120)
    salary_expectation: str = Field(default="", max_length=120)
    german_language_level: str = Field(default="", max_length=120)
    english_language_level: str = Field(default="", max_length=120)
    onsite_availability: str = Field(default="", max_length=20)
    travel_willingness: str = Field(default="", max_length=20)

    @field_validator("linkedin_url", "website_url")
    @classmethod
    def validate_optional_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("URLs must start with http:// or https://")
        return value


class GenerateInput(BaseModel):
    application_id: int
    document: str
    instructions: str = ""


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/overview")
def overview():
    with connect() as db:
        counts = {
            row["status"]: row["count"]
            for row in db.execute(
                "SELECT status, COUNT(*) AS count FROM applications GROUP BY status"
            )
        }
        recent = [
            dict(row)
            for row in db.execute(
                """SELECT id, company, job_title, status, created_at, updated_at
                   FROM applications ORDER BY updated_at DESC, id DESC LIMIT 5"""
            )
        ]
        total = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    return {"total": total, "by_status": counts, "recent": recent}


@app.get("/api/templates")
def get_templates():
    with connect() as db:
        rows = db.execute(
            "SELECT kind, filename, content, updated_at FROM document_templates"
        )
        return {row["kind"]: dict(row) for row in rows}


@app.put("/api/templates")
def save_templates(payload: TemplateUpdate):
    with connect() as db:
        for kind, content in (
            ("cv", payload.cv),
            ("cover_letter", payload.cover_letter),
        ):
            db.execute(
                """UPDATE document_templates
                   SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE kind = ?""",
                (content, kind),
            )
    return {"ok": True}


async def _read_latex_file(upload: UploadFile, label: str) -> tuple[str, str]:
    filename = Path(upload.filename or "").name
    if not filename.lower().endswith(".tex"):
        raise HTTPException(400, f"{label} must be a .tex file.")
    raw = await upload.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(400, f"{label} must be smaller than 2 MB.")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, f"{label} must use UTF-8 text encoding.") from exc
    if not content.strip():
        raise HTTPException(400, f"{label} is empty.")
    return filename, content


@app.post("/api/templates/upload")
async def upload_templates(
    cv: UploadFile | None = File(default=None),
    cover_letter: UploadFile | None = File(default=None),
):
    if not cv and not cover_letter:
        raise HTTPException(400, "Select at least one LaTeX file.")

    uploads: list[tuple[str, str, str]] = []
    if cv:
        filename, content = await _read_latex_file(cv, "CV")
        uploads.append(("cv", filename, content))
    if cover_letter:
        filename, content = await _read_latex_file(cover_letter, "Cover letter")
        uploads.append(("cover_letter", filename, content))

    with connect() as db:
        for kind, filename, content in uploads:
            db.execute(
                """UPDATE document_templates
                   SET filename = ?, content = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE kind = ?""",
                (filename, content, kind),
            )
    return get_templates()


@app.get("/api/applications")
def list_applications(search: str = "", status: str = ""):
    where, params = [], []
    if search:
        where.append("(company LIKE ? OR job_title LIKE ? OR job_description LIKE ?)")
        needle = f"%{search}%"
        params.extend([needle, needle, needle])
    if status:
        where.append("status = ?")
        params.append(status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with connect() as db:
        rows = db.execute(
            f"""SELECT id, company, job_title, source_url, status, created_at, updated_at
                FROM applications {clause}
                ORDER BY updated_at DESC, id DESC""",
            params,
        )
        return [dict(row) for row in rows]


@app.get("/api/applications/{application_id}")
def get_application(application_id: int):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Application not found")
    return row_to_dict(row)


@app.post("/api/applications", status_code=201)
def create_application(payload: ApplicationInput):
    fields = tuple(payload.model_dump().keys())
    values = tuple(payload.model_dump().values())
    placeholders = ", ".join("?" for _ in fields)
    with connect() as db:
        cursor = db.execute(
            f"INSERT INTO applications ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        application_id = cursor.lastrowid
    return get_application(application_id)


@app.put("/api/applications/{application_id}")
def update_application(application_id: int, payload: ApplicationInput):
    data = payload.model_dump()
    assignments = ", ".join(f"{field} = ?" for field in data)
    with connect() as db:
        cursor = db.execute(
            f"""UPDATE applications SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            [*data.values(), application_id],
        )
        if not cursor.rowcount:
            raise HTTPException(404, "Application not found")
    return get_application(application_id)


@app.delete("/api/applications/{application_id}", status_code=204)
def delete_application(application_id: int):
    with connect() as db:
        cursor = db.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        if not cursor.rowcount:
            raise HTTPException(404, "Application not found")


@app.post("/api/import")
def import_job(payload: ImportInput):
    if not payload.url and not payload.html:
        raise HTTPException(400, "Provide a URL or pasted HTML.")
    try:
        html = payload.html or download_page(payload.url)
        parsed = parse_job_page(html)
        return {**parsed, "raw_html": html, "source_url": payload.url}
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _settings() -> dict:
    with connect() as db:
        return {
            row["key"]: row["value"]
            for row in db.execute("SELECT key, value FROM settings")
        }


@app.get("/api/settings")
def get_settings():
    settings = _settings()
    return {
        "lm_studio_url": settings.get(
            "lm_studio_url", "http://localhost:1234/v1"
        ),
        "lm_studio_model": settings.get("lm_studio_model", ""),
    }


@app.put("/api/settings")
def save_settings(payload: SettingsInput):
    for key, value in payload.model_dump().items():
        if key == "lm_studio_url" and not value.startswith(("http://", "https://")):
            raise HTTPException(400, "LM Studio URL must start with http:// or https://")
        with connect() as db:
            db.execute(
                """INSERT INTO settings(key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value.rstrip("/") if key == "lm_studio_url" else value),
            )
    return get_settings()


def _personal_details() -> PersonalDetailsInput:
    with connect() as db:
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'personal_details'"
        ).fetchone()
    if not row or not row["value"]:
        return PersonalDetailsInput()
    try:
        return PersonalDetailsInput.model_validate(json.loads(row["value"]))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(500, "Stored personal details are invalid.") from exc


@app.get("/api/personal-details")
def get_personal_details():
    return _personal_details().model_dump()


@app.put("/api/personal-details")
def save_personal_details(payload: PersonalDetailsInput):
    data = payload.model_dump()
    with connect() as db:
        db.execute(
            """INSERT INTO settings(key, value) VALUES ('personal_details', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (json.dumps(data, ensure_ascii=False),),
        )
    return data


@app.get("/api/lm-studio/models")
async def lm_studio_models():
    settings = _settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings['lm_studio_url']}/models")
            response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not connect to LM Studio.") from exc


@app.post("/api/generate")
async def generate_document(payload: GenerateInput):
    if payload.document not in {"cv", "cover_letter"}:
        raise HTTPException(400, "Document must be cv or cover_letter.")
    application = get_application(payload.application_id)
    saved_templates = get_templates()
    source = saved_templates[payload.document]["content"]
    label = "CV" if payload.document == "cv" else "cover letter"
    prompt = f"""Tailor the following {label} for this job application.
Return only the finished document, without commentary or markdown fences.
Preserve all factual details. Do not invent experience, skills, dates, or credentials.

Company: {application['company']}
Role: {application['job_title']}
Job description:
{application['job_description']}

Candidate's source {label}:
{source}

Additional instructions:
{payload.instructions or 'Use a clear, professional tone and emphasize relevant evidence.'}
"""
    settings = _settings()
    model = settings.get("lm_studio_model") or os.getenv("LM_STUDIO_MODEL", "")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            if not model:
                models_response = await client.get(f"{settings['lm_studio_url']}/models")
                models_response.raise_for_status()
                model = models_response.json()["data"][0]["id"]
            request_body = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert job-application editor. Be accurate and concise.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.35,
            }
            response = await client.post(
                f"{settings['lm_studio_url']}/chat/completions", json=request_body
            )
            response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return {"content": content, "model": result.get("model", model)}
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(
            502, "LM Studio did not return a usable response. Check Settings and load a model."
        ) from exc
