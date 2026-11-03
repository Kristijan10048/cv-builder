"""Bounded cross-process acceptance using only explicit disposable paths and fake boards."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
from time import monotonic, sleep

import httpx
import pytest
from sqlalchemy import insert, select

from app import database
from app.database_models import AvailableJobModel, JobSearchPreferenceModel
from app.scheduler.contracts import CreateScheduleRequest, RunNowRequest, ReplaceScheduleRequest, TaskResult
from app.scheduler.database_models import TaskRunModel
from app.scheduler.repository import ScheduleRepository
from app.scheduler.triggers import SystemClock

C_TIMEOUT = 20
C_POLL_SECONDS = 0.05
C_ROOT = Path(__file__).resolve().parents[2]
C_CHILD_MODULE = "tests.scheduler_integration.worker"
C_ENV_ROOT = "CV_BUILDER_TEST_ROOT"
C_MODE = "CV_BUILDER_TEST_MODE"
C_STOP = "stop"


class ProcessHarness:
    """Own only explicitly created subprocesses and disposable paths."""

    def __init__(self, root, monkeypatch):
        """Create a marked root and propagate isolation to every child before imports."""
        self.root = root
        root.mkdir(parents=True)
        (root / "scheduler-test-root").write_text("disposable")
        self.environment = dict(os.environ)
        settings = {
            C_ENV_ROOT: str(root), "CV_BUILDER_DATABASE_PATH": str(root / "database.db"),
            "CV_BUILDER_LOCK_DIR": str(root / "locks"), "CV_BUILDER_SCHEDULER_LOG_DIR": str(root / "worker-logs"),
            "CV_BUILDER_LOG_DIR": str(root / "web-logs"), "CV_BUILDER_SCHEDULER_POLL_SECONDS": "1",
        }
        self.environment.update(settings)
        for key, value in settings.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(database, "DB_PATH", root / "database.db")
        self.processes = []

    def start(self, mode="worker", **settings):
        """Start a hidden child with bounded output and retained ownership for cleanup."""
        environment = {**self.environment, C_MODE: mode, **settings}
        process = subprocess.Popen([sys.executable, "-m", C_CHILD_MODULE], cwd=C_ROOT,
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.processes.append(process)
        return process

    def stop(self, process):
        """Request graceful drain and wait before terminating only the owned child."""
        (self.root / C_STOP).write_text("stop")
        try:
            return process.communicate(timeout=C_TIMEOUT)
        finally:
            (self.root / C_STOP).unlink(missing_ok=True)

    def close(self):
        """Kill only still-running subprocesses created by this test harness."""
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=C_TIMEOUT)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Isolate each scenario including whitespace-containing Windows paths."""
    instance = ProcessHarness(tmp_path / "scheduler with spaces", monkeypatch)
    yield instance
    instance.close()


def wait_for(predicate, process=None):
    """Use a bounded readiness deadline and surface child failures immediately."""
    deadline = monotonic() + C_TIMEOUT
    while monotonic() < deadline:
        if predicate():
            return
        if process is not None and process.poll() is not None:
            output, errors = process.communicate(timeout=C_TIMEOUT)
            pytest.fail(f"Child exited {process.returncode}: {output!r} {errors!r}")
        sleep(C_POLL_SECONDS)
    pytest.fail("Timed out waiting for disposable child readiness.")


def seed():
    """Create a real schedule and manual receipt without using the web application."""
    database.init_db()
    repository = ScheduleRepository()
    with repository.transaction(True) as connection:
        connection.execute(insert(JobSearchPreferenceModel).values(id=1, job_title="Developer", country="Germany",
                                                                  city="Berlin", radius_km=0, keywords=[], posted_within_days=None))
    now = datetime.now(timezone.utc)
    request = CreateScheduleRequest(name="Offline process search", task_type="fetch_jobs", payload_version=1,
                                    payload={"preference_id": 1, "sites": ["linkedin"]},
                                    trigger={"kind": "interval", "seconds": 600, "starts_at": now + timedelta(hours=1)})
    schedule = repository.create(request, now)
    run, duplicate = repository.request_manual(schedule.id, RunNowRequest(revision=1, idempotency_key="process-run"), now)
    return repository, schedule, run


def test_worker_fetches_without_web_rejects_duplicate_and_web_reads_results(harness):
    """Prove independent persistence, singleton exclusion, graceful stop and real HTTP visibility."""
    repository, schedule, run = seed()
    try:
        process = harness.start()
        wait_for(lambda: repository.get_run(run.id).state == "succeeded", process)
        duplicate = harness.start()
        output, errors = duplicate.communicate(timeout=C_TIMEOUT)
        assert duplicate.returncode != 0
        assert b"AlreadyLocked" in errors or b"LockException" in errors
        harness.stop(process)
        assert process.returncode == 0
        assert repository.worker_status(SystemClock().now()).state == "stopped"
        restarted = harness.start()
        wait_for(lambda: repository.worker_status(SystemClock().now()).state == "fresh", restarted)
        assert repository.get_run(run.id).state == "succeeded"
        harness.stop(restarted)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        web = harness.start("web", CV_BUILDER_TEST_PORT=str(port))
        base = f"http://127.0.0.1:{port}"

        def web_ready():
            """Wait only for this test's HTTP server, ignoring initial connection refusal."""
            try:
                return httpx.get(base + "/api/scheduler/status", timeout=1).status_code == 200
            except httpx.HTTPError:
                return False

        wait_for(web_ready, web)
        assert httpx.get(base + "/api/available-jobs").json()["total"] == 1
        assert httpx.get(base + f"/api/task-schedules/{schedule.id}/runs").json()["items"][0]["state"] == "succeeded"
        assert "scheduled_tasks.js" in httpx.get(base).text
        harness.stop(web)
        assert web.returncode == 0
    finally:
        repository.close()


