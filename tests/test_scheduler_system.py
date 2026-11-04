"""Offline integration of real scheduler storage, API, dispatch, and fetch handlers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from dataclasses import replace
import logging

import pandas
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app import database
from app.database_models import JobSearchPreferenceModel
from app.database_locking import DatabaseLock, configuration_for_database
from app.main import app
from app.scheduler import constants as scheduler_constants
from app.scheduler.contracts import (
    BaseClock, BaseTaskHandler, CreateScheduleRequest, PaginationRequest, ReplaceScheduleRequest,
    RunNowRequest, TaskResult, WorkerRegistration, ScheduleRecord, RunNowResponse, Page, RunRecord,
)
from app.scheduler.database_models import TaskRunModel, TaskScheduleModel
from app.scheduler.dispatcher import Dispatcher
from app.scheduler.errors import SchedulerError
from app.scheduler.executor import TaskExecutor
from app.scheduler.handlers.fetch_jobs import FetchJobsTaskHandler
from app.scheduler.logging_setup import WorkerLogging
from app.scheduler.registry import TaskRegistry
from app.scheduler.repository import ScheduleRepository, SchedulePreferenceDeletionGuard
from app.scheduler.triggers import TriggerCalculator
from app.services.job_board_coordinator import SharedJobBoardCoordinator
from app.services.job_search_dependencies import JobSearchServiceFactory
from app.services.job_search_errors import BoardUnavailableError
from app.job_search_repository import JobSearchRepository

C_NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
C_OWNER = "worker-one"
C_OTHER_OWNER = "worker-two"
C_TITLE = "Developer"
C_COUNTRY = "Germany"
C_SITE = "linkedin"
C_GLASSDOOR = "glassdoor"
C_SECONDS = 600
C_TIMEOUT = 10


class MutableClock(BaseClock):
    """Advance deterministic UTC time without sleeping for scheduler intervals."""

    def __init__(self, now=C_NOW):
        """Start at a future frozen instant shared by definitions and assertions."""
        self.instant = now

    def now(self):
        """Return the test-controlled instant."""
        return self.instant


class SuccessfulHandler(BaseTaskHandler):
    """Record invocations without contacting any external service."""

    def __init__(self):
        """Create an isolated invocation list."""
        self.runs = []

    def execute(self, run, repository, clock):
        """Return an empty success, which must still count as a successful run."""
        self.runs.append(run.id)
        return TaskResult(state="succeeded")


@pytest.fixture
def repository():
    """Migrate a disposable DB and seed one mapped preference."""
    database.init_db()
    storage = ScheduleRepository()
    with storage.transaction(True) as connection:
        connection.execute(insert(JobSearchPreferenceModel).values(
            id=1, job_title=C_TITLE, country=C_COUNTRY, city="Berlin", radius_km=0,
            keywords=[], posted_within_days=None,
        ))
    yield storage
    storage.close()


def definition(kind="interval", anchor=None, sites=None):
    """Build a supported schedule using a future explicit UTC anchor."""
    anchor = anchor or C_NOW + timedelta(seconds=C_SECONDS)
    trigger = {"kind": kind, "seconds": C_SECONDS, "starts_at": anchor} if kind == "interval" else {"kind": kind, "run_at": anchor}
    return CreateScheduleRequest.model_validate({
        "name": "My search", "task_type": "fetch_jobs", "payload_version": 1,
        "payload": {"preference_id": 1, "sites": sites or [C_SITE], "results_wanted": 50},
        "trigger": trigger,
    }, context={"now": C_NOW})


def manual(repository, schedule, key="request-one", now=C_NOW):
    """Accept one durable manual request with the schedule's current revision."""
    return repository.request_manual(schedule.id, RunNowRequest(revision=schedule.revision, idempotency_key=key), now)[0]


def start_manual(repository, schedule, now=C_NOW):
    """Claim and start a manual run through both ownership boundaries."""
    run = manual(repository, schedule, now=now)
    repository.claim_manual(run.id, C_OWNER, now)
    return repository.start_run(run.id, C_OWNER, now)


def worker(token=C_OWNER):
    """Construct registration metadata without treating it as lock ownership."""
    return WorkerRegistration(owner_token=token, process_id=1, hostname="offline-test", started_at=C_NOW)


