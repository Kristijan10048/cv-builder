"""Transport-independent errors; adapters map only known safe details to HTTP."""

from . import constants as scheduler_constants

C_ERROR_HTTP_STATUS = {
    scheduler_constants.C_ERROR_NOT_FOUND: scheduler_constants.C_HTTP_NOT_FOUND,
    scheduler_constants.C_ERROR_REVISION: scheduler_constants.C_HTTP_CONFLICT,
    scheduler_constants.C_ERROR_ACTIVE_RUN: scheduler_constants.C_HTTP_CONFLICT,
    scheduler_constants.C_ERROR_IDEMPOTENCY: scheduler_constants.C_HTTP_CONFLICT,
    scheduler_constants.C_ERROR_LIMIT: scheduler_constants.C_HTTP_CONFLICT,
    scheduler_constants.C_ERROR_PREFERENCE_REFERENCED: scheduler_constants.C_HTTP_CONFLICT,
    scheduler_constants.C_ERROR_PREFERENCE_MISSING: scheduler_constants.C_HTTP_VALIDATION,
    scheduler_constants.C_ERROR_VALIDATION: scheduler_constants.C_HTTP_VALIDATION,
    scheduler_constants.C_ERROR_TASK_UNSUPPORTED: scheduler_constants.C_HTTP_VALIDATION,
    scheduler_constants.C_ERROR_STORAGE: scheduler_constants.C_HTTP_UNAVAILABLE,
}


class SchedulerError(Exception):
    """Carry a stable code and deliberately safe message across service boundaries."""

    def __init__(
        self, code: str, message: str, *, current_revision: int | None = None,
        schedule_ids: tuple[int, ...] = (),
    ) -> None:
        """Keep database exceptions and personal payloads out of public error details."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.current_revision = current_revision
        self.schedule_ids = schedule_ids


class SchedulerConfigurationError(ValueError):
    """Reject invalid startup settings without echoing potentially sensitive values."""