def test_crash_after_job_persistence_recovers_without_replay(harness):
    """The uncertain commit window keeps saved jobs and records interrupted instead of retrying."""
    repository, schedule, run = seed()
    try:
        crashed = harness.start("crash")
        crashed.communicate(timeout=C_TIMEOUT)
        assert crashed.returncode == 23
        assert repository.get_run(run.id).state == "running"
        restarted = harness.start()
        wait_for(lambda: repository.get_run(run.id).state == "interrupted", restarted)
        harness.stop(restarted)
        with repository.transaction() as connection:
            assert len(connection.execute(select(AvailableJobModel.id)).all()) == 1
        assert repository.list_queued_manual(SystemClock().now(), 100) == []
    finally:
        repository.close()


def test_simultaneous_migration_and_board_process_exclusion(harness):
    """Independent startup serializes schema upgrades and OS locks release after process death."""
    processes = [harness.start("migrate"), harness.start("migrate")]
    for process in processes:
        output, errors = process.communicate(timeout=C_TIMEOUT)
        assert process.returncode == 0, errors
    from app.database_locking import DatabaseLock, configuration_for_database
    import portalocker

    holder = harness.start("board")
    wait_for(lambda: (harness.root / "ready").exists(), holder)
    configuration = configuration_for_database(database.DB_PATH)
    with pytest.raises(portalocker.exceptions.LockException):
        with DatabaseLock(configuration, "board-glassdoor"):
            pytest.fail("Board lock was not exclusive.")
    holder.kill()
    holder.communicate(timeout=C_TIMEOUT)
    with DatabaseLock(configuration, "board-glassdoor"):
        pass


def test_child_refuses_unisolated_database(harness):
    """Missing explicit isolation fails before importing application modules."""
    process = harness.start("migrate", CV_BUILDER_DATABASE_PATH="")
    output, errors = process.communicate(timeout=C_TIMEOUT)
    assert process.returncode != 0
    assert b"Every child path" in errors


def test_two_processes_cannot_duplicate_a_timed_claim(harness):
    """The SQL occurrence key and serialized due advance protect independent dispatchers."""
    repository, schedule, run = seed()
    try:
        now = SystemClock().now()
        repository.claim_manual(run.id, "test-owner", now)
        repository.start_run(run.id, "test-owner", now)
        repository.complete(run.id, "test-owner", TaskResult(state="succeeded"), now)
        definition = schedule.model_dump(include={"name", "task_type", "payload_version", "payload", "trigger"})
        anchor = now + timedelta(seconds=1)
        definition["trigger"] = {"kind": "once", "run_at": anchor}
        repository.replace(schedule.id, ReplaceScheduleRequest(**definition, revision=1), now)
        wait_for(lambda: SystemClock().now() >= anchor)
        processes = [harness.start("claim"), harness.start("claim")]
        for process in processes:
            output, errors = process.communicate(timeout=C_TIMEOUT)
            assert process.returncode == 0, errors
        with repository.transaction() as connection:
            timed = connection.execute(select(TaskRunModel.id).where(TaskRunModel.source == "timed")).all()
            assert len(timed) == 1
    finally:
        repository.close()


def test_worker_observes_persisted_board_cooldown_across_restarts(harness):
    """A cooldown recorded by manual-side storage prevents child-worker board calls."""
    repository, schedule, run = seed()
    try:
        now = SystemClock().now()
        repository.claim_manual(run.id, "test-owner", now)
        repository.start_run(run.id, "test-owner", now)
        repository.complete(run.id, "test-owner", TaskResult(state="succeeded"), now)
        definition = schedule.model_dump(include={"name", "task_type", "payload_version", "payload", "trigger"})
        definition["payload"]["sites"] = ["glassdoor"]
        schedule = repository.replace(schedule.id, ReplaceScheduleRequest(**definition, revision=1), now)
        deadline = now + timedelta(seconds=300)
        repository.extend_board_cooldown("glassdoor", deadline)
        for key in ("cooldown-first", "cooldown-after-restart"):
            queued, unused_duplicate = repository.request_manual(schedule.id, RunNowRequest(revision=2, idempotency_key=key), SystemClock().now())
            process = harness.start()
            wait_for(lambda: repository.get_run(queued.id).state == "failed", process)
            assert repository.get_run(queued.id).result.boards["glassdoor"].status == "cooldown"
            harness.stop(process)
            assert repository.get_board_cooldown("glassdoor") == deadline
    finally:
        repository.close()


def test_powershell_launcher_validates_spaces_and_rejects_invalid_configuration(harness):
    """Exercise the actual operator launcher without starting production searches."""
    if os.name != "nt":
        pytest.skip("Windows launcher acceptance requires Windows.")
    shell = shutil.which("pwsh") or "powershell.exe"
    command = [shell, "-NoProfile", "-File", str(C_ROOT / "scripts" / "Start-Scheduler.ps1"),
               "-DatabasePath", str(harness.root / "database.db"), "-LockDirectory", str(harness.root / "locks"),
               "-LogDirectory", str(harness.root / "worker-logs"), "-ValidateOnly"]
    result = subprocess.run(command, env=harness.environment, capture_output=True, timeout=C_TIMEOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert b"configuration and imports OK" in result.stdout
    result = subprocess.run(command, env={**harness.environment, "CV_BUILDER_SCHEDULER_MAX_WORKERS": "invalid"},
                            capture_output=True, timeout=C_TIMEOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode != 0
