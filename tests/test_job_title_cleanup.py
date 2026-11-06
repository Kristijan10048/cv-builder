"""Verify title cleanup, persisted search results, and transactional backfills."""

import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update

from app import database, db_migrations
from app.database_models import AvailableJobModel, JobSearchResultModel
from app.db_migrations import Migration
from app.job_search_repository import JobSearchRepository
from app.job_title_cleanup import RegexJobTitleCleaner
from app.main import app

C_TITLE_CASES = (
    ("Developer (m/w/d)", "Developer"),
    ("Developer (m/w/d) Python", "Developer Python"),
    ("(m/w/d) Developer", "Developer"),
    ("Developer m/w/d Python", "Developer Python"),
    ("Developer (f/m/d) Python", "Developer Python"),
    ("Developer f/m/d", "Developer"),
    ("Developer (all genders)", "Developer"),
    ("Developer (all genders) Python", "Developer Python"),
    ("Developer ( M / W / D )  Python", "Developer Python"),
    ("Developer ( F / M / D )", "Developer"),
    ("Developer (ALL   GENDERS)", "Developer"),
    ("Developer(m/w/d)Python", "Developer Python"),
    ("Developer (m/w/d) (f/m/d) (all genders)", "Developer"),
    ("Developer (Remote)", "Developer (Remote)"),
    ("Platform/w/data Developer", "Platform/w/data Developer"),
    ("Research for all genders", "Research for all genders"),
    ("  C++ / C# Developer  ", "  C++ / C# Developer  "),
    ("", ""),
)
C_CASE_PARAMETERS = ("original_title", "expected_title")
C_SOURCE_TITLE = "Developer (m/w/d) Python (all genders)"
C_REFRESHED_TITLE = "Developer (f/m/d) Python"
C_CLEAN_TITLE = "Developer Python"
C_TITLE_KEY = "job_title"
C_RAW_TITLE_KEY = "title"
C_RAW_DATA_KEY = "raw_data"
C_ID_KEY = "id"
C_ITEMS_KEY = "items"
C_SEARCH_KEY = "search"
C_PREFERENCE_ENDPOINT = "/api/job-search-preferences"
C_JOBS_ENDPOINT = "/api/available-jobs"
C_SITE = "indeed"
C_JOB_URL = "https://example.test/title-cleanup"
C_LEGACY_MIGRATION_COUNT = 6
C_FAILURE_MESSAGE = "Simulated failure after cleaning titles"
C_FAILURE_PARAMETER = "fail_before_commit"
C_FIRST_ITEM = 0


class TestJobTitleCleanup:
    """Cover marker boundaries and the database behavior visible to users."""

    @pytest.mark.parametrize(C_CASE_PARAMETERS, C_TITLE_CASES)
    def test_supported_markers_and_meaningful_text(self, original_title, expected_title):
        """Remove markers at every position while preserving unrelated title content."""
        cleaner = RegexJobTitleCleaner()
        assert cleaner.clean(original_title) == expected_title
        assert cleaner.clean(expected_title) == expected_title

    @staticmethod
    def create_posting(client, repository):
        """Persist a posting linked to a saved search through the normal save path."""
        preference = client.post(C_PREFERENCE_ENDPOINT, json={C_TITLE_KEY: C_CLEAN_TITLE}).json()
        posting = AvailableJobModel(
            site=C_SITE,
            job_url=C_JOB_URL,
            job_title=C_SOURCE_TITLE,
            raw_data=json.dumps({C_RAW_TITLE_KEY: C_SOURCE_TITLE}),
        )
        repository.save_jobs(preference[C_ID_KEY], [posting])
        return preference[C_ID_KEY], posting

    @staticmethod
    def read_posting(repository):
        """Read every stored field directly, bypassing listing serialization."""
        with repository.engine.begin() as connection:
            return dict(connection.execute(select(AvailableJobModel.__table__)).mappings().one())

    def test_inserts_and_refreshes_store_searchable_clean_titles(self):
        """Both insert and upsert must persist clean titles while retaining source JSON."""
        with TestClient(app) as client:
            repository = JobSearchRepository()
            try:
                preference_id, posting = self.create_posting(client, repository)
                assert self.read_posting(repository)[C_TITLE_KEY] == C_CLEAN_TITLE
                posting.job_title = C_REFRESHED_TITLE
                repository.save_jobs(preference_id, [posting])
                stored_posting = self.read_posting(repository)
                assert stored_posting[C_TITLE_KEY] == C_CLEAN_TITLE
                assert stored_posting[C_RAW_DATA_KEY] == posting.raw_data
                listing = client.get(C_JOBS_ENDPOINT, params={C_SEARCH_KEY: C_CLEAN_TITLE}).json()
                assert listing[C_ITEMS_KEY][C_FIRST_ITEM][C_TITLE_KEY] == C_CLEAN_TITLE
            finally:
                repository.close()

    @pytest.mark.parametrize(C_FAILURE_PARAMETER, (False, True))
    def test_existing_titles_migrate_atomically_and_repeatably(self, monkeypatch, fail_before_commit):
        """Backfill only titles, preserve links, and recover from a failed migration."""
        migrations = db_migrations.MIGRATIONS
        legacy_migrations = migrations[:C_LEGACY_MIGRATION_COUNT]
        cleanup_migration = migrations[C_LEGACY_MIGRATION_COUNT]
        monkeypatch.setattr(db_migrations, "MIGRATIONS", legacy_migrations)
        with TestClient(app) as client:
            repository = JobSearchRepository()
            try:
                self.create_posting(client, repository)
                with repository.engine.begin() as connection:
                    connection.execute(update(AvailableJobModel).values(job_title=C_SOURCE_TITLE))
                    original_links = connection.execute(select(JobSearchResultModel.__table__)).all()
                original_posting = self.read_posting(repository)

                def fail_after_cleanup(connection):
                    """Fail after title updates to verify rollback of both data and version."""
                    cleanup_migration.apply(connection)
                    raise RuntimeError(C_FAILURE_MESSAGE)

                if fail_before_commit:
                    failing_migration = Migration(
                        cleanup_migration.version, cleanup_migration.name, fail_after_cleanup,
                    )
                    monkeypatch.setattr(db_migrations, "MIGRATIONS", legacy_migrations + (failing_migration,))
                    with pytest.raises(RuntimeError, match=C_FAILURE_MESSAGE):
                        database.init_db()
                    assert self.read_posting(repository) == original_posting

                monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations)
                database.init_db()
                database.init_db()
                expected_posting = dict(original_posting)
                expected_posting[C_TITLE_KEY] = C_CLEAN_TITLE
                assert self.read_posting(repository) == expected_posting
                with repository.engine.begin() as connection:
                    assert connection.execute(select(JobSearchResultModel.__table__)).all() == original_links
            finally:
                repository.close()
