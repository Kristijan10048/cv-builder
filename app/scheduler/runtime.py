"""Standalone APScheduler lifecycle; never imported or launched by FastAPI startup."""

import logging
import os
import signal
import socket
from uuid import uuid4

from apscheduler.schedulers.blocking import BlockingScheduler

from app import database
from app.database_locking import DatabaseLock
from . import constants as scheduler_constants
from .configuration import SchedulerConfiguration
from .contracts import WorkerRegistration
from .dispatcher import Dispatcher
from .executor import TaskExecutor
from .handlers.fetch_jobs import FetchJobsTaskHandler
from .logging_setup import WorkerLogging
from .registry import TaskRegistry
from .repository import ScheduleRepository
from .triggers import SystemClock

C_DISPATCH_JOB = "dispatch"
C_INTERVAL = "interval"
C_TIMEZONE = "UTC"
C_LOGGER = logging.getLogger(__name__)


class SchedulerRuntime:
    """Retain singleton ownership until all business execution and persistence finish."""

    def __init__(self, configuration=None, handler=None, clock=None):
        """Allow trusted test injections without adding public fake-task configuration."""
        self.configuration = configuration or SchedulerConfiguration.from_environment()
        self.handler = handler or FetchJobsTaskHandler()
        self.clock = clock or SystemClock()
        self.scheduler = BlockingScheduler(timezone=C_TIMEZONE)
        self.dispatcher = None

    def request_stop(self, signal_number=None, frame=None):
        """Stop new claims; APScheduler shutdown waits for the short active dispatch pass."""
        if self.dispatcher is not None:
            self.dispatcher.stopped = True
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

    def run(self):
        """Acquire ownership, migrate/recover, dispatch, then drain before releasing the lock."""
        configuration = self.configuration
        with DatabaseLock(configuration, scheduler_constants.C_LOCK_WORKER), WorkerLogging(configuration):
            database.DB_PATH = configuration.database_path
            database.init_db()
            repository = ScheduleRepository()
            executor = TaskExecutor(configuration.max_workers)
            owner_token = str(uuid4())
            registry = TaskRegistry()
            registry.register(scheduler_constants.C_TASK_FETCH_JOBS, scheduler_constants.C_PAYLOAD_VERSION, self.handler)
            self.dispatcher = Dispatcher(repository, registry, executor, self.clock, owner_token, configuration.retention_days)
            previous_handlers = {}
            try:
                repository.recover(WorkerRegistration(owner_token=owner_token, process_id=os.getpid(),
                                                      hostname=socket.gethostname(), started_at=self.clock.now()), self.clock.now())
                for signal_number in (signal.SIGINT, signal.SIGTERM):
                    previous_handlers[signal_number] = signal.signal(signal_number, self.request_stop)
                self.scheduler.add_job(self.dispatcher.tick, C_INTERVAL, seconds=configuration.poll_seconds,
                                       id=C_DISPATCH_JOB, coalesce=True, max_instances=scheduler_constants.C_ONE,
                                       next_run_time=self.clock.now())
                C_LOGGER.info("worker_started owner_token=%s", owner_token)
                self.scheduler.start()
            finally:
                self.dispatcher.stopped = True
                executor.shutdown()
                try:
                    self.dispatcher.reconcile_submissions()
                    executor.reconcile(repository, self.clock)
                    repository.stop_worker(owner_token, self.clock.now())
                finally:
                    repository.close()
                    for signal_number, previous in previous_handlers.items():
                        signal.signal(signal_number, previous)
                C_LOGGER.info("worker_stopped owner_token=%s", owner_token)