def test_repository_crud_revision_and_future_anchor(repository):
    """Preserve recurrence for name edits, advance resumes, and reject competing stale writes."""
    schedule = repository.create(definition(), C_NOW)
    replacement = ReplaceScheduleRequest(**definition().model_dump(), revision=1)
    replacement.name = "Edited"
    updated = repository.replace(schedule.id, replacement, C_NOW + timedelta(seconds=800))
    assert updated.next_run_at == schedule.next_run_at
    with pytest.raises(SchedulerError, match="changed"):
        repository.replace(schedule.id, replacement, C_NOW)
    paused = repository.set_enabled(schedule.id, updated.revision, False, C_NOW)
    assert paused.next_run_at is None
    resumed = repository.set_enabled(schedule.id, paused.revision, True, C_NOW + timedelta(seconds=1800))
    assert resumed.next_run_at == C_NOW + timedelta(seconds=2400)
    assert repository.set_enabled(schedule.id, resumed.revision, True, C_NOW).next_run_at == resumed.next_run_at


def test_manual_dedupe_snapshots_and_preference_deletion(repository):
    """Retained keys survive edits, snapshots are detached and tombstones release live references."""
    schedule = repository.create(definition(), C_NOW)
    run = manual(repository, schedule)
    run.claim_snapshot.payload.sites.append("indeed")
    assert repository.get_run(run.id).claim_snapshot.payload.sites == [C_SITE]
    paused = repository.set_enabled(schedule.id, 1, False, C_NOW)
    duplicate, deduplicated = repository.request_manual(schedule.id, RunNowRequest(revision=1, idempotency_key="request-one"), C_NOW)
    assert deduplicated and duplicate.id == run.id
    with pytest.raises(SchedulerError) as error:
        manual(repository, paused)
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(SchedulerError) as error:
        manual(repository, paused, "other")
    assert error.value.code == "active_run_conflict"
    search_repository = JobSearchRepository()
    try:
        with pytest.raises(SchedulerError) as error:
            search_repository.delete_preference(1, SchedulePreferenceDeletionGuard())
        assert error.value.schedule_ids == (schedule.id,)
        repository.tombstone(schedule.id, paused.revision, C_NOW)
        search_repository.delete_preference(1, SchedulePreferenceDeletionGuard())
        assert repository.list_runs(schedule.id, PaginationRequest()).total == 1
    finally:
        search_repository.close()


@pytest.mark.parametrize("operation", ["pause", "replace", "delete"])
def test_final_start_gate_cancels_invalidated_claim(repository, operation):
    """An edit between claim and invocation must prevent scraper execution."""
    schedule = repository.create(definition(), C_NOW)
    run = manual(repository, schedule)
    repository.claim_manual(run.id, C_OWNER, C_NOW)
    if operation == "pause":
        repository.set_enabled(schedule.id, 1, False, C_NOW)
    elif operation == "replace":
        repository.replace(schedule.id, ReplaceScheduleRequest(**definition().model_dump(), revision=1), C_NOW)
    else:
        repository.tombstone(schedule.id, 1, C_NOW)
    assert repository.start_run(run.id, C_OWNER, C_NOW).state == "cancelled"


def test_pause_does_not_cancel_running_work_and_manual_once_not_consumed(repository):
    """Already-running manual work finishes despite pause and does not consume a one-shot."""
    schedule = repository.create(definition("once"), C_NOW)
    run = start_manual(repository, schedule)
    paused = repository.set_enabled(schedule.id, 1, False, C_NOW)
    result = TaskResult(state="succeeded")
    finished = repository.complete(run.id, C_OWNER, result, C_NOW)
    assert repository.complete(run.id, C_OWNER, result, C_NOW) == finished
    resumed = repository.set_enabled(schedule.id, paused.revision, True, C_NOW)
    assert resumed.next_run_at == schedule.next_run_at
    assert repository.get_run(run.id).state == "succeeded"


@pytest.mark.parametrize("elapsed,active,state,count", [(600, False, "queued", 0), (1800, False, "queued", 2), (2150, False, "missed", 3), (1800, True, "skipped_overlap", 3), (2150, True, "skipped_overlap", 3)])
def test_coalescing_lateness_and_overlap(repository, elapsed, active, state, count):
    """Coalesce around the original anchor with explicit active-overlap precedence."""
    schedule = repository.create(definition(), C_NOW)
    if active:
        start_manual(repository, schedule)
    schedule = repository.get(schedule.id)
    now = C_NOW + timedelta(seconds=elapsed)
    claim = TriggerCalculator.due(schedule, now)
    assert claim.disposition == state
    assert claim.skipped_count == count
    run = repository.claim_timed(claim, C_OWNER, now)
    assert run.state == state
    assert repository.claim_timed(claim, C_OWNER, now) is None
    assert repository.get(schedule.id).next_run_at > now


