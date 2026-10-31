"""Executable SCH-01 wire models and substitution boundaries; no runtime startup."""

from abc import ABC, abstractmethod
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer,
    StringConstraints, ValidationInfo, field_validator, model_validator,
)

from app.models import JobBoard, JobSearchInput, JobSearchPreferenceInput
from . import constants as scheduler_constants


C_MODEL_CONFIGURATION = ConfigDict(extra="forbid", validate_default=True, strict=True)
C_AFTER_VALIDATION = "after"
C_BEFORE_VALIDATION = "before"
C_TRIGGER_DISCRIMINATOR = "kind"
C_TYPE_VARIABLE_NAME = "PageItem"
C_TIMESTAMP_SEPARATOR = "T"
C_TIMESTAMP_SPACE = " "
C_PAGE_ERROR = "Pagination totals must match the envelope."
C_SNAPSHOT_ERROR = "Run identity must match its claim snapshot."
C_RUN_STATE_ERROR = "Run timestamps and result must agree with the lifecycle state."


class UtcTimestampCodec:
    """Accept offset-bearing ISO timestamps or aware datetimes, never epoch numbers."""

    @staticmethod
    def parse(value: object) -> datetime:
        """Reject coercion and naive input before normalizing all timestamps to UTC."""
        if isinstance(value, str):
            if C_TIMESTAMP_SEPARATOR not in value and C_TIMESTAMP_SPACE not in value:
                raise ValueError(scheduler_constants.C_TIMESTAMP_ERROR)
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exception:
                raise ValueError(scheduler_constants.C_TIMESTAMP_ERROR) from exception
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(scheduler_constants.C_TIMESTAMP_ERROR)
        return value.astimezone(timezone.utc)

    @staticmethod
    def serialize(value: datetime) -> str:
        """Use exactly one Z suffix for UTC wire values."""
        return value.isoformat().replace(scheduler_constants.C_OFFSET_SUFFIX, scheduler_constants.C_UTC_SUFFIX)


UtcTimestamp = Annotated[
    datetime, BeforeValidator(UtcTimestampCodec.parse),
    PlainSerializer(UtcTimestampCodec.serialize, return_type=str),
]
PositiveInteger = Annotated[int, Field(strict=True, ge=scheduler_constants.C_ONE)]
NonnegativeInteger = Annotated[int, Field(strict=True, ge=scheduler_constants.C_ZERO)]
ScheduleName = Annotated[str, StringConstraints(
    strict=True, strip_whitespace=True, min_length=scheduler_constants.C_ONE,
    max_length=scheduler_constants.C_MAX_NAME_LENGTH,
)]
IdempotencyKey = Annotated[str, StringConstraints(
    strict=True, min_length=scheduler_constants.C_ONE,
    max_length=scheduler_constants.C_KEY_MAX_LENGTH, pattern=scheduler_constants.C_KEY_PATTERN,
)]
RunState = Literal[
    scheduler_constants.C_RUN_QUEUED, scheduler_constants.C_RUN_RUNNING,
    scheduler_constants.C_RUN_SUCCEEDED, scheduler_constants.C_RUN_PARTIAL,
    scheduler_constants.C_RUN_FAILED, scheduler_constants.C_RUN_CANCELLED,
    scheduler_constants.C_RUN_MISSED, scheduler_constants.C_RUN_INTERRUPTED,
    scheduler_constants.C_RUN_SKIPPED_OVERLAP,
]
WorkerState = Literal[
    scheduler_constants.C_WORKER_FRESH, scheduler_constants.C_WORKER_STALE,
    scheduler_constants.C_WORKER_STOPPED,
]
TaskType = Literal[scheduler_constants.C_TASK_FETCH_JOBS]


class PayloadVersionValidator:
    """Prevent Python boolean/integer equality from accepting true as version one."""

    @staticmethod
    def validate(value: object) -> int:
        """Accept only the exact integer version frozen for the fetch_jobs handler."""
        if type(value) is not int or value != scheduler_constants.C_PAYLOAD_VERSION:
            raise ValueError(scheduler_constants.C_ERROR_TASK_UNSUPPORTED)
        return value


PayloadVersion = Annotated[
    Literal[scheduler_constants.C_PAYLOAD_VERSION], BeforeValidator(PayloadVersionValidator.validate),
]


class ContractModel(BaseModel):
    """Reject unknown properties at every scheduler-owned object boundary."""

    model_config = C_MODEL_CONFIGURATION


