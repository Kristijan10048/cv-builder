"""Scheduler management routes with strict safe errors and no worker startup side effects."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import constants as scheduler_constants
from .contracts import (
    CreateScheduleRequest, ErrorDetail, ErrorResponse, Page, PaginationRequest,
    ReplaceScheduleRequest, RevisionRequest, RunNowRequest, RunNowResponse,
    RunRecord, ScheduleRecord, WorkerStatus,
)
from .errors import C_ERROR_HTTP_STATUS, SchedulerError
from .management_service import ScheduleManagementService
from .repository import ScheduleRepository
from .triggers import SystemClock

C_PREFIX = "/api"
C_TAG = "Scheduled tasks"
C_COLLECTION = "/task-schedules"
C_ITEM = "/task-schedules/{schedule_id}"
C_PAUSE = C_ITEM + "/pause"
C_RESUME = C_ITEM + "/resume"
C_RUN_NOW = C_ITEM + "/run-now"
C_HISTORY = C_ITEM + "/runs"
C_STATUS = "/scheduler/status"
C_CREATED = 201
C_ACCEPTED = 202
C_NO_CONTENT = 204
C_SAFE_VALIDATION_MESSAGE = "Invalid request. Check the field types, limits and future start time."
C_FIELD_LOCATION = "loc"
C_BODY_LOCATION = "body"
C_QUERY_LOCATION = "query"
C_PATH_LOCATION = "path"
C_IDENTIFIER = "schedule_id"
C_INTEGER_PATTERN = r"[1-9][0-9]*"
C_JSON_MODE = "json"
C_PAGE_FIELDS = frozenset({"page", "page_size"})
C_REVISION_FIELDS = frozenset({"revision"})
C_TASK_FIELDS = frozenset({"task_type", "payload_version"})
C_UNSUPPORTED_MESSAGE = "This task type or payload version is not supported."
C_VALIDATION_FIELDS = frozenset({
    "preference_id", "sites", "results_wanted", "kind", "seconds", "starts_at", "run_at",
    "idempotency_key", "page", "page_size", C_IDENTIFIER,
    C_BODY_LOCATION, C_QUERY_LOCATION, C_PATH_LOCATION,
})


def error_response(exception: SchedulerError):
    """Serialize only explicitly safe domain fields, never exception internals."""
    body = ErrorResponse(error=ErrorDetail(code=exception.code, message=exception.message,
                                         current_revision=exception.current_revision,
                                         schedule_ids=list(exception.schedule_ids)))
    return JSONResponse(status_code=C_ERROR_HTTP_STATUS[exception.code], content=body.model_dump(mode=C_JSON_MODE))


class SchedulerRoute(APIRoute):
    """Translate validation locally without changing unrelated application's error shapes."""

    def get_route_handler(self):
        """Wrap dependency/body validation as well as the final route invocation."""
        original = super().get_route_handler()

        async def handle(request):
            """Keep rejected values, database paths and raw Pydantic context out of responses."""
            try:
                return await original(request)
            except SchedulerError as exception:
                return error_response(exception)
            except (RequestValidationError, ValidationError) as exception:
                # Only declared fields and numeric array positions may be reflected.
                declared = set(CreateScheduleRequest.model_fields) | set(ReplaceScheduleRequest.model_fields)
                declared |= C_VALIDATION_FIELDS
                location = exception.errors()[scheduler_constants.C_ZERO].get(C_FIELD_LOCATION, ())
                path = [part for part in location if isinstance(part, int) or part in declared]
                unsupported = bool(C_TASK_FIELDS.intersection(location))
                body = ErrorResponse(error=ErrorDetail(
                    code=scheduler_constants.C_ERROR_TASK_UNSUPPORTED if unsupported else scheduler_constants.C_ERROR_VALIDATION,
                    message=C_UNSUPPORTED_MESSAGE if unsupported else C_SAFE_VALIDATION_MESSAGE, path=path))
                return JSONResponse(status_code=scheduler_constants.C_HTTP_VALIDATION, content=body.model_dump(mode=C_JSON_MODE))
        return handle


C_ROUTER = APIRouter(prefix=C_PREFIX, tags=[C_TAG], route_class=SchedulerRoute)


def get_repository():
    """Close each request's engine even when management fails."""
    repository = ScheduleRepository()
    try:
        yield repository
    finally:
        repository.close()


def get_clock():
    """Expose an overrideable wall clock for HTTP contract tests."""
    return SystemClock()


def validate_query(request: Request, allowed=frozenset()):
    """Reject unknown/duplicate query fields rather than silently ignoring client mistakes."""
    keys = list(request.query_params.keys())
    if set(keys) - allowed or any(len(request.query_params.getlist(key)) != scheduler_constants.C_ONE for key in keys):
        raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, C_SAFE_VALIDATION_MESSAGE)


def no_query(request: Request):
    """Require an empty query on mutation/item/status routes."""
    validate_query(request)


