"""Offline service, ownership and transactional preference seam checks."""

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from unittest.mock import Mock

import pandas
import pytest
from sqlalchemy import event, insert, select, update

from app import database
from app.database_models import AvailableJobModel, JobSearchPreferenceModel, JobSearchResultModel
from app.job_search_adapter import BaseJobBoardCoordinator
from app.job_search_repository import BasePreferenceDeletionGuard, JobSearchRepository
from app.models import JobSearchInput
from app.services import job_search_dependencies
from app.services.job_search_dependencies import JobSearchServiceFactory
from app.services.job_search_errors import AllBoardsFailedError, PreferenceDeletedError, PreferenceNotFoundError
from app.services.job_search_service import JobSearchPreferenceService

C_FIRST_ID = 1
C_MISSING_ID = 999
C_ZERO = 0
C_ONE = 1
C_TWO = 2
C_TIMEOUT = 30
C_BARRIER_TIMEOUT = 5
C_USA = "USA"
C_GERMANY = "Germany"
C_TITLE = "Developer"
C_CHANGED_TITLE = "Changed criteria"
C_KEYWORD = "python"
C_RADIUS = 0
C_EMPTY = ""
C_INDEED = "indeed"
C_LINKEDIN = "linkedin"
C_GLASSDOOR = "glassdoor"
C_ZIP_RECRUITER = "zip_recruiter"
C_JOB_URL = "https://example.test/service-job"
C_DESCRIPTION = "Python services. Fluent in German."
C_WARNING = "Offline source warning"
C_PRIVATE_FAILURE = "secret internal failure"
C_COMPLETED = "completed"
C_FAILED = "failed"
C_PARTIAL = "partial"
C_STATUS = "status"
C_FETCHED = "fetched"
C_BOARDS = "boards"
C_TOTAL = "total"
C_CHECKOUT_EVENT = "checkout"
C_CHECKIN_EVENT = "checkin"
C_DISPOSE_EVENT = "engine_disposed"
C_FACTORY_ADAPTER = "JobSearchAdapter"
C_PHASE = "phase"
C_SUCCESS_PHASE = "success"
C_LOOKUP_PHASE = "lookup"
C_FETCH_PHASE = "fetch"
C_SAVE_PHASE = "save"
C_CALLBACK_PHASE = "callback"
C_BUILD_PHASE = "build"
C_FRAME_TITLE = "title"
C_FRAME_URL = "job_url"
C_FRAME_DESCRIPTION = "description"
C_SITE_NAME = "site_name"
C_SEARCH_TERM = "search_term"
C_PAGE_SIZE = 20
C_ENV_DATABASE = "APPLYKIT_DATABASE_PATH"
C_ENV_LOCKS = "APPLYKIT_LOCK_DIR"
C_ENV_LOGS = "APPLYKIT_SCHEDULER_LOG_DIR"
C_DATABASE_NAME = "child.db"
C_LOCKS_NAME = "locks"
C_LOGS_NAME = "logs"
C_CHILD_ARGUMENT = "-c"
C_DATA_DIRECTORY = "DATA_DIR"
C_SAVE_METHOD = "save_job"
C_CLOSE_METHOD = "close"
C_ROOT = Path(__file__).resolve().parents[C_ONE]
C_IMPORT_PROBE = '''
import importlib.abc
import os
from pathlib import Path
import sys
C_REQUIRED = ("APPLYKIT_DATABASE_PATH", "APPLYKIT_LOCK_DIR", "APPLYKIT_SCHEDULER_LOG_DIR")
assert all(os.environ.get(name) for name in C_REQUIRED)
C_BLOCKED = ("app.main", "app.job_search", "fastapi")
class RejectTransportImports(importlib.abc.MetaPathFinder):
    """Reject routes or FastAPI even when introduced through indirect imports."""
    def find_spec(self, fullname, path=None, target=None):
        """Fail closed when reusable fetching reaches a transport module."""
        assert fullname not in C_BLOCKED, fullname
        return None
sys.meta_path.insert(0, RejectTransportImports())
from app import database
database.DB_PATH = Path(os.environ[C_REQUIRED[0]])
database.DATA_DIR = database.DB_PATH.parent
from app.services.job_search_dependencies import JobSearchServiceFactory
from app.database_models import JobSearchPreferenceModel
from app.models import JobSearchInput
from sqlalchemy import insert
import pandas
assert not database.DB_PATH.exists()
database.init_db()
class OfflineScraper:
    """Supply an empty board without loading a real scraper."""
    def __call__(self, **arguments):
        """Return an empty successful frame."""
        return pandas.DataFrame()
with JobSearchServiceFactory(scraper=OfflineScraper()).create() as service:
    with service.repository.engine.begin() as connection:
        connection.execute(insert(JobSearchPreferenceModel).values(
            id=1, job_title="Offline", country="", city="", radius_km=0,
            keywords=[], posted_within_days=None))
    assert service.search(JobSearchInput(preference_id=1, sites=["linkedin"]))["fetched"] == 0
assert all(name not in sys.modules for name in C_BLOCKED)
'''