class FetchJobsPayload(JobSearchInput):
    """Reuse existing search bounds and board names with strict distinct selections."""

    model_config = C_MODEL_CONFIGURATION

    @field_validator(scheduler_constants.C_FIELD_SITES, mode=C_BEFORE_VALIDATION)
    @classmethod
    def validate_distinct_sites(cls, value: object) -> object:
        """Reject duplicates before the inherited manual-search deduplication runs."""
        if not isinstance(value, list):
            raise ValueError(scheduler_constants.C_DUPLICATE_SITES_ERROR)
        if any(site in value[:position] for position, site in enumerate(value)):
            raise ValueError(scheduler_constants.C_DUPLICATE_SITES_ERROR)
        return value


class PreferenceSnapshot(JobSearchPreferenceInput):
    """Persist the effective saved-search criteria without scraper or ORM objects."""

    model_config = C_MODEL_CONFIGURATION


class IntervalTrigger(ContractModel):
    """Elapsed seconds anchored in UTC; a 24-hour interval is not a calendar day."""

    kind: Literal["interval"]
    seconds: int = Field(strict=True, ge=scheduler_constants.C_MIN_INTERVAL_SECONDS,
                         le=scheduler_constants.C_MAX_INTERVAL_SECONDS)
    starts_at: UtcTimestamp


class OnceTrigger(ContractModel):
    """One separately consumable timed occurrence, independent of manual runs."""

    kind: Literal["once"]
    run_at: UtcTimestamp


ScheduleTrigger = Annotated[IntervalTrigger | OnceTrigger, Field(discriminator=C_TRIGGER_DISCRIMINATOR)]


class ScheduleDefinition(ContractModel):
    """Editable fields; state changes use revision-checked dedicated operations."""

    name: ScheduleName
    task_type: TaskType
    payload_version: PayloadVersion
    payload: FetchJobsPayload
    trigger: ScheduleTrigger

    def require_future_anchor(self, now: datetime) -> None:
        """Check anchors at the transaction boundary using an injected current time."""
        anchor = self.trigger.starts_at if isinstance(self.trigger, IntervalTrigger) else self.trigger.run_at
        if anchor <= UtcTimestampCodec.parse(now):
            raise ValueError(scheduler_constants.C_FUTURE_ERROR)


class CreateScheduleRequest(ScheduleDefinition):
    """Create an enabled schedule with a strictly future first execution."""

    @model_validator(mode=C_AFTER_VALIDATION)
    def validate_future_anchor(self, information: ValidationInfo) -> "CreateScheduleRequest":
        """Use a supplied clock instant for tests/services, UTC wall time otherwise."""
        context = information.context or {}
        self.require_future_anchor(context.get(scheduler_constants.C_CONTEXT_NOW, datetime.now(timezone.utc)))
        return self


class ReplaceScheduleRequest(ScheduleDefinition):
    """Replace editable fields using the current revision, preserving unchanged anchors."""

    revision: PositiveInteger

    def validate_against(self, current: ScheduleDefinition, now: datetime) -> None:
        """Require a future anchor only when the normalized trigger actually changes."""
        if self.trigger != current.trigger:
            self.require_future_anchor(now)


class RevisionRequest(ContractModel):
    """Expected revision for pause, resume, and the DELETE query parameter."""

    revision: PositiveInteger


class RunNowRequest(RevisionRequest):
    """A durable manual request, deduplicated per schedule and retained key."""

    idempotency_key: IdempotencyKey


class PaginationRequest(ContractModel):
    """Bound list requests consistently for schedules and execution history."""

    page: PositiveInteger = scheduler_constants.C_ONE
    page_size: int = Field(default=scheduler_constants.C_DEFAULT_PAGE_SIZE, strict=True,
                           ge=scheduler_constants.C_ONE, le=scheduler_constants.C_MAX_PAGE_SIZE)


class ErrorDetail(ContractModel):
    """Stable safe API error details; validation paths contain field names only."""

    code: str = Field(strict=True)
    message: str = Field(strict=True)
    path: list[str | int] = Field(default_factory=list)
    current_revision: PositiveInteger | None = None
    schedule_ids: list[PositiveInteger] = Field(default_factory=list)


class ErrorResponse(ContractModel):
    """Common envelope for every scheduler HTTP error, including validation errors."""

    error: ErrorDetail


class BoardResult(ContractModel):
    """Safe per-board summary compatible with existing manual-fetch status names."""

    status: Literal["completed", "partial", "failed", "busy", "cooldown"]
    count: NonnegativeInteger
    warnings: list[str] = Field(default_factory=list)


