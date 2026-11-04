"""Verify Glassdoor location formatting against the pinned JobSpy parser."""

import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import jobspy.glassdoor
from jobspy.model import Country, JobPost, Location
import pytest

from app import job_search_adapter
from app.database_models import JobSearchPreferenceModel
from app.job_search_adapter import JobSearchAdapter
from app.job_search_glassdoor import C_GLASSDOOR_LOGGER_NAME, GlassdoorSearchGuard
from app.main import app
from app.scheduler.repository import ScheduleRepository
from app.scheduler.triggers import SystemClock

C_GLASSDOOR_CITY_ID = 2727242
C_HTTP_OK = 200
C_LOCATION_ID_FIELD = "locationId"
C_LOCATION_TYPE_FIELD = "locationType"
C_CITY_LOCATION_TYPE = "CITY"
C_SEARCH_OPERATION = "JobSearchResultsQuery"
C_DETAILS_OPERATION = "JobDetails"
C_SEARCH_RESPONSE = [{"data": {"jobListings": {
    "jobListings": [{"jobview": {
        "job": {"jobTitleText": "Backend Developer", "listingId": 123},
        "map": {"country": "Germany"},
        "overview": {},
        "header": {
            "locationName": "Düsseldorf", "locationType": "C",
            "payCurrency": None, "payPeriod": None, "payPeriodAdjustedPay": None,
            "adOrderSponsorshipLevel": "ORGANIC", "ageInDays": 0,
            "employer": {"id": 456}, "employerNameFromSearch": "Example Company",
        },
    }}],
    "paginationCursors": [],
}}}]
C_DETAILS_RESPONSE = [{"data": {"j123": {"job": {"description": "Build Python services"}}}}]


@pytest.fixture
def glassdoor_guard(monkeypatch) -> GlassdoorSearchGuard:
    """Isolate each rate-limit test from the application's process-wide cooldown."""
    search_guard = GlassdoorSearchGuard()
    monkeypatch.setattr(job_search_adapter, "C_GLASSDOOR_GUARD", search_guard)
    return search_guard


class TestGlassdoorLocation:
    """Keep autocomplete city terms separate from Glassdoor's country setting."""

    @pytest.mark.parametrize("city", ["Düsseldorf", "Berlin", "München"])
    def test_city_is_forwarded_without_country(self, city: str) -> None:
        """Preserve city spelling and Unicode while selecting the German domain."""
        saved_preference = JobSearchPreferenceModel(
            id=1, job_title="Developer", country="Germany", city=city,
            radius_km=25, keywords=[], posted_within_days=1,
        )
        search_adapter = JobSearchAdapter(None)
        arguments = search_adapter.build_arguments(saved_preference, "glassdoor", 50)
        assert arguments["location"] == city
        assert arguments["country_indeed"] == "germany"
        assert arguments["hours_old"] == 24
        assert arguments["distance"] == 16

    @pytest.mark.parametrize("site", ["indeed", "linkedin"])
    def test_other_boards_keep_full_location(self, site: str) -> None:
        """Retain existing location formatting for boards using the full place name."""
        saved_preference = JobSearchPreferenceModel(
            id=1, job_title="Developer", country="Germany", city="Düsseldorf",
            radius_km=25, keywords=[], posted_within_days=None,
        )
        search_adapter = JobSearchAdapter(None)
        arguments = search_adapter.build_arguments(saved_preference, site, 50)
        assert arguments["location"] == "Düsseldorf, Germany"

    def test_country_only_search_retains_explicit_location(self) -> None:
        """Avoid JobSpy's implicit remote search when no city has been selected."""
        saved_preference = JobSearchPreferenceModel(
            id=1, job_title="Developer", country="Germany", city="",
            radius_km=25, keywords=[], posted_within_days=None,
        )
        search_adapter = JobSearchAdapter(None)
        arguments = search_adapter.build_arguments(saved_preference, "glassdoor", 50)
        assert arguments["location"] == "Germany"

    def test_installed_parser_resolves_city_and_persists_jobs(self, monkeypatch) -> None:
        """Exercise real autocomplete parsing and persistence without live networking."""
        autocomplete_terms = []

        class AutocompleteResponse:
            """Represent a successful Glassdoor autocomplete HTTP response."""

            status_code = 200

            def __init__(self, location_term: str) -> None:
                """Record the decoded term to reproduce the observed live responses."""
                self.location_term = location_term

            def json(self) -> list[dict]:
                """Return the city match only for Glassdoor's accepted autocomplete term."""
                if self.location_term != "Düsseldorf":
                    return []
                return [{"locationId": C_GLASSDOOR_CITY_ID, "locationType": "C"}]

        class AutocompleteSession:
            """Replace HTTP transport while retaining JobSpy's location parsing logic."""

            def __init__(self) -> None:
                """Provide the mutable headers expected by the pinned scraper."""
                self.headers = {}

            def get(self, request_url: str) -> AutocompleteResponse:
                """Decode the Unicode term and require the selected German domain."""
                parsed_url = urlsplit(request_url)
                assert parsed_url.hostname == "www.glassdoor.de"
                assert parsed_url.path == "/autocomplete/location"
                location_term = parse_qs(parsed_url.query)["term"][0]
                autocomplete_terms.append(location_term)
                return AutocompleteResponse(location_term)

        def create_session(*positional_arguments, **arguments) -> AutocompleteSession:
            """Create a new fake HTTP session for the real Glassdoor scraper."""
            return AutocompleteSession()

        class GraphResponse:
            """Supply search and detail responses to the actual result parsers."""

            status_code = C_HTTP_OK

            def __init__(self, payload: list[dict]) -> None:
                """Keep the selected response fixture separate from transport."""
                self.payload = payload

            def json(self) -> list[dict]:
                """Return the GraphQL response expected by the installed scraper."""
                return self.payload

        def fetch_graph(scraper, operation: str, query: str, variables: dict) -> GraphResponse:
            """Verify autocomplete output and exercise search and detail parsing."""
            if operation == C_SEARCH_OPERATION:
                assert variables[C_LOCATION_ID_FIELD] == C_GLASSDOOR_CITY_ID
                assert variables[C_LOCATION_TYPE_FIELD] == C_CITY_LOCATION_TYPE
                return GraphResponse(C_SEARCH_RESPONSE)
            assert operation == C_DETAILS_OPERATION
            return GraphResponse(C_DETAILS_RESPONSE)

        monkeypatch.setattr(jobspy.glassdoor, "create_session", create_session)
        monkeypatch.setattr(jobspy.glassdoor.Glassdoor, "_graph", fetch_graph)
        with TestClient(app) as client:
            saved_response = client.post("/api/job-search-preferences", json={
                "job_title": "Developer", "country": "Germany", "city": "Düsseldorf",
            })
            assert saved_response.status_code == 201
            preference_id = saved_response.json()["id"]
            search_response = client.post("/api/job-search", json={
                "preference_id": preference_id, "sites": ["glassdoor"], "results_wanted": 1,
            })
            assert search_response.status_code == 200, search_response.text
            assert search_response.json()["boards"]["glassdoor"] == {"status": "completed", "count": 1}
            assert autocomplete_terms == ["Düsseldorf"]
            listing = client.get("/api/available-jobs", params={"preference_id": preference_id}).json()
            assert listing["total"] == 1
            assert listing["items"][0]["job_title"] == "Backend Developer"
            assert listing["items"][0]["location"] == "Düsseldorf, Germany"


