from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    test_core_workflow()
    test_html_import()
    test_template_upload_rejects_non_latex()
    print("ApplyKit verification passed.")