@pytest.mark.parametrize("expired", [False, True])
def test_once_completion_and_missed_disable(repository, expired):
    """A timed one-shot is consumed on completion or expiry, never retried."""
    schedule = repository.create(definition("once"), C_NOW)
    now = schedule.next_run_at + timedelta(seconds=301 if expired else 0)
    run = repository.claim_timed(TriggerCalculator.due(schedule, now), C_OWNER, now)
    if expired:
        assert run.state == "missed"
    else:
        repository.start_run(run.id, C_OWNER, now)
        repository.complete(run.id, C_OWNER, TaskResult(state="succeeded"), now)
    assert not repository.get(schedule.id).enabled


def test_once_edit_during_execution_survives_completion(repository):
    """Completing an old one-shot cannot disable a newly supplied future trigger."""
    schedule = repository.create(definition("once"), C_NOW)
    now = schedule.next_run_at
    run = repository.claim_timed(TriggerCalculator.due(schedule, now), C_OWNER, now)
    repository.start_run(run.id, C_OWNER, now)
    future = definition("once", now + timedelta(seconds=C_SECONDS))
    updated = repository.replace(schedule.id, ReplaceScheduleRequest(**future.model_dump(), revision=1), now)
    repository.complete(run.id, C_OWNER, TaskResult(state="succeeded"), now)
    assert repository.get(schedule.id).next_run_at == updated.next_run_at
    assert repository.get(schedule.id).enabled


def test_recovery_health_expiry_retention_and_fencing(repository):
    """Recover only owned work, preserve unowned queue, and never prune active rows."""
    first = repository.create(definition(), C_NOW)
    running = start_manual(repository, first)
    second = repository.create(definition(), C_NOW)
    queued = manual(repository, second)
    assert repository.recover(worker(C_OTHER_OWNER), C_NOW) == 1
    assert repository.get_run(running.id).state == "interrupted"
    assert repository.get_run(queued.id).state == "queued"
    with pytest.raises(SchedulerError):
        repository.complete(running.id, C_OWNER, TaskResult(state="succeeded"), C_NOW)
    assert repository.worker_status(C_NOW).state == "stale"
    repository.heartbeat(C_OTHER_OWNER, C_NOW)
    repository.heartbeat(C_OWNER, C_NOW + timedelta(seconds=30))
    assert repository.worker_status(C_NOW + timedelta(seconds=31)).state == "stale"
    assert repository.prune_terminal(C_NOW, 100) == 0
    assert repository.prune_terminal(C_NOW + timedelta(seconds=1), 100) == 1
    assert repository.expire_manual(C_NOW + timedelta(seconds=300), 100) == 1
    assert repository.get_run(queued.id).state == "missed"
    repository.stop_worker(C_OTHER_OWNER, C_NOW)
    assert repository.worker_status(C_NOW).state == "stopped"


def test_revision_and_manual_races_use_independent_connections(repository):
    """Exactly one edit wins while repeated keys return the same durable request."""
    schedule = repository.create(definition(), C_NOW)
    barrier = Barrier(2)

    def edit():
        """Race two connections after both threads are ready."""
        barrier.wait(timeout=C_TIMEOUT)
        try:
            return repository.set_enabled(schedule.id, 1, False, C_NOW).revision
        except SchedulerError as exception:
            return exception.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(edit) for unused in range(2)]
        assert set(future.result(timeout=C_TIMEOUT) for future in futures) == {2, "revision_conflict"}
    schedule = repository.get(schedule.id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(manual, repository, schedule) for unused in range(2)]
        assert len({future.result(timeout=C_TIMEOUT).id for future in futures}) == 1


def test_database_unique_active_index_cannot_be_bypassed(repository):
    """Direct insertion still cannot create two active rows for one schedule."""
    schedule = repository.create(definition(), C_NOW)
    manual(repository, schedule)
    with pytest.raises(SchedulerError) as error:
        with repository.transaction(True) as connection:
            record = dict(connection.execute(select(TaskRunModel.__table__)).mappings().one())
            record.pop("id")
            record["idempotency_key"] = "different-key"
            connection.execute(insert(TaskRunModel).values(**record))
    assert error.value.code == "storage_unavailable"