class TaskResult(ContractModel):
    """Handler completion, with counts and warnings but no full scraped postings."""

    state: Literal["succeeded", "partial", "failed"]
    fetched: NonnegativeInteger = scheduler_constants.C_ZERO
    boards: dict[JobBoard, BoardResult] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: ErrorDetail | None = None

    @model_validator(mode=C_AFTER_VALIDATION)
    def validate_error(self) -> "TaskResult":
        """Make failed task results actionable without inventing successful errors."""
        if (self.state == scheduler_constants.C_RUN_FAILED) != (self.error is not None):
            raise ValueError(scheduler_constants.C_RESULT_ERROR)
        return self


class ClaimSnapshot(ScheduleDefinition):
    """Immutable-by-storage-copy definition captured during the claim transaction."""

    schedule_id: PositiveInteger
    revision: PositiveInteger


class RunSummary(ContractModel):
    """Compact execution summary displayed beside a schedule."""

    id: PositiveInteger
    state: RunState
    source: Literal["timed", "manual"]
    scheduled_for: UtcTimestamp | None = None
    queued_at: UtcTimestamp
    started_at: UtcTimestamp | None = None
    finished_at: UtcTimestamp | None = None
    skipped_count: NonnegativeInteger = scheduler_constants.C_ZERO
    result: TaskResult | None = None
    error: ErrorDetail | None = None


class RunRecord(RunSummary):
    """Durable execution with separate claim and effective-input snapshots."""

    schedule_id: PositiveInteger
    revision: PositiveInteger
    idempotency_key: IdempotencyKey | None = None
    expires_at: UtcTimestamp | None = None
    owner_token: str | None = None
    claim_snapshot: ClaimSnapshot
    effective_preference: PreferenceSnapshot | None = None

    @model_validator(mode=C_AFTER_VALIDATION)
    def validate_identity(self) -> "RunRecord":
        """Keep manual/timed uniqueness keys disjoint and snapshots traceable."""
        manual = self.source == scheduler_constants.C_SOURCE_MANUAL
        if manual != (self.idempotency_key is not None and self.expires_at is not None):
            raise ValueError(scheduler_constants.C_RUN_SOURCE_ERROR)
        if manual == (self.scheduled_for is not None):
            raise ValueError(scheduler_constants.C_RUN_SOURCE_ERROR)
        if not manual and (self.idempotency_key is not None or self.expires_at is not None):
            raise ValueError(scheduler_constants.C_RUN_SOURCE_ERROR)
        if (self.schedule_id, self.revision) != (self.claim_snapshot.schedule_id, self.claim_snapshot.revision):
            raise ValueError(C_SNAPSHOT_ERROR)
        terminal = self.state in scheduler_constants.C_TERMINAL_STATES
        if terminal != (self.finished_at is not None):
            raise ValueError(C_RUN_STATE_ERROR)
        if self.state == scheduler_constants.C_RUN_RUNNING and (self.started_at is None or self.owner_token is None):
            raise ValueError(C_RUN_STATE_ERROR)
        if self.state == scheduler_constants.C_RUN_QUEUED and self.started_at is not None:
            raise ValueError(C_RUN_STATE_ERROR)
        completed = self.state in {
            scheduler_constants.C_RUN_SUCCEEDED, scheduler_constants.C_RUN_PARTIAL,
            scheduler_constants.C_RUN_FAILED,
        }
        if completed != (self.result is not None):
            raise ValueError(C_RUN_STATE_ERROR)
        if self.result is not None and (self.result.state != self.state or self.started_at is None):
            raise ValueError(C_RUN_STATE_ERROR)
        return self


class ScheduleRecord(ScheduleDefinition):
    """Public schedule representation, also used for internal revision snapshots."""

    id: PositiveInteger
    revision: PositiveInteger
    enabled: bool = Field(strict=True)
    deleted: bool = Field(default=False, strict=True)
    next_run_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    active_run_id: PositiveInteger | None = None
    latest_run: RunSummary | None = None


class WorkerStatus(ContractModel):
    """Health is observational, never evidence of OS-lock ownership."""

    state: WorkerState
    heartbeat_at: UtcTimestamp | None = None
    started_at: UtcTimestamp | None = None
    stopped_at: UtcTimestamp | None = None
    queued_count: NonnegativeInteger = scheduler_constants.C_ZERO
    running_count: NonnegativeInteger = scheduler_constants.C_ZERO
    freshness_seconds: PositiveInteger = scheduler_constants.C_FRESHNESS_SECONDS


