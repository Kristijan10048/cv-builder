"""Execute saved-search fetching through the same service as manual requests."""

from dataclasses import asdict

from app.services.job_search_dependencies import JobSearchServiceFactory
from app.services.job_search_errors import AllBoardsFailedError, PreferenceDeletedError, PreferenceNotFoundError
from .. import constants as scheduler_constants
from ..contracts import BaseTaskHandler, BoardResult, ErrorDetail, PreferenceSnapshot, TaskResult

C_STATUS = "status"
C_COUNT = "count"
C_COMPLETED = "completed"
C_WARNING_SEPARATOR = ": "
C_FAILURE_MESSAGE = "The job search could not complete. Check the saved search and board warnings."


class FetchJobsTaskHandler(BaseTaskHandler):
    """Capture effective inputs before fetching and map independent board outcomes."""

    def __init__(self, factory=None):
        """Accept an offline scraper factory for integration tests without new task types."""
        self.factory = factory or JobSearchServiceFactory()

    @staticmethod
    def _boards(boards, warnings):
        """Preserve safe board statuses/counts and attach their corresponding warnings."""
        return {site: BoardResult(status=result[C_STATUS], count=result[C_COUNT], warnings=[
            warning for warning in warnings if warning.startswith(site + C_WARNING_SEPARATOR)
        ]) for site, result in boards.items()}

    def execute(self, run, repository, clock):
        """Read current criteria, record them once, and reuse existing transactional upserts."""
        def capture_preference(preference):
            """Persist only the search criteria used by this execution, without ORM metadata."""
            fields = asdict(preference)
            snapshot = PreferenceSnapshot.model_validate({field: fields[field] for field in PreferenceSnapshot.model_fields})
            repository.record_effective_preference(run.id, run.owner_token, snapshot, clock.now())

        try:
            with self.factory.create() as service:
                outcome = service.fetch(run.claim_snapshot.payload, on_preference=capture_preference)
            boards = self._boards(outcome.boards, outcome.warnings)
            partial = bool(outcome.warnings) or any(board.status != C_COMPLETED for board in boards.values())
            return TaskResult(state=scheduler_constants.C_RUN_PARTIAL if partial else scheduler_constants.C_RUN_SUCCEEDED,
                              fetched=len({(job.site, job.job_url) for job in outcome.jobs}),
                              boards=boards, warnings=outcome.warnings)
        except AllBoardsFailedError as exception:
            return TaskResult(state=scheduler_constants.C_RUN_FAILED,
                              boards=self._boards(exception.boards, exception.warnings), warnings=exception.warnings,
                              error=ErrorDetail(code=scheduler_constants.C_ERROR_TASK_FAILED, message=C_FAILURE_MESSAGE))
        except (PreferenceNotFoundError, PreferenceDeletedError):
            return TaskResult(state=scheduler_constants.C_RUN_FAILED,
                              error=ErrorDetail(code=scheduler_constants.C_ERROR_PREFERENCE_MISSING, message=C_FAILURE_MESSAGE))
