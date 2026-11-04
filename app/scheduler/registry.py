"""Explicit handler registry with no persisted import paths or arbitrary execution."""

from .contracts import BaseTaskHandler, ErrorDetail, TaskResult
from .errors import SchedulerError
from . import constants as scheduler_constants

C_UNSUPPORTED_MESSAGE = "This task type or payload version is not supported."


class UnsupportedTaskHandler(BaseTaskHandler):
    """Record a safe terminal failure when a valid persisted pair has been disabled."""

    def execute(self, run, repository, clock):
        """Never invoke business code for a registry entry with no trusted handler."""
        return TaskResult(state=scheduler_constants.C_RUN_FAILED, error=ErrorDetail(
            code=scheduler_constants.C_ERROR_TASK_UNSUPPORTED, message=C_UNSUPPORTED_MESSAGE))


class TaskRegistry:
    """Associate validated task/version pairs with already-constructed handlers."""

    def __init__(self):
        """Start empty so tests and runtime explicitly choose their handlers."""
        self.handlers = {}

    def register(self, task_type: str, payload_version: int, handler: BaseTaskHandler):
        """Register a trusted handler instance, never a user-provided callable string."""
        self.handlers[(task_type, payload_version)] = handler

    def resolve(self, task_type, payload_version):
        """Fail safely if a persisted task has no supported implementation."""
        handler = self.handlers.get((task_type, payload_version))
        if handler is None:
            raise SchedulerError(scheduler_constants.C_ERROR_TASK_UNSUPPORTED, C_UNSUPPORTED_MESSAGE)
        return handler