class RunNowResponse(ContractModel):
    """A 202 receipt can describe a deduplicated terminal run, not just a new queue entry."""

    run: RunRecord
    deduplicated: bool = Field(strict=True)
    worker: WorkerStatus
    warning: str | None = None


PageItem = TypeVar(C_TYPE_VARIABLE_NAME)


class Page(ContractModel, Generic[PageItem]):
    """Shared list envelope; empty collections have zero total pages."""

    items: list[PageItem]
    total: NonnegativeInteger
    page: PositiveInteger
    page_size: int = Field(strict=True, ge=scheduler_constants.C_ONE, le=scheduler_constants.C_MAX_PAGE_SIZE)
    total_pages: NonnegativeInteger

    @model_validator(mode=C_AFTER_VALIDATION)
    def validate_totals(self) -> "Page[PageItem]":
        """Reject inconsistent totals in API fixtures and repository adapters."""
        expected_pages = (self.total + self.page_size - scheduler_constants.C_ONE) // self.page_size
        if self.total_pages != expected_pages or len(self.items) > min(self.total, self.page_size):
            raise ValueError(C_PAGE_ERROR)
        return self


class TimedClaim(ContractModel):
    """Dispatcher calculation rechecked atomically against the expected next due time."""

    schedule_id: PositiveInteger
    revision: PositiveInteger
    expected_next_run_at: UtcTimestamp
    scheduled_for: UtcTimestamp
    next_run_at: UtcTimestamp | None
    disposition: Literal["queued", "missed", "skipped_overlap"]
    skipped_count: NonnegativeInteger = scheduler_constants.C_ZERO


class WorkerRegistration(ContractModel):
    """Process metadata for the single health slot; the token fences stale writes."""

    owner_token: IdempotencyKey
    process_id: PositiveInteger
    hostname: str = Field(strict=True)
    started_at: UtcTimestamp


class BaseClock(ABC):
    """Inject time to make lifecycle and lateness checks deterministic."""

    @abstractmethod
    def now(self) -> datetime:
        """Return an aware UTC instant."""
        raise NotImplementedError


class BaseTaskHandler(ABC):
    """Registry-owned handler, selected only by known task type and payload version."""

    @abstractmethod
    def execute(self, run: RunRecord, repository: "BaseScheduleRepository", clock: BaseClock) -> TaskResult:
        """Read and persist effective criteria before scraping; return a safe result."""
        raise NotImplementedError


class BaseExecutionReservation(ABC):
    """Own a capacity slot before claiming; release unused slots even on claim failure."""

    @abstractmethod
    def submit(self, handler: BaseTaskHandler, run: RunRecord,
               repository: "BaseScheduleRepository", clock: BaseClock) -> Future[TaskResult | None]:
        """Submit a start-gated invocation; None means cancelled/missed, then release capacity."""
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        """Idempotently release an unused reservation; never cancel running work."""
        raise NotImplementedError


class BaseExecutor(ABC):
    """Bound business work independently from APScheduler's short dispatch job."""

    @abstractmethod
    def reserve(self) -> BaseExecutionReservation | None:
        """Nonblockingly reserve capacity, returning None when all slots are occupied."""
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        """Reject submissions and drain all running work before ownership lock release."""
        raise NotImplementedError


