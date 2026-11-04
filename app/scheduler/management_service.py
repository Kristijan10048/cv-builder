"""Web-facing orchestration that records requests without launching business work."""

from . import constants as scheduler_constants
from .contracts import RunNowResponse


class ScheduleManagementService:
    """Combine durable request receipts with observational worker availability."""

    def __init__(self, repository, clock):
        """Borrow request-scoped persistence and an injectable UTC clock."""
        self.repository = repository
        self.clock = clock

    def run_now(self, schedule_id, request):
        """Accept/deduplicate a request and explicitly warn when the worker is offline."""
        now = self.clock.now()
        run, deduplicated = self.repository.request_manual(schedule_id, request, now)
        worker = self.repository.worker_status(now)
        return RunNowResponse(run=run, deduplicated=deduplicated, worker=worker,
                              warning=None if worker.state == scheduler_constants.C_WORKER_FRESH
                              else scheduler_constants.C_WORKER_OFFLINE_WARNING)
