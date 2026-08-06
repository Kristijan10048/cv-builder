import sqlite3

from fastapi.testclient import TestClient

from app.database import connect
from app.db_migrations import run_migrations
from app.main import app


def test_core_workflow():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        uploaded = client.post(
            "/api/templates/upload",
            files={
                "cv": ("candidate_cv.tex", b"\\documentclass{article}", "text/x-tex"),
                "cover_letter": (
                    "cover_letter.tex",
                    b"\\documentclass{letter}",
                    "text/x-tex",
                ),
            },
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["cv"]["filename"] == "candidate_cv.tex"

        created = client.post(
            "/api/applications",
            json={
                "company": "Northstar Labs",
                "job_title": "Software Engineer",
                "job_description": "Build reliable APIs",
                "status": "Draft",
            },
        )
        assert created.status_code == 201
        application_id = created.json()["id"]

        listed = client.get("/api/applications?search=Northstar")
        assert listed.status_code == 200
        assert any(item["id"] == application_id for item in listed.json())

        overview = client.get("/api/overview").json()
        assert overview["total"] >= 1

        assert client.delete(f"/api/applications/{application_id}").status_code == 204


def test_html_import():
    html = """
    <html><head>
      <title>Backend Engineer</title>
      <meta property="og:site_name" content="Example Co">
    </head><body><main>Design and maintain Python services.</main></body></html>
    """
    with TestClient(app) as client:
        result = client.post("/api/import", json={"html": html})
        assert result.status_code == 200
        assert result.json()["job_title"] == "Backend Engineer"
        assert "Python services" in result.json()["job_description"]


def test_template_upload_rejects_non_latex():
    with TestClient(app) as client:
        result = client.post(
            "/api/templates/upload",
            files={"cv": ("candidate.txt", b"plain text", "text/plain")},
        )
        assert result.status_code == 400


def test_migrations_upgrade_legacy_database_and_are_repeatable():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE document_templates (
               kind TEXT PRIMARY KEY,
               content TEXT NOT NULL DEFAULT '',
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute(
        "INSERT INTO settings(key, value) VALUES ('lm_studio_model', 'keep-me')"
    )

    run_migrations(db)
    run_migrations(db)

    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(document_templates)")
    }
    assert "filename" in columns
    assert db.execute(
        "SELECT value FROM settings WHERE key = 'lm_studio_model'"
    ).fetchone()[0] == "keep-me"
    assert db.execute(
        "SELECT value FROM settings WHERE key = 'personal_details'"
    ).fetchone()[0] == "{}"
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
    db.close()


def test_personal_details_are_stored_in_settings():
    with TestClient(app) as client:
        original = client.get("/api/personal-details").json()
        payload = {
            **original,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.test",
            "city": "London",
            "website_url": "https://example.test",
        }
        try:
            saved = client.put("/api/personal-details", json=payload)
            assert saved.status_code == 200
            assert saved.json()["first_name"] == "Ada"
            assert client.get("/api/personal-details").json()["city"] == "London"
            with connect() as db:
                stored = db.execute(
                    "SELECT value FROM settings WHERE key = 'personal_details'"
                ).fetchone()[0]
            assert '"first_name": "Ada"' in stored
        finally:
            client.put("/api/personal-details", json=original)


if __name__ == "__main__":
    test_core_workflow()
    test_html_import()
    test_template_upload_rejects_non_latex()
    test_migrations_upgrade_legacy_database_and_are_repeatable()
    test_personal_details_are_stored_in_settings()
    print("ApplyKit verification passed.")
