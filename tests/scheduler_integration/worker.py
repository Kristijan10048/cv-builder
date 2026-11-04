"""Disposable worker/web entry point with fail-closed environment isolation."""

import os
from pathlib import Path
import sys
from threading import Thread
from time import sleep

C_ENV_ROOT = "CV_BUILDER_TEST_ROOT"
C_ENV_MODE = "CV_BUILDER_TEST_MODE"
C_ENV_PORT = "CV_BUILDER_TEST_PORT"
C_REQUIRED_PATHS = ("CV_BUILDER_DATABASE_PATH", "CV_BUILDER_LOCK_DIR", "CV_BUILDER_SCHEDULER_LOG_DIR", "CV_BUILDER_LOG_DIR")
C_MARKER = "scheduler-test-root"
C_STOP_FILE = "stop"
C_MODE_WORKER = "worker"
C_MODE_WEB = "web"
C_MODE_MIGRATE = "migrate"
C_MODE_BOARD = "board"
C_MODE_CRASH = "crash"
C_MODE_CLAIM = "claim"
C_LOOP_SECONDS = 0.05
C_TEST_URL = "https://example.test/offline-job"


def validate_isolation():
    """Reject missing paths, default locations, and files outside the marked test root."""
    value = os.environ.get(C_ENV_ROOT)
    if not value:
        raise RuntimeError("A marked disposable test root is required.")
    root = Path(value).resolve()
    if not (root / C_MARKER).is_file():
        raise RuntimeError("Missing disposable-root marker.")
    for variable in C_REQUIRED_PATHS:
        setting = os.environ.get(variable)
        if not setting or root not in Path(setting).resolve().parents:
            raise RuntimeError("Every child path must stay inside the disposable root.")
    return root


def fake_scraper(**arguments):
    """Return deterministic synthetic postings through the real adapter and persistence."""
    import pandas

    return pandas.DataFrame([{"title": "Offline developer", "job_url": C_TEST_URL,
                              "description": "Synthetic fixture; never fetched from a board."}])


def main():
    """Launch only a test-selected mode after isolation checks and before app imports."""
    root = validate_isolation()
    from app import database
    from app.scheduler.configuration import SchedulerConfiguration

    mode = os.environ.get(C_ENV_MODE, C_MODE_WORKER)
    if mode == C_MODE_MIGRATE:
        database.init_db()
        return
    if mode == C_MODE_WEB:
        import uvicorn
        from app import job_search
        from app.main import app

        job_search.scrape_jobs = fake_scraper
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=int(os.environ[C_ENV_PORT]), log_level="error"))

        def stop_web():
            """Stop only this explicitly created server when its test marker is written."""
            while not (root / C_STOP_FILE).exists():
                sleep(C_LOOP_SECONDS)
            server.should_exit = True

        Thread(target=stop_web, daemon=True).start()
        server.run()
        return
    if mode == C_MODE_BOARD:
        from app.database_locking import DatabaseLock

        with DatabaseLock(SchedulerConfiguration.from_environment(), "board-glassdoor"):
            (root / "ready").write_text("ready")
            while not (root / C_STOP_FILE).exists():
                sleep(C_LOOP_SECONDS)
        return
    if mode == C_MODE_CLAIM:
        from app.scheduler.repository import ScheduleRepository
        from app.scheduler.triggers import TriggerCalculator, SystemClock

        repository = ScheduleRepository()
        try:
            now = SystemClock().now()
            for schedule in repository.list_due(now, 100):
                repository.claim_timed(TriggerCalculator.due(schedule, now), "race-worker", now)
        finally:
            repository.close()
        return
    from app.scheduler.handlers.fetch_jobs import FetchJobsTaskHandler
    from app.scheduler.runtime import SchedulerRuntime
    from app.services.job_search_dependencies import JobSearchServiceFactory

    class CrashAfterPersistenceHandler(FetchJobsTaskHandler):
        """Simulate process loss after postings commit but before completion is recorded."""

        def execute(self, run, repository, clock):
            """Exit only this disposable child after the real service has saved fixture jobs."""
            super().execute(run, repository, clock)
            os._exit(23)

    handler_class = CrashAfterPersistenceHandler if mode == C_MODE_CRASH else FetchJobsTaskHandler
    runtime = SchedulerRuntime(handler=handler_class(JobSearchServiceFactory(scraper=fake_scraper)))

    def stop_worker():
        """Use normal runtime shutdown after APScheduler has actually started."""
        while not (root / C_STOP_FILE).exists() or not runtime.scheduler.running:
            sleep(C_LOOP_SECONDS)
        runtime.request_stop()

    Thread(target=stop_worker, daemon=True).start()
    runtime.run()


if __name__ == "__main__":
    main()
