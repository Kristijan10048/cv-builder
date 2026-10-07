import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import connect
from app.db_migrations import MIGRATIONS, run_migrations
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
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)
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
            "linkedin_url": "https://linkedin.com/in/ada-lovelace",
            "strongest_programming_language": "Python",
            "nationality": "British",
            "date_of_birth": "1815-12-10",
            "german_language_level": "B2",
            "english_language_level": "Native",
            "onsite_availability": "Yes",
            "travel_willingness": "No",
        }
        try:
            saved = client.put("/api/personal-details", json=payload)
            assert saved.status_code == 200
            assert saved.json()["first_name"] == "Ada"
            assert saved.json()["date_of_birth"] == "1815-12-10"
            assert saved.json()["onsite_availability"] == "Yes"
            assert saved.json()["linkedin_url"] == "https://linkedin.com/in/ada-lovelace"
            assert saved.json()["strongest_programming_language"] == "Python"
            assert client.get("/api/personal-details").json()["city"] == "London"
            with connect() as db:
                stored = db.execute(
                    "SELECT value FROM settings WHERE key = 'personal_details'"
                ).fetchone()[0]
            assert '"first_name": "Ada"' in stored
        finally:
            client.put("/api/personal-details", json=original)


def test_personal_details_are_presented_in_the_profile_view():
    with TestClient(app) as client:
        html = client.get("/").text

    profile_view = html.index('id="profileView"')
    personal_form = html.index('id="personalDetailsForm"')
    settings_view = html.index('id="settingsView"')

    assert 'data-view="profile"' in html
    assert profile_view < personal_form < settings_view
    assert 'id="profileDetails"' in html
    assert 'id="editProfileButton"' in html
    assert 'id="profileNationality"' in html
    assert 'id="profileDateOfBirth"' in html
    assert 'id="profileGermanLanguageLevel"' in html
    assert 'id="profileEnglishLanguageLevel"' in html
    assert 'id="profileOnsiteAvailability"' in html
    assert 'id="profileTravelWillingness"' in html
    assert 'id="profileLinkedinUrl"' in html
    assert 'id="profileStrongestProgrammingLanguage"' in html
    assert html.count('data-action="edit-profile"') == 2
    assert 'data-action="cancel-profile-edit"' in html
    assert "/static/app.js?v=" in html


def test_applications_page_has_application_history_table():
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="applicationsView"' in html
    assert 'class="application-table"' in html
    assert 'id="applicationList"' in html
    for heading in ("Company", "Role", "Job page", "Applied on", "Status"):
        assert f"<th>{heading}</th>" in html


def test_extension_supports_profile_fields_and_application_saving():
    extension_dir = Path(__file__).parents[1] / "firefox-extension"
    background_source = (extension_dir / "background.js").read_text(encoding="utf-8")
    popup_html = (extension_dir / "popup" / "popup.html").read_text(encoding="utf-8")
    popup_source = (extension_dir / "popup" / "popup.js").read_text(encoding="utf-8")
    content_source = (extension_dir / "content.js").read_text(encoding="utf-8")

    assert 'files: ["/content.js"]' in popup_source
    for profile_key in (
        "nationality",
        "date_of_birth",
        "german_language_level",
        "english_language_level",
        "onsite_availability",
        "travel_willingness",
        "linkedin_url",
        "strongest_programming_language",
    ):
        assert profile_key in content_source

    assert 'id="saveButton"' in popup_html
    assert "applykit:application-details" in popup_source
    assert "applykit:application-details" in content_source
    assert "applykit:save-application" in popup_source
    assert "applykit:save-application" in background_source
    assert 'status: "Applied"' in background_source


if __name__ == "__main__":
    test_core_workflow()
    test_html_import()
    test_template_upload_rejects_non_latex()
    test_migrations_upgrade_legacy_database_and_are_repeatable()
    test_personal_details_are_stored_in_settings()
    test_personal_details_are_presented_in_the_profile_view()
    test_applications_page_has_application_history_table()
    test_extension_supports_profile_fields_and_application_saving()
    print("ApplyKit verification passed.")
