"""JobSpy integration, persistence, migration, and pagination without live scraping."""

from contextlib import closing
from datetime import date
import json
import sqlite3
from threading import Barrier

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app import job_search
from app.database import connect
from app.db_migrations import MIGRATIONS, run_migrations
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def preference(client, **fields):
    response = client.post("/api/job-search-preferences", json={"job_title": "Developer", "country": "USA", **fields})
    assert response.status_code == 201
    return response.json()["id"]


def frame(count=1, **fields):
    return pd.DataFrame([
        {"title": f"Developer {index}", "job_url": f"https://example.test/job/{index}",
         "company": "Company", "description": "Build PYTHON and SQL services", "location": "Boston, USA",
         "date_posted": date(2026, 10, 7), "is_remote": True, "min_amount": float("nan"), **fields}
        for index in range(count)
    ])


def fetch(client, preference_id, sites=None):
    payload = {"preference_id": preference_id}
    if sites is not None:
        payload["sites"] = sites
    return client.post("/api/job-search", json=payload)


@pytest.mark.parametrize("level", ["INFO", "DEBUG", "TRACE"])
def test_search_logging_and_result_level(level, tmp_path, monkeypatch):
    monkeypatch.setenv("CV_BUILDER_LOG_LEVEL", level)
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: frame(2, company="Trace Company"))
    with TestClient(app) as client:
        saved = preference(client, city="Boston", radius_km=50, posted_within_days=7, keywords=["python"])
        response = fetch(client, saved, ["indeed"])
        assert response.status_code == 200
        assert response.json()["fetched"] == 2

    content = (tmp_path / "logs" / "cv_builder.log").read_text(encoding="utf-8")
    assert f"job_search_started preference_id={saved}" in content
    assert 'sites=["indeed"] results_wanted=50' in content
    assert '"job_title": "Developer"' in content
    assert '"city": "Boston"' in content
    assert '"radius_km": 50' in content
    assert '"posted_within_days": 7' in content
    assert '"keywords": ["python"]' in content
    assert f"job_search_board_completed preference_id={saved} site=indeed count=2 skipped=0" in content
    assert f"job_search_completed preference_id={saved} fetched=2" in content
    result_lines = [line for line in content.splitlines() if "job_search_result " in line]
    assert len(result_lines) == (2 if level == "TRACE" else 0)
    assert ("Trace Company" in content) == (level == "TRACE")
    for index, line in enumerate(result_lines):
        assert " TRACE app.job_search " in line
        job = json.loads(line.split(" job=", 1)[1])
        assert job["job_url"] == f"https://example.test/job/{index}"
        assert job["description"] == "Build PYTHON and SQL services"
        assert json.loads(job["raw_data"])["min_amount"] is None


def test_all_four_boards_run_concurrently_with_saved_filters(client, monkeypatch):
    saved = preference(client, city="Boston", radius_km=50, posted_within_days=7, keywords=["python", "sql"])
    barrier = Barrier(4, timeout=10)
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs)
        barrier.wait()  # Sequential board calls would time out.
        return frame()

    monkeypatch.setattr(job_search, "scrape_jobs", scrape)
    response = fetch(client, saved)
    assert response.status_code == 200, response.text
    assert response.json()["fetched"] == 4
    assert {call["site_name"][0] for call in calls} == {"linkedin", "indeed", "glassdoor", "zip_recruiter"}
    for call in calls:
        assert call["search_term"] == "Developer"
        expected_location = "Boston" if call["site_name"] == ["glassdoor"] else "Boston, USA"
        assert call["location"] == expected_location
        assert call["distance"] == 32
        assert call["hours_old"] == 168
        assert call["country_indeed"] == "usa"
        assert call["fetch_description"] is True
    items = client.get("/api/available-jobs").json()["items"]
    assert len(items) == 4
    assert all(item["date_posted"] == "2026-10-07" and item["is_remote"] for item in items)
    with closing(connect()) as db:
        raw = json.loads(db.execute("SELECT raw_data FROM available_jobs LIMIT 1").fetchone()[0])
        assert raw["min_amount"] is None


def test_installed_jobspy_adapter_and_schema(client, monkeypatch):
    # Exercise the real pinned library, replacing only its HTTP scraper.
    import jobspy
    from jobspy.model import Country, JobPost, JobResponse, Location

    def scrape(scraper, inputs):
        assert inputs.country == Country.GERMANY
        assert inputs.fetch_description is True
        assert inputs.distance == 16
        return JobResponse(jobs=[JobPost(
            title="Backend Developer", company_name="Actual schema",
            job_url="https://example.test/real-schema",
            location=Location(city="Berlin", country=Country.GERMANY),
            description="Python services", date_posted=date(2026, 10, 7),
        )])

    monkeypatch.setattr(jobspy.Indeed, "scrape", scrape)
    saved = preference(client, country="Germany", city="Berlin", radius_km=25)
    response = fetch(client, saved, ["indeed"])
    assert response.status_code == 200, response.text
    assert response.json()["fetched"] == 1
    item = client.get("/api/available-jobs").json()["items"][0]
    assert item["company"] == "Actual schema"
    assert item["location"] == "Berlin, Germany"
    assert item["date_posted"] == "2026-10-07"