def test_dispatch_saturation_and_future_completion(repository):
    """Full capacity leaves timed work due and shutdown drains the bounded handler."""
    schedule = repository.create(definition(), C_NOW)
    clock = MutableClock(schedule.next_run_at)
    handler = SuccessfulHandler()
    registry = TaskRegistry()
    registry.register("fetch_jobs", 1, handler)
    executor = TaskExecutor(1)
    repository.recover(worker(), clock.now())
    dispatcher = Dispatcher(repository, registry, executor, clock, C_OWNER, 90)
    reservation = executor.reserve()
    try:
        dispatcher.dispatch()
        assert repository.get(schedule.id).next_run_at == schedule.next_run_at
        reservation.release()
        dispatcher.dispatch()
        executor.shutdown()
        executor.reconcile(repository, clock)
        assert len(handler.runs) == 1
        assert repository.get(schedule.id).latest_run.state == "succeeded"
    finally:
        reservation.release()
        executor.shutdown()


@pytest.mark.parametrize("mode,expected", [("success", "succeeded"), ("empty", "succeeded"), ("partial", "partial"), ("failure", "failed"), ("value_error", "failed")])
def test_fetch_handler_reuses_storage_and_captures_preference(repository, mode, expected):
    """Exercise real adapters/upserts and result mapping using synthetic boards only."""
    schedule = repository.create(definition(sites=[C_SITE, "indeed"]), C_NOW)
    run = start_manual(repository, schedule)

    def scrape(**arguments):
        """Return fixture postings or bounded failures without network access."""
        if mode == "value_error":
            raise ValueError("secret source details must never appear in results")
        if mode == "failure" or (mode == "partial" and arguments["site_name"] == ["indeed"]):
            raise RuntimeError("secret source details must never appear in results")
        if mode == "empty":
            return pandas.DataFrame([])
        return pandas.DataFrame([{"title": C_TITLE, "job_url": "https://example.test/job", "description": "Synthetic role"}])

    handler = FetchJobsTaskHandler(JobSearchServiceFactory(scraper=scrape))
    result = handler.execute(run, repository, MutableClock())
    repository.complete(run.id, C_OWNER, result, C_NOW)
    assert result.state == expected
    assert "secret source" not in result.model_dump_json()
    assert repository.get_run(run.id).effective_preference.job_title == C_TITLE
    if mode == "success":
        search_repository = JobSearchRepository()
        try:
            with JobSearchServiceFactory(scraper=scrape).create(search_repository) as service:
                service.fetch(schedule.payload)
            assert search_repository.list_jobs(1, 20, 1, None, "")["total"] == 2
        finally:
            search_repository.close()


def test_shared_board_busy_cooldown_and_exception_cleanup(repository):
    """Persist a 429 even if scraping raises, and release locks after exceptions."""
    configuration = configuration_for_database(database.DB_PATH)
    clock = MutableClock()
    coordinator = SharedJobBoardCoordinator(configuration, repository, clock)
    arguments = {"site_name": [C_GLASSDOOR]}
    with DatabaseLock(configuration, "board-glassdoor"):
        with pytest.raises(BoardUnavailableError) as error:
            coordinator.search(None, arguments)
        assert error.value.status == "busy"

    def failing_scraper(**arguments):
        """Mimic JobSpy swallowing/logging a rate limit before another failure."""
        logging.getLogger("jobspy.glassdoor").error("response status code 429")
        raise RuntimeError("transport failed")

    with pytest.raises(RuntimeError):
        coordinator.search(failing_scraper, arguments)
    with pytest.raises(BoardUnavailableError) as error:
        SharedJobBoardCoordinator(configuration, repository, clock).search(None, arguments)
    assert error.value.status == "cooldown"
    clock.instant += timedelta(seconds=301)
    assert coordinator.search(lambda **arguments: "frame", arguments) == ("frame", None)


def test_worker_log_is_separate_and_does_not_collect_service_payload(repository):
    """Only safe scheduler identifiers and outcomes reach the dedicated worker file."""
    configuration = configuration_for_database(database.DB_PATH)
    with WorkerLogging(configuration):
        logging.getLogger("app.job_search").error("PRIVATE SEARCH CRITERIA")
        logging.getLogger("app.scheduler.dispatcher").info("run_id=1 state=succeeded")
    content = configuration.log_path.read_text()
    assert "run_id=1" in content
    assert "PRIVATE" not in content


