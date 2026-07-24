from fastapi.testclient import TestClient

from app.main import app


def test_core_workflow():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.put(
            "/api/templates",
            json={"cv": "Python developer", "cover_letter": "Dear hiring team"},
        ).status_code == 200

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


if __name__ == "__main__":
    test_core_workflow()
    test_html_import()
    print("ApplyKit verification passed.")