class OfflineScraper:
    """Return deterministic postings and record effective adapter arguments."""

    def __init__(self, empty=False, barrier=None):
        """Optionally provide zero matches or synchronize concurrent boards."""
        self.empty = empty
        self.barrier = barrier
        self.calls = []

    def __call__(self, **arguments):
        """Return local data without any network access."""
        self.calls.append(deepcopy(arguments))
        if self.barrier is not None:
            self.barrier.wait()
        if self.empty:
            return pandas.DataFrame()
        return pandas.DataFrame([{
            C_FRAME_TITLE: C_TITLE, C_FRAME_URL: C_JOB_URL, C_FRAME_DESCRIPTION: C_DESCRIPTION,
        }])


class OfflineCoordinator(BaseJobBoardCoordinator):
    """Inject board failures or partial data at the proposed coordination seam."""

    def __init__(self, failed_sites=(), warning_sites=()):
        """Select simulated failures without touching the global Glassdoor guard."""
        self.failed_sites = failed_sites
        self.warning_sites = warning_sites

    def search(self, scraper, arguments):
        """Reject selected boards and retain successful data with optional warnings."""
        site = arguments[C_SITE_NAME][C_ZERO]
        if site in self.failed_sites:
            raise RuntimeError(C_PRIVATE_FAILURE)
        return scraper(**arguments), C_WARNING if site in self.warning_sites else None


class VetoDeletionGuard(BasePreferenceDeletionGuard):
    """Modify criteria before vetoing to verify that policy work also rolls back."""

    def validate_deletion(self, connection, preference_id):
        """Use the already-locked transaction and reject deletion."""
        assert connection.in_transaction()
        connection.execute(update(JobSearchPreferenceModel).where(
            JobSearchPreferenceModel.id == preference_id,
        ).values(job_title=C_CHANGED_TITLE))
        raise ValueError(C_WARNING)


@pytest.fixture
def service_repository(tmp_path, monkeypatch):
    """Migrate a temporary database and dispose its engine at fixture teardown."""
    monkeypatch.setattr(database, C_DATA_DIRECTORY, tmp_path)
    database.init_db()
    repository = JobSearchRepository()
    with repository.engine.begin() as connection:
        connection.execute(insert(JobSearchPreferenceModel).values(
            id=C_FIRST_ID, job_title=C_TITLE, country=C_USA, city=C_EMPTY,
            radius_km=C_RADIUS, keywords=[C_KEYWORD], posted_within_days=None,
        ))
    try:
        yield repository
    finally:
        repository.close()