def test_api_end_to_end_offline_worker_and_tombstone_history(repository):
    """Exercise every route against executable response contracts without starting a worker."""
    with TestClient(app) as client:
        created = client.post("/api/task-schedules", json=definition().model_dump(mode="json"))
        assert created.status_code == 201, created.text
        schedule = ScheduleRecord.model_validate(created.json())
        path = f"/api/task-schedules/{schedule.id}"
        assert client.get(path).status_code == 200
        assert client.get("/api/task-schedules").json()["total"] == 1
        paused = client.post(path + "/pause", json={"revision": 1}).json()
        receipt = client.post(path + "/run-now", json={"revision": paused["revision"], "idempotency_key": "api-run"})
        assert receipt.status_code == 202, receipt.text
        result = RunNowResponse.model_validate(receipt.json())
        assert result.run.state == "queued" and result.worker.state == "stopped" and result.warning
        assert client.post(path + "/run-now", json={"revision": paused["revision"], "idempotency_key": "api-run"}).json()["deduplicated"]
        assert client.delete("/api/job-search-preferences/1").status_code == 409
        resumed = client.post(path + "/resume", json={"revision": paused["revision"]}).json()
        payload = definition().model_dump(mode="json")
        payload.update(name="Edited through HTTP", revision=resumed["revision"])
        edited = client.put(path, json=payload)
        assert edited.status_code == 200
        assert client.delete(path + f'?revision={edited.json()["revision"]}').status_code == 204
        assert client.get(path).status_code == 404
        assert Page[RunRecord].model_validate(client.get(path + "/runs").json()).total == 1
        assert client.delete("/api/job-search-preferences/1").status_code == 204
        assert client.get("/api/scheduler/status").json()["queued_count"] == 1


@pytest.mark.parametrize("path", ["/api/task-schedules?unknown=secret", "/api/task-schedules?page=0", "/api/task-schedules?page_size=101", "/api/task-schedules/0", "/api/task-schedules/x", "/api/scheduler/status?unknown=secret", "/api/task-schedules?page=1&page=2"])
def test_api_rejects_unknown_and_invalid_queries(repository, path):
    """Reject malformed URL fields with a safe uniform scheduler envelope."""
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert "secret" not in response.text


def test_api_stale_revision_and_strict_body(repository):
    """No coercion, rejected-value reflection, or scraper calls occur during management."""
    schedule = repository.create(definition(), C_NOW)
    with TestClient(app) as client:
        path = f"/api/task-schedules/{schedule.id}/pause"
        response = client.post(path, json={"revision": 99})
        assert response.status_code == 409
        assert response.json()["error"]["current_revision"] == 1
        for payload in ({"revision": True}, {"revision": "1"}, {"revision": 1, "SECRET": "PRIVATE"}):
            response = client.post(path, json=payload)
            assert response.status_code == 422
            assert "PRIVATE" not in response.text and "SECRET" not in response.text
        unsupported = definition().model_dump(mode="json")
        unsupported["task_type"] = "os.system"
        response = client.post("/api/task-schedules", json=unsupported)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unsupported_task"


def test_executor_rejection_and_failed_cancellation_are_reconciled(repository, monkeypatch):
    """A transient error while persisting submission failure cannot leak an active claim."""
    schedule = repository.create(definition(), C_NOW)
    clock = MutableClock(schedule.next_run_at)
    registry = TaskRegistry()
    registry.register("fetch_jobs", 1, SuccessfulHandler())
    executor = TaskExecutor(1)
    dispatcher = Dispatcher(repository, registry, executor, clock, C_OWNER, 90)
    original_cancel = repository.cancel_submission
    failures = []

    def reject(*arguments, **keywords):
        """Reject the executor submission before any task starts."""
        raise RuntimeError("executor unavailable")

    def unavailable_once(*arguments):
        """Fail the first terminal write, then permit the next pass to reconcile it."""
        if not failures:
            failures.append(True)
            raise SchedulerError("storage_unavailable", "temporary test contention")
        return original_cancel(*arguments)

    monkeypatch.setattr(executor.pool, "submit", reject)
    monkeypatch.setattr(repository, "cancel_submission", unavailable_once)
    try:
        with pytest.raises(SchedulerError):
            dispatcher.dispatch()
        assert repository.get(schedule.id).latest_run.state == "queued"
        dispatcher.dispatch()
        assert repository.get(schedule.id).latest_run.state == "cancelled"
        assert not dispatcher.pending_submissions
        reservation = executor.reserve()
        assert reservation is not None
        reservation.release()
    finally:
        executor.shutdown()


