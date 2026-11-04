"""Reserve capacity before claims and drain running network work before releasing ownership."""

from concurrent.futures import ThreadPoolExecutor
import logging
from threading import BoundedSemaphore, Lock

from . import constants as scheduler_constants
from .contracts import BaseExecutionReservation, BaseExecutor, ErrorDetail, TaskResult

C_THREAD_PREFIX = "scheduled-task"
C_FAILURE_MESSAGE = "Task execution failed. See worker diagnostics."
C_LOGGER = logging.getLogger(__name__)


class ExecutionReservation(BaseExecutionReservation):
    """Transfer exactly one reserved slot to a submitted future."""

    def __init__(self, executor):
        """Retain the executor and protect slot release against repeated cleanup."""
        self.executor = executor
        self.released = False
        self.lock = Lock()

    def release(self):
        """Return an unused or completed slot exactly once."""
        with self.lock:
            if not self.released:
                self.released = True
                self.executor.capacity.release()

    def submit(self, handler, run, repository, clock):
        """Start-gate, execute, persist completion, and release capacity in the worker thread."""
        def execute():
            """Prevent queued invalidation races and sanitize unexpected handler failures."""
            try:
                started = repository.start_run(run.id, run.owner_token, clock.now())
                if started.state != scheduler_constants.C_RUN_RUNNING:
                    return None
                try:
                    result = handler.execute(started, repository, clock)
                except Exception as exception:
                    C_LOGGER.error("task_failed run_id=%s schedule_id=%s error_type=%s", run.id, run.schedule_id, type(exception).__name__)
                    result = TaskResult(state=scheduler_constants.C_RUN_FAILED, error=ErrorDetail(
                        code=scheduler_constants.C_ERROR_TASK_FAILED, message=C_FAILURE_MESSAGE))
                repository.complete(run.id, run.owner_token, result, clock.now())
                C_LOGGER.info("task_completed run_id=%s schedule_id=%s state=%s fetched=%s duration_seconds=%s",
                              run.id, run.schedule_id, result.state, result.fetched,
                              (clock.now() - started.started_at).total_seconds())
                return result
            finally:
                self.release()

        try:
            future = self.executor.pool.submit(execute)
            self.executor.track(future, run)
            return future
        except Exception:
            self.release()
            raise


class TaskExecutor(BaseExecutor):
    """Use a bounded business executor independent of APScheduler dispatch threads."""

    def __init__(self, max_workers):
        """Allocate capacity accounting without claiming any durable work."""
        self.capacity = BoundedSemaphore(max_workers)
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=C_THREAD_PREFIX)
        self.stopped = False
        self.futures = {}
        self.lock = Lock()

    def reserve(self):
        """Return immediately if capacity is full; no database claim has happened yet."""
        if self.stopped or not self.capacity.acquire(blocking=False):
            return None
        return ExecutionReservation(self)

    def track(self, future, run):
        """Keep completed futures until dispatch can persist any exceptional transition."""
        with self.lock:
            self.futures[future] = run

    def reconcile(self, repository, clock):
        """Retry failed terminal writes without replaying uncertain business work."""
        with self.lock:
            completed = [(future, run) for future, run in self.futures.items() if future.done()]
        for future, run in completed:
            if future.exception() is not None:
                current = repository.get_run(run.id)
                if current.state == scheduler_constants.C_RUN_QUEUED:
                    repository.cancel_submission(run.id, run.owner_token, clock.now())
                elif current.state == scheduler_constants.C_RUN_RUNNING:
                    repository.complete(run.id, run.owner_token, TaskResult(
                        state=scheduler_constants.C_RUN_FAILED,
                        error=ErrorDetail(code=scheduler_constants.C_ERROR_TASK_FAILED, message=C_FAILURE_MESSAGE)), clock.now())
            with self.lock:
                self.futures.pop(future, None)

    def shutdown(self):
        """Stop accepting reservations and wait for all submitted calls to finish."""
        self.stopped = True
        self.pool.shutdown(wait=True)