def test_repeat_fetch_updates_jobs_and_links_multiple_preferences(client, monkeypatch):
    first, second = preference(client), preference(client, job_title="Engineer")
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: frame())
    assert fetch(client, first, ["indeed"]).status_code == 200
    original = client.get("/api/available-jobs").json()["items"][0]
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: frame(company="Updated Company"))
    assert fetch(client, first, ["indeed", "indeed"]).json()["fetched"] == 1
    assert fetch(client, second, ["indeed"]).status_code == 200
    listing = client.get("/api/available-jobs").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == original["id"]
    assert listing["items"][0]["first_fetched_at"] == original["first_fetched_at"]
    assert listing["items"][0]["company"] == "Updated Company"
    for saved in (first, second):
        assert client.get("/api/available-jobs", params={"preference_id": saved}).json()["total"] == 1
    with TestClient(app) as restarted:
        assert restarted.get("/api/available-jobs").json()["total"] == 1
    assert client.delete(f"/api/job-search-preferences/{first}").status_code == 204
    assert client.get("/api/available-jobs").json()["total"] == 1


def test_pagination_filters_and_real_applied_status(client, monkeypatch):
    saved = preference(client)
    other = preference(client)
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: frame(25))
    assert fetch(client, saved, ["indeed"]).status_code == 200
    first = client.get("/api/available-jobs", params={"page_size": 10}).json()
    second = client.get("/api/available-jobs", params={"page": 2, "page_size": 10}).json()
    last = client.get("/api/available-jobs", params={"page": 99, "page_size": 10}).json()
    assert first["total"] == 25 and first["total_pages"] == 3
    assert len(first["items"]) == len(second["items"]) == 10
    assert last["page"] == 3 and len(last["items"]) == 5
    assert first["has_next"] and not first["has_previous"]
    assert last["has_previous"] and not last["has_next"]
    ids = [item["id"] for page in (first, second, last) for item in page["items"]]
    assert ids == sorted(set(ids), reverse=True)
    assert client.get("/api/available-jobs", params={"search": "Developer 24", "site": "indeed", "preference_id": saved}).json()["total"] == 1
    assert client.get("/api/available-jobs", params={"site": "linkedin"}).json()["total"] == 0
    assert client.get("/api/available-jobs", params={"preference_id": other}).json()["total"] == 0
    payload = {"company": "Company", "job_title": "Developer", "source_url": first["items"][0]["job_url"], "status": "Applied"}
    application = client.post("/api/applications", json=payload).json()
    assert client.get("/api/available-jobs").json()["items"][0]["applied"] is True
    client.put(f"/api/applications/{application['id']}", json={**payload, "status": "Draft"})
    assert client.get("/api/available-jobs").json()["items"][0]["applied"] is False


def test_partial_failure_retains_results_and_all_failure_preserves_old_jobs(client, monkeypatch):
    saved = preference(client)

    def scrape(**kwargs):
        if kwargs["site_name"] == ["linkedin"]:
            raise RuntimeError("private diagnostic")
        return frame()

    monkeypatch.setattr(job_search, "scrape_jobs", scrape)
    response = fetch(client, saved, ["linkedin", "indeed"])
    assert response.status_code == 200
    assert response.json()["boards"]["linkedin"]["status"] == "failed"
    assert "private diagnostic" not in response.text
    response = fetch(client, saved, ["linkedin"])
    assert response.status_code == 502
    assert response.json()["detail"]["warnings"]
    assert client.get("/api/available-jobs").json()["total"] == 1


def test_country_support_and_other_boards(client, monkeypatch):
    calls = []
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: calls.append(kwargs) or frame())
    saved = preference(client, country="DE", city="Berlin")
    response = fetch(client, saved)
    assert response.status_code == 200
    assert response.json()["boards"]["zip_recruiter"]["status"] == "failed"
    assert len(calls) == 3
    assert all(call["country_indeed"] == "germany" for call in calls)
    blank = preference(client, country="")
    assert fetch(client, blank, ["indeed", "glassdoor"]).status_code == 502
    assert fetch(client, blank, ["linkedin"]).status_code == 200
    for country, site in [("India", "naukri"), ("Bangladesh", "bdjobs"), ("USA", "bayt")]:
        assert fetch(client, preference(client, country=country), [site]).status_code == 200


def test_keywords_missing_values_and_unsafe_urls(client, monkeypatch):
    saved = preference(client, keywords=["PYTHON", "SQL"])
    records = frame().to_dict("records")
    records += frame(description="Python only", job_url="https://example.test/no-sql").to_dict("records")
    records += frame(description=None, job_url="https://example.test/no-description").to_dict("records")
    for url in ("javascript:alert(1)", "not a URL", "https://user:secret@example.test/job", "https://["):
        records += frame(job_url=url).to_dict("records")
    records += frame(title=None).to_dict("records")
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: pd.DataFrame(records))
    response = fetch(client, saved, ["indeed"])
    assert response.status_code == 200
    assert response.json()["fetched"] == 1
    assert response.json()["warnings"] == ["indeed: skipped 5 incomplete postings."]