def test_dispatch_failure_stops_heartbeat_and_never_executes_corrupt_definition(repository):
    """Corrupt task data fails closed without importing a supplied path or refreshing health."""
    schedule = repository.create(definition(), C_NOW)
    clock = MutableClock(schedule.next_run_at)
    repository.recover(worker(), C_NOW)
    repository.heartbeat(C_OWNER, C_NOW)
    with repository.transaction(True) as connection:
        corrupted = schedule.model_dump(mode="json")
        corrupted["task_type"] = "os.system"
        connection.execute(update(TaskScheduleModel).where(TaskScheduleModel.id == schedule.id).values(record=corrupted))
    executor = TaskExecutor(1)
    try:
        Dispatcher(repository, TaskRegistry(), executor, clock, C_OWNER, 90).tick()
        assert repository.worker_status(clock.now()).state == "stale"
        with repository.transaction() as connection:
            assert connection.execute(select(TaskRunModel.id)).all() == []
    finally:
        executor.shutdown()


def test_create_versus_preference_delete_is_transactional(repository):
    """One of creation/deletion wins; no committed schedule can reference a missing search."""
    barrier = Barrier(2)

    def create():
        """Race schedule creation with a guarded preference delete."""
        barrier.wait(timeout=C_TIMEOUT)
        try:
            return repository.create(definition(), C_NOW)
        except SchedulerError as exception:
            return exception.code

    def delete_search():
        """Use an independent connection and the real transactional deletion guard."""
        search_repository = JobSearchRepository()
        try:
            barrier.wait(timeout=C_TIMEOUT)
            search_repository.delete_preference(1, SchedulePreferenceDeletionGuard())
            return "deleted"
        except SchedulerError as exception:
            return exception.code
        finally:
            search_repository.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = executor.submit(create)
        deleted = executor.submit(delete_search)
        creation_result = created.result(timeout=C_TIMEOUT)
        deletion_result = deleted.result(timeout=C_TIMEOUT)
    assert (creation_result == "preference_not_found" and deletion_result == "deleted") or (
        isinstance(creation_result, ScheduleRecord) and deletion_result == "preference_in_use")


def test_running_handler_handles_preference_removal_without_scraping(repository):
    """Deletion after tombstoning a running schedule becomes a safe terminal failure."""
    schedule = repository.create(definition(), C_NOW)
    run = start_manual(repository, schedule)
    repository.tombstone(schedule.id, schedule.revision, C_NOW)
    search_repository = JobSearchRepository()
    try:
        search_repository.delete_preference(1, SchedulePreferenceDeletionGuard())
    finally:
        search_repository.close()

    def no_scrape(**arguments):
        """Fail the test if missing-preference work attempts any board access."""
        pytest.fail("No scraping is permitted after preference removal.")

    result = FetchJobsTaskHandler(JobSearchServiceFactory(scraper=no_scrape)).execute(run, repository, MutableClock())
    assert result.state == "failed" and result.error.code == "preference_not_found"


def test_schedule_limit_and_database_contention(repository, monkeypatch):
    """Count caps are transactional and SQLite lock waits become safe retryable failures."""
    monkeypatch.setattr(scheduler_constants, "C_MAX_SCHEDULES", 1)
    repository.create(definition(), C_NOW)
    with pytest.raises(SchedulerError) as error:
        repository.create(definition(), C_NOW)
    assert error.value.code == "schedule_limit_reached"
    monkeypatch.setattr(scheduler_constants, "C_SQLITE_BUSY_TIMEOUT_SECONDS", 0.01)
    with repository.transaction(True):
        with pytest.raises(SchedulerError) as error:
            repository.set_enabled(1, 1, False, C_NOW)
        assert error.value.code == "storage_unavailable"


def test_disabled_registry_entry_finishes_as_unsupported_task(repository):
    """Removing a trusted handler produces a visible failure rather than executing any import path."""
    schedule = repository.create(definition(), C_NOW)
    clock = MutableClock(schedule.next_run_at)
    executor = TaskExecutor(1)
    try:
        Dispatcher(repository, TaskRegistry(), executor, clock, C_OWNER, 90).dispatch()
        executor.shutdown()
        executor.reconcile(repository, clock)
        latest = repository.get(schedule.id).latest_run
        assert latest.state == "failed"
        assert latest.result.error.code == "unsupported_task"
    finally:
        executor.shutdown()
