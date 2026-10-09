"""Exercise transaction and serialization boundaries introduced by the search refactor."""

import sqlite3
from datetime import datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect, update
from sqlalchemy.engine import Connection

from app.database_models import AvailableJobModel, DatabaseModel
from app.job_search_repository import JobSearchRepository
from app.main import app


@pytest.fixture
def api_client():
    """Initialize the application with the suite's isolated temporary database."""
    with TestClient(app) as client:
        yield client


class FailingJobSearchRepository(JobSearchRepository):
    """Simulate a storage failure after earlier postings have been written."""

    def save_job(self, connection: Connection, preference_id: int, job: AvailableJobModel) -> None:
        """Fail for the designated posting while using real persistence for preceding jobs."""
        if job.job_url.endswith("/fail"):
            raise sqlite3.IntegrityError("Simulated storage failure")
        super().save_job(connection, preference_id, job)


class TestJobSearchRepository:
    """Verify atomic writes, bound filtering, and SQLite flag serialization."""

    @staticmethod
    def create_preference(api_client: TestClient, job_title: str = "Developer") -> int:
        """Create a saved search through the unchanged preference API."""
        response = api_client.post("/api/job-search-preferences", json={"job_title": job_title})
        assert response.status_code == 201
        return response.json()["id"]

    def test_model_mappings_match_the_existing_migrated_schema(self, api_client):
        """Every migrated table must have a mapping with matching columns and primary keys."""
        repository = JobSearchRepository()
        schema_inspector = inspect(repository.engine)
        assert set(schema_inspector.get_table_names()) == set(DatabaseModel.metadata.tables)
        for table_name, mapped_table in DatabaseModel.metadata.tables.items():
            stored_columns = schema_inspector.get_columns(table_name)
            assert {column["name"] for column in stored_columns} == set(mapped_table.columns.keys())
            stored_primary_key = schema_inspector.get_pk_constraint(table_name)
            assert set(stored_primary_key["constrained_columns"]) == set(mapped_table.primary_key.columns.keys())

    def test_sqlalchemy_inserts_and_updates_keep_database_timestamps(self, api_client):
        """Insert defaults must produce real timestamps and refreshes must retain first fetch."""
        preference_id = self.create_preference(api_client)
        repository = JobSearchRepository()
        job = AvailableJobModel(site="indeed", job_url="https://example.test/timestamps", job_title="Developer")
        repository.save_jobs(preference_id, [job])
        inserted_job = api_client.get("/api/available-jobs").json()["items"][0]
        assert isinstance(inserted_job["id"], int)
        assert datetime.fromisoformat(inserted_job["first_fetched_at"]) > datetime(2000, 1, 1)
        assert datetime.fromisoformat(inserted_job["fetched_at"]) > datetime(2000, 1, 1)
        historical_timestamp = "2001-01-01 00:00:00"
        statement = update(AvailableJobModel).where(AvailableJobModel.id == inserted_job["id"]).values(
            first_fetched_at=historical_timestamp,
            fetched_at=historical_timestamp,
        )
        with repository.engine.begin() as connection:
            connection.execute(statement)
        repository.save_jobs(preference_id, [job])
        refreshed_job = api_client.get("/api/available-jobs").json()["items"][0]
        assert refreshed_job["id"] == inserted_job["id"]
        assert refreshed_job["first_fetched_at"] == historical_timestamp
        assert datetime.fromisoformat(refreshed_job["fetched_at"]) > datetime.fromisoformat(historical_timestamp)

    def test_failed_write_rolls_back_postings_updates_and_links(self, api_client):
        """A mid-batch failure must undo inserted jobs, updated jobs, and search links."""
        original_preference_id = self.create_preference(api_client)
        new_preference_id = self.create_preference(api_client, "Engineer")
        repository = JobSearchRepository()
        original_job = AvailableJobModel(
            site="indeed",
            job_url="https://example.test/original",
            job_title="Developer",
            company="Original company",
        )
        repository.save_jobs(original_preference_id, [original_job])
        updated_job = AvailableJobModel(
            site=original_job.site,
            job_url=original_job.job_url,
            job_title="Updated developer",
            company="Updated company",
        )
        new_job = AvailableJobModel(site="indeed", job_url="https://example.test/new", job_title="New job")
        failing_job = AvailableJobModel(site="indeed", job_url="https://example.test/fail", job_title="Failure")
        with pytest.raises(sqlite3.IntegrityError, match="Simulated storage failure"):
            FailingJobSearchRepository().save_jobs(new_preference_id, [updated_job, new_job, failing_job])
        listing = api_client.get("/api/available-jobs").json()
        assert listing["total"] == 1
        assert listing["items"][0]["company"] == original_job.company
        assert listing["items"][0]["job_title"] == original_job.job_title
        new_search_listing = api_client.get("/api/available-jobs", params={"preference_id": new_preference_id}).json()
        assert new_search_listing["total"] == 0

    def test_text_with_quotes_is_bound_and_empty_fetch_preserves_jobs(self, api_client):
        """Quoted filter text must remain data and an empty successful save must retain jobs."""
        preference_id = self.create_preference(api_client)
        repository = JobSearchRepository()
        quoted_title = "Developer ' OR 1=1 --"
        jobs = [
            AvailableJobModel(site="indeed", job_url="https://example.test/quoted", job_title=quoted_title),
            AvailableJobModel(site="linkedin", job_url="https://example.test/other", job_title="Other developer"),
        ]
        repository.save_jobs(preference_id, jobs)
        repository.save_jobs(preference_id, [])
        assert api_client.get("/api/available-jobs").json()["total"] == 2
        response = api_client.get("/api/available-jobs", params={
            "preference_id": preference_id,
            "site": "indeed",
            "search": f"  {quoted_title}  ",
        })
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["job_title"] == quoted_title
        empty_listing = api_client.get("/api/available-jobs", params={"search": "' OR 2=2 --"}).json()
        assert empty_listing["total"] == 0

    def test_remote_flags_preserve_unknown_false_and_true(self, api_client):
        """Listing models must distinguish missing remote data from false and true flags."""
        preference_id = self.create_preference(api_client)
        jobs = [
            AvailableJobModel(
                site="indeed",
                job_url=f"https://example.test/remote/{index}",
                job_title=f"Remote flag {index}",
                is_remote=remote_value,
            )
            for index, remote_value in enumerate([None, 0, 1])
        ]
        JobSearchRepository().save_jobs(preference_id, jobs)
        listing = api_client.get("/api/available-jobs").json()
        remote_values = {item["job_title"]: item["is_remote"] for item in listing["items"]}
        assert remote_values["Remote flag 0"] is None
        assert remote_values["Remote flag 1"] is False
        assert remote_values["Remote flag 2"] is True