def test_validation_and_empty_results(client, monkeypatch):
    saved = preference(client)
    monkeypatch.setattr(job_search, "scrape_jobs", lambda **kwargs: pd.DataFrame())
    assert fetch(client, saved, ["indeed"]).json()["fetched"] == 0
    listing = client.get("/api/available-jobs").json()
    assert listing["items"] == [] and listing["total_pages"] == 1
    assert not listing["has_next"] and not listing["has_previous"]
    assert fetch(client, 999, ["indeed"]).status_code == 404
    invalid_search_fields = (
        {"sites": []},
        {"sites": ["unknown"]},
        {"results_wanted": 0},
        {"results_wanted": 1001},
        {"results_wanted": True},
        {"results_wanted": 1000.5},
        {"results_wanted": "1000"},
        {"preference_id": True},
    )
    for invalid_fields in invalid_search_fields:
        assert client.post("/api/job-search", json={"preference_id": saved, **invalid_fields}).status_code == 422
    for query in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"site": "unknown"}):
        assert client.get("/api/available-jobs", params=query).status_code == 422
    assert client.get("/api/available-jobs?preference_id=999").status_code == 404


class TestExtendedJobSearchLimit:
    """Verify larger daily source requests reach the scraper and persist beyond 100 jobs."""

    @pytest.mark.parametrize("requested_limit", [101, 1000])
    def test_daily_request_preserves_requested_limit_and_all_matching_jobs(
        self, client: TestClient, monkeypatch, requested_limit: int,
    ) -> None:
        """Pass the extended limit and 24-hour age to the scraper without truncating storage."""
        preference_id = preference(client, posted_within_days=1, keywords=["python", "sql"])
        scraper_requests = []

        def scrape_board(**arguments):
            """Return a matching source batch sized by the actual forwarded request."""
            scraper_requests.append(arguments)
            return frame(arguments["results_wanted"])

        monkeypatch.setattr(job_search, "scrape_jobs", scrape_board)
        response = client.post("/api/job-search", json={
            "preference_id": preference_id,
            "sites": ["indeed"],
            "results_wanted": requested_limit,
        })
        assert response.status_code == 200, response.text
        assert len(scraper_requests) == 1
        assert scraper_requests[0]["results_wanted"] == requested_limit
        assert scraper_requests[0]["hours_old"] == 24
        assert response.json()["fetched"] == requested_limit
        assert response.json()["boards"]["indeed"]["count"] == requested_limit
        listing = client.get("/api/available-jobs", params={"preference_id": preference_id}).json()
        assert listing["total"] == requested_limit
        assert listing["items"][0]["job_title"] == f"Developer {requested_limit - 1}"

    def test_search_page_offers_one_thousand_results_and_retains_default(
        self, client: TestClient,
    ) -> None:
        """Expose the new maximum in the rendered form without increasing the default request."""
        response = client.get("/")
        assert response.status_code == 200
        document = BeautifulSoup(response.text, "html.parser")
        result_limit = document.find("select", id="jobSearchLimit")
        assert result_limit.find("option", value="1000") is not None
        assert result_limit.find("option", selected=True)["value"] == "50"
        assert document.find(id="jobSearchLimitHelp") is not None


def test_deleted_preference_during_scraping_returns_conflict(client, monkeypatch):
    saved = preference(client)

    def scrape(**kwargs):
        client.delete(f"/api/job-search-preferences/{saved}")
        return frame()

    monkeypatch.setattr(job_search, "scrape_jobs", scrape)
    assert fetch(client, saved, ["indeed"]).status_code == 409
    assert client.get("/api/available-jobs").json()["total"] == 0


@pytest.mark.parametrize("previous_schema", [False, True])
def test_jobs_migration_preserves_existing_data_and_is_repeatable(previous_schema):
    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        if previous_schema:
            db.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            for migration in MIGRATIONS[:3]:
                migration.apply(db)
                db.execute("INSERT INTO schema_migrations VALUES (?, ?)", (migration.version, migration.name))
            db.execute("INSERT INTO applications(company, job_title) VALUES ('Original', 'Role')")
            db.execute("INSERT INTO job_search_preferences(job_title) VALUES ('Original search')")
            db.commit()
        run_migrations(db)
        db.execute("INSERT INTO available_jobs(site, job_url, job_title) VALUES ('indeed', 'https://example.test/job', 'Stored')")
        db.commit()
        run_migrations(db)
        assert db.execute("SELECT job_title FROM available_jobs").fetchone()[0] == "Stored"
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)
        if previous_schema:
            assert db.execute("SELECT company FROM applications").fetchone()[0] == "Original"
            assert db.execute("SELECT job_title FROM job_search_preferences").fetchone()[0] == "Original search"