class TestJobSearchService:
    """Exercise transport-independent fetching against local data only."""

    def test_standalone_fetch_never_imports_routes(self, tmp_path):
        """Run a real empty fetch in a fresh interpreter that rejects web imports."""
        environment = dict(os.environ)
        environment[C_ENV_DATABASE] = str(tmp_path / C_DATABASE_NAME)
        environment[C_ENV_LOCKS] = str(tmp_path / C_LOCKS_NAME)
        environment[C_ENV_LOGS] = str(tmp_path / C_LOGS_NAME)
        result = subprocess.run(
            [sys.executable, C_CHILD_ARGUMENT, C_IMPORT_PROBE], cwd=C_ROOT,
            env=environment, capture_output=True, text=True, timeout=C_TIMEOUT,
        )
        assert result.returncode == C_ZERO, result.stderr

    def test_parallel_boards_and_detached_snapshot(self, service_repository):
        """Capture criteria before concurrent scraping; snapshot mutations cannot affect it."""
        scraper = OfflineScraper(barrier=Barrier(C_TWO, timeout=C_BARRIER_TIMEOUT))
        snapshots = []

        def capture(preference):
            """Mutate the callback's copy to verify isolation of effective criteria."""
            assert not scraper.calls
            snapshots.append(deepcopy(preference))
            preference.job_title = C_CHANGED_TITLE
            preference.keywords.clear()

        with JobSearchServiceFactory(scraper).create(service_repository) as service:
            outcome = service.fetch(JobSearchInput(
                preference_id=C_FIRST_ID, sites=[C_INDEED, C_LINKEDIN],
            ), on_preference=capture)
        assert outcome.to_response()[C_FETCHED] == C_TWO
        assert snapshots[C_ZERO].keywords == [C_KEYWORD]
        assert all(call[C_SEARCH_TERM] == C_TITLE for call in scraper.calls)
        assert service_repository.list_jobs(C_ONE, C_PAGE_SIZE, C_FIRST_ID, None, C_EMPTY)[C_TOTAL] == C_TWO

    def test_zero_matches_is_success(self, service_repository):
        """An empty completed board must not be mistaken for a failed board."""
        with JobSearchServiceFactory(OfflineScraper(empty=True)).create(service_repository) as service:
            response = service.search(JobSearchInput(preference_id=C_FIRST_ID, sites=[C_INDEED]))
        assert response[C_FETCHED] == C_ZERO
        assert response[C_BOARDS][C_INDEED][C_STATUS] == C_COMPLETED

    def test_partial_success_persists_with_injected_coordinator(self, service_repository):
        """Persist completed/partial boards and sanitize unexpected board errors."""
        coordinator = OfflineCoordinator(failed_sites=[C_INDEED], warning_sites=[C_GLASSDOOR])
        scraper = OfflineScraper()
        with JobSearchServiceFactory(scraper, coordinator).create(service_repository) as service:
            response = service.search(JobSearchInput(
                preference_id=C_FIRST_ID, sites=[C_INDEED, C_GLASSDOOR, C_LINKEDIN],
            ))
        assert response[C_FETCHED] == C_TWO
        assert response[C_BOARDS][C_INDEED][C_STATUS] == C_FAILED
        assert response[C_BOARDS][C_GLASSDOOR][C_STATUS] == C_PARTIAL
        assert C_PRIVATE_FAILURE not in str(response)
        assert len(scraper.calls) == C_TWO
        assert service_repository.list_jobs(C_ONE, C_PAGE_SIZE, None, None, C_EMPTY)[C_TOTAL] == C_TWO

    def test_all_boards_failure_is_domain_error(self, service_repository):
        """Expose per-board diagnostics without HTTP exceptions or persistence."""
        scraper = OfflineScraper()
        coordinator = OfflineCoordinator(failed_sites=[C_INDEED])
        with JobSearchServiceFactory(scraper, coordinator).create(service_repository) as service:
            with pytest.raises(AllBoardsFailedError) as failure:
                service.search(JobSearchInput(preference_id=C_FIRST_ID, sites=[C_INDEED]))
        assert failure.value.boards[C_INDEED][C_STATUS] == C_FAILED
        assert len(failure.value.warnings) == C_ONE
        assert not scraper.calls
        assert C_PRIVATE_FAILURE not in str(failure.value.warnings)

    def test_deleted_preference_rejects_persistence(self, service_repository):
        """Deletion after snapshot capture prevents both job and link writes."""
        def delete_preference(preference):
            """Simulate deletion before the scrape result is saved."""
            service_repository.delete_preference(preference.id)

        with JobSearchServiceFactory(OfflineScraper()).create(service_repository) as service:
            with pytest.raises(PreferenceDeletedError):
                service.fetch(JobSearchInput(preference_id=C_FIRST_ID, sites=[C_INDEED]), delete_preference)
        assert service_repository.list_jobs(C_ONE, C_PAGE_SIZE, None, None, C_EMPTY)[C_TOTAL] == C_ZERO


