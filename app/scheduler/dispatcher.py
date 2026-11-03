"""Short fair dispatch passes that never execute scrapers on APScheduler threads."""

from datetime import timedelta
import logging

from . import constants as scheduler_constants
from .triggers import TriggerCalculator
from .errors import SchedulerError
from .registry import UnsupportedTaskHandler

C_LOGGER = logging.getLogger(__name__)


class Dispatcher:
    """Alternate manual/timed queues and reserve capacity before durable ownership."""

    def __init__(self, repository, registry, executor, clock, owner_token, retention_days):
        """Borrow runtime resources and start with manual work to service queued requests."""
        self.repository = repository
        self.registry = registry
        self.executor = executor
        self.clock = clock
        self.owner_token = owner_token
        self.retention_days = retention_days
        self.manual_first = True
        self.stopped = False
        self.pending_submissions = {}

    def _submit(self, reservation, run):
        """Cancel rejected claims rather than leaking an active record or rewinding time."""
        self.pending_submissions[run.id] = run
        try:
            try:
                handler = self.registry.resolve(run.claim_snapshot.task_type, run.claim_snapshot.payload_version)
            except SchedulerError as exception:
                if exception.code != scheduler_constants.C_ERROR_TASK_UNSUPPORTED:
                    raise
                handler = UnsupportedTaskHandler()
            reservation.submit(handler, run, self.repository, self.clock)
            self.pending_submissions.pop(run.id, None)
        except Exception:
            reservation.release()
            self.repository.cancel_submission(run.id, self.owner_token, self.clock.now())
            self.pending_submissions.pop(run.id, None)
            raise

    def reconcile_submissions(self):
        """Retry terminal writes after submission rejection without ever replaying a handler."""
        for run_id in tuple(self.pending_submissions):
            run = self.repository.get_run(run_id)
            if run.state == scheduler_constants.C_RUN_QUEUED:
                self.repository.cancel_submission(run_id, self.owner_token, self.clock.now())
            self.pending_submissions.pop(run_id, None)

    def dispatch(self):
        """Advance summaries despite saturation and heartbeat only after a successful pass."""
        if self.stopped:
            return
        now = self.clock.now()
        self.reconcile_submissions()
        self.executor.reconcile(self.repository, self.clock)
        self.repository.expire_manual(now, scheduler_constants.C_RETENTION_BATCH_SIZE)
        timed = self.repository.list_due(now, scheduler_constants.C_MAX_SCHEDULES)
        manual = self.repository.list_queued_manual(now, scheduler_constants.C_MAX_SCHEDULES)
        work = []
        # Keep FIFO order within each queue while alternating priority between ticks.
        while timed or manual:
            queues = ((manual, True), (timed, False)) if self.manual_first else ((timed, False), (manual, True))
            for queue, is_manual in queues:
                if queue:
                    work.append((queue.pop(scheduler_constants.C_ZERO), is_manual))
        self.manual_first = not self.manual_first
        for record, is_manual in work:
            if self.stopped:
                break
            claim = None if is_manual else TriggerCalculator.due(record, now)
            if claim is not None and claim.disposition != scheduler_constants.C_RUN_QUEUED:
                self.repository.claim_timed(claim, self.owner_token, now)
                continue
            reservation = self.executor.reserve()
            if reservation is None:
                continue
            try:
                run = (self.repository.claim_manual(record.id, self.owner_token, now) if is_manual
                       else self.repository.claim_timed(claim, self.owner_token, now))
                if run is None:
                    reservation.release()
                else:
                    self._submit(reservation, run)
            except Exception:
                reservation.release()
                raise
        self.repository.prune_terminal(now - timedelta(days=self.retention_days), scheduler_constants.C_RETENTION_BATCH_SIZE)
        self.repository.heartbeat(self.owner_token, self.clock.now())

    def tick(self):
        """Log safe failure metadata and leave health stale when dispatch cannot progress."""
        try:
            self.dispatch()
        except Exception as exception:
            C_LOGGER.error("dispatch_failed error_type=%s", type(exception).__name__)