class TestGlassdoorRateLimiting:
    """Expose swallowed HTTP 429 failures and preserve available jobs."""

    @pytest.mark.parametrize("request_stage", ["autocomplete", "results"])
    def test_real_scraper_rate_limit_is_reported_and_cooldown_blocks_requests(
        self, monkeypatch, glassdoor_guard: GlassdoorSearchGuard, request_stage: str,
    ) -> None:
        """Exercise actual JobSpy HTTP-status handling and reject retries locally."""
        http_requests = []
        original_handlers = list(logging.getLogger(C_GLASSDOOR_LOGGER_NAME).handlers)

        class StatusResponse:
            """Provide fake transport responses for real Glassdoor parsing."""

            def __init__(self, status_code: int) -> None:
                """Store the HTTP status without making any external request."""
                self.status_code = status_code

            def json(self) -> list[dict]:
                """Provide a city match for the successful autocomplete stage."""
                assert self.status_code == 200
                return [{"locationId": C_GLASSDOOR_CITY_ID, "locationType": "C"}]

        class RateLimitedSession:
            """Rate-limit either autocomplete or the first results page."""

            def __init__(self) -> None:
                """Provide the headers that JobSpy sets on a new session."""
                self.headers = {}

            def get(self, request_url: str) -> StatusResponse:
                """Return a city match unless autocomplete is being rate-limited."""
                http_requests.append(request_url)
                return StatusResponse(429 if request_stage == "autocomplete" else 200)

            def post(self, request_url: str, **arguments) -> StatusResponse:
                """Return HTTP 429 for the real scraper's results-page request."""
                http_requests.append(request_url)
                return StatusResponse(429)

        def create_session(*positional_arguments, **arguments) -> RateLimitedSession:
            """Replace only the HTTP transport used by the installed scraper."""
            return RateLimitedSession()

        monkeypatch.setattr(jobspy.glassdoor, "create_session", create_session)
        with TestClient(app) as client:
            saved_response = client.post("/api/job-search-preferences", json={
                "job_title": "Developer", "country": "Germany", "city": "Düsseldorf",
            })
            preference_id = saved_response.json()["id"]
            payload = {"preference_id": preference_id, "sites": ["glassdoor"]}
            first_response = client.post("/api/job-search", json=payload)
            assert first_response.status_code == 502
            assert "HTTP 429" in first_response.json()["detail"]["warnings"][0]
            assert "5 minutes" in first_response.text
            request_count = len(http_requests)
            assert request_count == (1 if request_stage == "autocomplete" else 2)

            retry_response = client.post("/api/job-search", json=payload)
            assert retry_response.status_code == 502
            assert "paused after HTTP 429" in retry_response.text
            assert len(http_requests) == request_count
            assert logging.getLogger(C_GLASSDOOR_LOGGER_NAME).handlers == original_handlers

            # Advance the app clock, without waiting or claiming Glassdoor has reset.
            with_schedule_repository = ScheduleRepository()
            try:
                cooldown_end = with_schedule_repository.get_board_cooldown("glassdoor") + timedelta(seconds=1)
            finally:
                with_schedule_repository.close()
            monkeypatch.setattr(SystemClock, "now", lambda self: cooldown_end)
            client.post("/api/job-search", json=payload)
            assert len(http_requests) == request_count * 2
            assert logging.getLogger(C_GLASSDOOR_LOGGER_NAME).handlers == original_handlers

    @pytest.mark.parametrize("partial_jobs", [False, True])
    def test_rate_limit_keeps_other_boards_and_previously_fetched_jobs(
        self, monkeypatch, glassdoor_guard: GlassdoorSearchGuard, partial_jobs: bool,
    ) -> None:
        """Keep old data and successful results when Glassdoor stops during a search."""
        def scrape_indeed(scraper, scraper_input) -> list[JobPost]:
            """Return one successfully fetched job from an independent board."""
            return [JobPost(
                title="Indeed Developer", company="Example Company",
                job_url="https://example.test/indeed", location=None,
                description="Python services",
            )]

        def scrape_glassdoor(scraper, scraper_input) -> list[JobPost]:
            """Reproduce a logged HTTP 429 with optional earlier page results."""
            logging.getLogger(C_GLASSDOOR_LOGGER_NAME).error("Glassdoor response status code 429")
            return [JobPost(
                title="Glassdoor Developer", company="Example Company",
                job_url="https://example.test/glassdoor", location=None,
                description="Python services",
            )] if partial_jobs else []

        monkeypatch.setattr(jobspy.Indeed, "scrape", scrape_indeed)
        monkeypatch.setattr(jobspy.glassdoor.Glassdoor, "scrape", scrape_glassdoor)
        with TestClient(app) as client:
            saved_response = client.post("/api/job-search-preferences", json={
                "job_title": "Developer", "country": "Germany", "city": "Düsseldorf",
            })
            preference_id = saved_response.json()["id"]
            assert client.post("/api/job-search", json={
                "preference_id": preference_id, "sites": ["indeed"],
            }).status_code == 200
            response = client.post("/api/job-search", json={
                "preference_id": preference_id, "sites": ["indeed", "glassdoor"],
            })
            assert response.status_code == 200, response.text
            assert response.json()["boards"]["indeed"] == {"status": "completed", "count": 1}
            assert response.json()["boards"]["glassdoor"] == {
                "status": "partial" if partial_jobs else "failed",
                "count": 1 if partial_jobs else 0,
            }
            assert "HTTP 429" in response.json()["warnings"][0]
            listing = client.get("/api/available-jobs").json()
            assert listing["total"] == (2 if partial_jobs else 1)
            only_glassdoor = client.post("/api/job-search", json={
                "preference_id": preference_id, "sites": ["glassdoor"],
            })
            assert only_glassdoor.status_code == 502
            assert client.get("/api/available-jobs").json()["total"] == listing["total"]

    def test_successful_empty_search_does_not_start_cooldown(
        self, monkeypatch, glassdoor_guard: GlassdoorSearchGuard,
    ) -> None:
        """Distinguish a successful empty result from an observed rate-limit failure."""
        def scrape_glassdoor(scraper, scraper_input) -> list[JobPost]:
            """Return no postings without logging a transport failure."""
            return []

        monkeypatch.setattr(jobspy.glassdoor.Glassdoor, "scrape", scrape_glassdoor)
        with TestClient(app) as client:
            saved_response = client.post("/api/job-search-preferences", json={
                "job_title": "Developer", "country": "Germany", "city": "Düsseldorf",
            })
            response = client.post("/api/job-search", json={
                "preference_id": saved_response.json()["id"], "sites": ["glassdoor"],
            })
            assert response.status_code == 200
            assert response.json()["boards"]["glassdoor"] == {"status": "completed", "count": 0}
            assert response.json()["warnings"] == []
            assert glassdoor_guard.retry_after == 0.0