class BaseScheduleRepository(ABC):
    """Atomic operations; implementations use short transactions and no network I/O."""

    @abstractmethod
    def create(self, request: CreateScheduleRequest, now: datetime) -> ScheduleRecord:
        """Revalidate future time, live preference and the 100-record limit atomically."""
        raise NotImplementedError

    @abstractmethod
    def get(self, schedule_id: int) -> ScheduleRecord:
        """Return a nondeleted definition or raise schedule_not_found."""
        raise NotImplementedError

    @abstractmethod
    def list_schedules(self, pagination: PaginationRequest) -> Page[ScheduleRecord]:
        """Return nondeleted schedules ordered by id ascending, with consistent totals."""
        raise NotImplementedError

    @abstractmethod
    def replace(self, schedule_id: int, request: ReplaceScheduleRequest, now: datetime) -> ScheduleRecord:
        """Check revision/preferences; preserve unchanged due time; increment revision."""
        raise NotImplementedError

    @abstractmethod
    def set_enabled(self, schedule_id: int, revision: int, enabled: bool, now: datetime) -> ScheduleRecord:
        """Revision-check pause/resume; resume advances intervals, rejects expired once."""
        raise NotImplementedError

    @abstractmethod
    def tombstone(self, schedule_id: int, revision: int, now: datetime) -> None:
        """Disable, increment revision and clear the preference FK; active work can finish."""
        raise NotImplementedError

    @abstractmethod
    def referencing_schedule_ids(self, preference_id: int) -> list[int]:
        """List live references; deletion must repeat this guard in its own transaction."""
        raise NotImplementedError

    @abstractmethod
    def request_manual(self, schedule_id: int, request: RunNowRequest, now: datetime) -> tuple[RunRecord, bool]:
        """Deduplicate before revision check; otherwise atomically enforce one active run."""
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: int) -> RunRecord:
        """Return retained run snapshots or raise schedule_not_found for absent history."""
        raise NotImplementedError

    @abstractmethod
    def list_runs(self, schedule_id: int, pagination: PaginationRequest) -> Page[RunRecord]:
        """Include tombstoned schedule history, ordered by queued_at then id descending."""
        raise NotImplementedError

    @abstractmethod
    def list_due(self, now: datetime, limit: int) -> list[ScheduleRecord]:
        """Return enabled due schedules ordered by next_run_at then id, without claiming."""
        raise NotImplementedError

    @abstractmethod
    def list_queued_manual(self, now: datetime, limit: int) -> list[RunRecord]:
        """Return unexpired unowned manual requests ordered by queued_at then id."""
        raise NotImplementedError

    @abstractmethod
    def claim_timed(self, claim: TimedClaim, owner_token: str, now: datetime) -> RunRecord | None:
        """Compare due/revision/state, snapshot and advance atomically; None loses a race."""
        raise NotImplementedError

    @abstractmethod
    def claim_manual(self, run_id: int, owner_token: str, now: datetime) -> RunRecord | None:
        """Assign an unowned queued request atomically; do not change recurrence."""
        raise NotImplementedError

    @abstractmethod
    def start_run(self, run_id: int, owner_token: str, now: datetime) -> RunRecord:
        """Final atomic check returns running, cancelled or missed; invoke only running."""
        raise NotImplementedError

    @abstractmethod
    def record_effective_preference(self, run_id: int, owner_token: str,
                                    preference: PreferenceSnapshot, now: datetime) -> None:
        """Copy effective criteria exactly once for an owned running run before scraping."""
        raise NotImplementedError

    @abstractmethod
    def complete(self, run_id: int, owner_token: str, result: TaskResult, now: datetime) -> RunRecord:
        """Finish an owned running run; disable only its still-current timed once schedule."""
        raise NotImplementedError

    @abstractmethod
    def cancel_submission(self, run_id: int, owner_token: str, now: datetime) -> RunRecord:
        """Cancel owned queued work after executor rejection; never rewind due time."""
        raise NotImplementedError

    @abstractmethod
    def expire_manual(self, now: datetime, limit: int) -> int:
        """Mark expired queued manual requests missed, even when executor capacity is full."""
        raise NotImplementedError

    @abstractmethod
    def recover(self, worker: WorkerRegistration, now: datetime) -> int:
        """Under singleton lock, interrupt old-owner work and replace health ownership."""
        raise NotImplementedError

    @abstractmethod
    def heartbeat(self, owner_token: str, now: datetime) -> None:
        """Refresh only the current owner after a successful dispatch pass."""
        raise NotImplementedError

    @abstractmethod
    def stop_worker(self, owner_token: str, now: datetime) -> None:
        """Mark the current worker stopped after draining tasks."""
        raise NotImplementedError

    @abstractmethod
    def worker_status(self, now: datetime) -> WorkerStatus:
        """Compute freshness and active counts; no worker row means stopped."""
        raise NotImplementedError

    @abstractmethod
    def prune_terminal(self, before: datetime, limit: int) -> int:
        """Delete a bounded oldest-first batch of terminal runs, never active runs."""
        raise NotImplementedError

    @abstractmethod
    def get_board_cooldown(self, site: JobBoard) -> datetime | None:
        """Read a persisted UTC cooldown under the shared per-board OS lock."""
        raise NotImplementedError

    @abstractmethod
    def extend_board_cooldown(self, site: JobBoard, until: datetime) -> None:
        """Persist the maximum of existing and requested deadlines, never shorten it."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release repository resources without changing durable worker ownership."""
        raise NotImplementedError