class TestJobSearchOwnership:
    """Cover deterministic cleanup for owned and borrowed collaborators."""

    @pytest.mark.parametrize(C_PHASE, [
        C_SUCCESS_PHASE, C_LOOKUP_PHASE, C_FETCH_PHASE, C_SAVE_PHASE, C_CALLBACK_PHASE, C_BUILD_PHASE,
    ])
    def test_owned_engine_disposed_on_every_exit(self, service_repository, monkeypatch, phase):
        """Return connections and dispose owned engines on construction, fetch and storage failures."""
        checkout = Mock()
        checkin = Mock()
        disposed = Mock()
        event.listen(service_repository.engine, C_CHECKOUT_EVENT, checkout)
        event.listen(service_repository.engine, C_CHECKIN_EVENT, checkin)
        event.listen(service_repository.engine, C_DISPOSE_EVENT, disposed)
        scraper = OfflineScraper()
        coordinator = OfflineCoordinator(failed_sites=[C_INDEED] if phase == C_FETCH_PHASE else ())
        callback = None
        preference_id = C_MISSING_ID if phase == C_LOOKUP_PHASE else C_FIRST_ID
        if phase == C_SAVE_PHASE:
            monkeypatch.setattr(service_repository, C_SAVE_METHOD, Mock(side_effect=RuntimeError(C_WARNING)))
        if phase == C_CALLBACK_PHASE:
            callback = Mock(side_effect=RuntimeError(C_WARNING))
        if phase == C_BUILD_PHASE:
            monkeypatch.setattr(job_search_dependencies, C_FACTORY_ADAPTER, Mock(side_effect=RuntimeError(C_WARNING)))
        repository_factory = Mock(return_value=service_repository)
        factory = JobSearchServiceFactory(scraper, coordinator, repository_factory)

        def fetch_owned():
            """Enter the factory before exercising the selected failure boundary."""
            with factory.create() as service:
                service.fetch(JobSearchInput(preference_id=preference_id, sites=[C_INDEED]), callback)

        if phase == C_SUCCESS_PHASE:
            fetch_owned()
        else:
            with pytest.raises((RuntimeError, AllBoardsFailedError, PreferenceNotFoundError)):
                fetch_owned()
        assert disposed.call_count == C_ONE
        assert checkout.call_count == checkin.call_count
        if phase in (C_LOOKUP_PHASE, C_CALLBACK_PHASE, C_BUILD_PHASE):
            assert not scraper.calls
        if phase == C_SAVE_PHASE:
            assert service_repository.list_jobs(C_ONE, C_PAGE_SIZE, None, None, C_EMPTY)[C_TOTAL] == C_ZERO

    def test_borrowed_repository_remains_open(self, service_repository, monkeypatch):
        """An injected repository belongs to its caller even when searching fails."""
        close = Mock()
        monkeypatch.setattr(service_repository, C_CLOSE_METHOD, close)
        with JobSearchServiceFactory(OfflineScraper()).create(service_repository) as service:
            with pytest.raises(PreferenceNotFoundError):
                service.search(JobSearchInput(preference_id=C_MISSING_ID, sites=[C_INDEED]))
        close.assert_not_called()
        service_repository.engine.dispose()


class TestPreferenceServiceSeams:
    """Verify offline board validation and deletion policy transaction boundaries."""

    def test_location_validation_reuses_existing_rules(self, service_repository):
        """Reject incompatible boards using the existing offline country catalog."""
        with service_repository.engine.begin() as connection:
            connection.execute(update(JobSearchPreferenceModel).values(country=C_GERMANY))
        service = JobSearchPreferenceService(service_repository)
        assert service.validate_search(JobSearchInput(
            preference_id=C_FIRST_ID, sites=[C_GLASSDOOR, C_INDEED],
        )).country == C_GERMANY
        with pytest.raises(ValueError):
            service.validate_search(JobSearchInput(preference_id=C_FIRST_ID, sites=[C_ZIP_RECRUITER]))
        with pytest.raises(PreferenceNotFoundError):
            service.get_preference(C_MISSING_ID)

    def test_guard_rollback_and_existing_deletion_cascade(self, service_repository):
        """Roll back rejected policy writes; allowed deletion retains jobs and removes links."""
        service = JobSearchPreferenceService(service_repository)
        service_repository.save_jobs(C_FIRST_ID, [AvailableJobModel(
            site=C_INDEED, job_url=C_JOB_URL, job_title=C_TITLE,
        )])
        with pytest.raises(ValueError, match=C_WARNING):
            service.delete_preference(C_FIRST_ID, VetoDeletionGuard())
        assert service.get_preference(C_FIRST_ID).job_title == C_TITLE
        service.delete_preference(C_FIRST_ID)
        with pytest.raises(PreferenceNotFoundError):
            service.delete_preference(C_FIRST_ID)
        with service_repository.engine.begin() as connection:
            assert connection.execute(select(JobSearchResultModel)).first() is None
            assert connection.execute(select(AvailableJobModel)).first() is not None