def positive_parameter(value):
    """Parse canonical decimal URL integers without accepting signs, floats or booleans."""
    if re.fullmatch(C_INTEGER_PATTERN, value) is None:
        raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, C_SAFE_VALIDATION_MESSAGE)
    return int(value)


def schedule_identifier(request: Request):
    """Validate positive path identity with the same safe error contract."""
    return positive_parameter(request.path_params[C_IDENTIFIER])


def pagination(request: Request):
    """Validate and bound only the declared pagination query parameters."""
    validate_query(request, C_PAGE_FIELDS)
    return PaginationRequest(**{key: positive_parameter(value) for key, value in request.query_params.items()})


def delete_revision(request: Request):
    """Require exactly the current revision query for deletion."""
    validate_query(request, C_REVISION_FIELDS)
    return RevisionRequest(**{key: positive_parameter(value) for key, value in request.query_params.items()})


RepositoryDependency = Annotated[ScheduleRepository, Depends(get_repository)]
ClockDependency = Annotated[SystemClock, Depends(get_clock)]
IdentifierDependency = Annotated[int, Depends(schedule_identifier)]
PaginationDependency = Annotated[PaginationRequest, Depends(pagination)]
C_NO_QUERY = [Depends(no_query)]


@C_ROUTER.get(C_COLLECTION, response_model=Page[ScheduleRecord])
def list_schedules(repository: RepositoryDependency, page: PaginationDependency):
    """List live definitions whether the worker is online or offline."""
    return repository.list_schedules(page)


@C_ROUTER.post(C_COLLECTION, response_model=ScheduleRecord, status_code=C_CREATED, dependencies=C_NO_QUERY)
def create_schedule(payload: CreateScheduleRequest, repository: RepositoryDependency, clock: ClockDependency):
    """Create an enabled future schedule without starting a task."""
    return repository.create(payload, clock.now())


@C_ROUTER.get(C_ITEM, response_model=ScheduleRecord, dependencies=C_NO_QUERY)
def get_schedule(schedule_id: IdentifierDependency, repository: RepositoryDependency):
    """Read a single nondeleted definition."""
    return repository.get(schedule_id)


@C_ROUTER.put(C_ITEM, response_model=ScheduleRecord, dependencies=C_NO_QUERY)
def replace_schedule(schedule_id: IdentifierDependency, payload: ReplaceScheduleRequest,
                     repository: RepositoryDependency, clock: ClockDependency):
    """Replace editable fields with revision checking."""
    return repository.replace(schedule_id, payload, clock.now())


@C_ROUTER.post(C_PAUSE, response_model=ScheduleRecord, dependencies=C_NO_QUERY)
def pause_schedule(schedule_id: IdentifierDependency, payload: RevisionRequest,
                   repository: RepositoryDependency, clock: ClockDependency):
    """Pause future eligibility; an already-running handler may finish."""
    return repository.set_enabled(schedule_id, payload.revision, False, clock.now())


@C_ROUTER.post(C_RESUME, response_model=ScheduleRecord, dependencies=C_NO_QUERY)
def resume_schedule(schedule_id: IdentifierDependency, payload: RevisionRequest,
                    repository: RepositoryDependency, clock: ClockDependency):
    """Resume at the next future interval occurrence or a future one-time anchor."""
    return repository.set_enabled(schedule_id, payload.revision, True, clock.now())


@C_ROUTER.delete(C_ITEM, status_code=C_NO_CONTENT)
def delete_schedule(schedule_id: IdentifierDependency, revision: Annotated[RevisionRequest, Depends(delete_revision)],
                    repository: RepositoryDependency, clock: ClockDependency):
    """Tombstone a definition while retaining its execution history."""
    repository.tombstone(schedule_id, revision.revision, clock.now())
    return Response(status_code=C_NO_CONTENT)


@C_ROUTER.post(C_RUN_NOW, response_model=RunNowResponse, status_code=C_ACCEPTED, dependencies=C_NO_QUERY)
def run_now(schedule_id: IdentifierDependency, payload: RunNowRequest,
            repository: RepositoryDependency, clock: ClockDependency):
    """Return a durable acceptance receipt, never a fabricated task completion."""
    return ScheduleManagementService(repository, clock).run_now(schedule_id, payload)


@C_ROUTER.get(C_HISTORY, response_model=Page[RunRecord])
def list_runs(schedule_id: IdentifierDependency, repository: RepositoryDependency, page: PaginationDependency):
    """Return paginated history including deleted schedules."""
    return repository.list_runs(schedule_id, page)


@C_ROUTER.get(C_STATUS, response_model=WorkerStatus, dependencies=C_NO_QUERY)
def worker_status(repository: RepositoryDependency, clock: ClockDependency):
    """Observe worker freshness and active queue counts without launching anything."""
    return repository.worker_status(clock.now())
