"""Short serialized SQLite transactions implementing durable scheduler contracts."""

from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import create_engine, delete, event, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import database
from app.database_models import JobSearchPreferenceModel
from app.job_search_adapter import JobSearchAdapter
from app.job_search_repository import BasePreferenceDeletionGuard
from . import constants as scheduler_constants
from .contracts import (
    BaseScheduleRepository, ClaimSnapshot, ErrorDetail, Page, PreferenceSnapshot,
    RunRecord, RunSummary, ScheduleRecord, UtcTimestampCodec, WorkerStatus,
)
from .database_models import (
    JobBoardStateModel, SchedulerWorkerModel, TaskRunModel, TaskScheduleModel,
)
from .errors import SchedulerError
from .queries import ScheduleQueries
from .triggers import TriggerCalculator

C_ENGINE_URL = "sqlite://"
C_BEGIN_EVENT = "begin"
C_BEGIN_READ = "BEGIN"
C_BEGIN_WRITE = "BEGIN IMMEDIATE"
C_WRITE_OPTION = "scheduler_write"
C_JSON_MODE = "json"
C_ID = "id"
C_RECORD = "record"
C_HEARTBEAT = "heartbeat_at"
C_STARTED = "started_at"
C_STOPPED = "stopped_at"
C_MESSAGE_NOT_FOUND = "Schedule or retained run not found."
C_MESSAGE_REVISION = "This schedule changed. Refresh before trying again."
C_MESSAGE_ACTIVE = "An execution is already active or ownership has changed."
C_MESSAGE_STORAGE = "Storage is temporarily unavailable. Try again."
C_MESSAGE_REFERENCE = "Delete the referencing schedules before deleting this saved search."
C_MESSAGE_PREFERENCE = "The saved search does not exist."
C_MESSAGE_LIMIT = "You can save up to 100 schedules."
C_MESSAGE_KEY = "This request key was already used with another revision."
C_MESSAGE_CANCELLED = "The queued execution was invalidated by a schedule change."
C_MESSAGE_EXPIRED = "The queued request expired before execution."
C_MESSAGE_INTERRUPTED = "Worker stopped unexpectedly. Jobs may have been saved; execution was not retried."
C_MESSAGE_SUBMISSION = "The worker could not submit this execution."
C_TIMESTAMP_PRECISION = "microseconds"
C_RUN_TIMESTAMP_FIELDS = ("scheduled_for", "queued_at", "finished_at", "expires_at")
C_DEFINITION_FIELDS = frozenset({"name", "task_type", "payload_version", "payload", "trigger"})
C_SCHEDULE_FIELDS = ("revision", "enabled", "deleted", "next_run_at")
C_RUN_FIELDS = (
    "schedule_id", "revision", "state", "source", "scheduled_for", "idempotency_key",
    "owner_token", "queued_at", "finished_at", "expires_at",
)


class SchedulePreferenceDeletionGuard(BasePreferenceDeletionGuard):
    """Veto preference deletion inside the caller's already-serialized transaction."""

    def validate_deletion(self, connection, preference_id: int) -> None:
        """Protect both enabled and paused nondeleted schedules from broken references."""
        identifiers = tuple(connection.execute(ScheduleQueries.references(preference_id)).scalars())
        if identifiers:
            raise SchedulerError(scheduler_constants.C_ERROR_PREFERENCE_REFERENCED,
                                 C_MESSAGE_REFERENCE, schedule_ids=identifiers)


class ScheduleRepository(BaseScheduleRepository):
    """Store validated JSON snapshots alongside indexed relational lifecycle fields."""

    def __init__(self, connection_factory=None) -> None:
        """Create a close-on-return engine without opening or migrating the database."""
        self.connection_factory = connection_factory or database.connect
        self.engine = create_engine(C_ENGINE_URL, creator=self._connect, poolclass=NullPool)
        event.listen(self.engine, C_BEGIN_EVENT, self._begin)

    def _connect(self):
        """Disable sqlite implicit transactions so reads and writes have explicit boundaries."""
        connection = self.connection_factory()
        connection.isolation_level = None
        return connection

    @staticmethod
    def _begin(connection) -> None:
        """Acquire the writer lock before reading values used by any mutation."""
        statement = C_BEGIN_WRITE if connection.get_execution_options().get(C_WRITE_OPTION) else C_BEGIN_READ
        connection.exec_driver_sql(statement)

    @contextmanager
    def transaction(self, write=False):
        """Rollback failures and translate database details into a safe domain error."""
        try:
            with self.engine.connect().execution_options(**{C_WRITE_OPTION: write}) as connection:
                with connection.begin():
                    yield connection
        except SQLAlchemyError as exception:
            raise SchedulerError(scheduler_constants.C_ERROR_STORAGE, C_MESSAGE_STORAGE) from exception

    @staticmethod
    def _stamp(instant):
        """Use fixed precision so lexical SQLite timestamp ordering remains chronological."""
        if instant is None:
            return None
        return UtcTimestampCodec.parse(instant).isoformat(timespec=C_TIMESTAMP_PRECISION)

    @staticmethod
    def _error(code, message):
        """Build safe persisted lifecycle error details."""
        return ErrorDetail(code=code, message=message)

    def _schedule(self, connection, schedule_id, include_deleted=False):
        """Load a detached definition and derive current run summaries in the same snapshot."""
        record = connection.execute(select(TaskScheduleModel.record).where(TaskScheduleModel.id == schedule_id)).scalar_one_or_none()
        if record is None:
            raise SchedulerError(scheduler_constants.C_ERROR_NOT_FOUND, C_MESSAGE_NOT_FOUND)
        schedule = ScheduleRecord.model_validate(record)
        if schedule.deleted and not include_deleted:
            raise SchedulerError(scheduler_constants.C_ERROR_NOT_FOUND, C_MESSAGE_NOT_FOUND)
        active = connection.execute(ScheduleQueries.active(schedule_id)).scalar_one_or_none()
        latest = connection.execute(select(TaskRunModel.record).where(
            TaskRunModel.schedule_id == schedule_id,
        ).order_by(TaskRunModel.queued_at.desc(), TaskRunModel.id.desc()).limit(scheduler_constants.C_ONE)).scalar_one_or_none()
        schedule.active_run_id = active[C_ID] if active else None
        schedule.latest_run = RunSummary.model_validate({
            field: latest[field] for field in RunSummary.model_fields
        }) if latest else None
        return schedule

    @staticmethod
    def _revision(schedule, revision):
        """Reject stale writes before any mutation."""
        if schedule.revision != revision:
            raise SchedulerError(scheduler_constants.C_ERROR_REVISION, C_MESSAGE_REVISION,
                                 current_revision=schedule.revision)

    @staticmethod
    def _validate_preference(connection, payload):
        """Check existence and board location rules while holding the write lock."""
        preference = connection.execute(select(JobSearchPreferenceModel.__table__).where(
            JobSearchPreferenceModel.id == payload.preference_id,
        )).mappings().first()
        if preference is None:
            raise SchedulerError(scheduler_constants.C_ERROR_PREFERENCE_MISSING, C_MESSAGE_PREFERENCE)
        preference = JobSearchPreferenceModel.from_record(preference)
        country = JobSearchAdapter.resolve_country(preference.country)
        try:
            for site in payload.sites:
                JobSearchAdapter.validate_country(site, country, preference.country)
        except ValueError as exception:
            raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, str(exception)) from exception

    def _save_schedule(self, connection, schedule):
        """Persist definition and indexed fields together, excluding derived summaries."""
        record = schedule.model_dump(mode=C_JSON_MODE)
        values = {field: record[field] for field in C_SCHEDULE_FIELDS}
        values.update(preference_id=None if schedule.deleted else schedule.payload.preference_id,
                      next_run_at=self._stamp(schedule.next_run_at), record=record)
        connection.execute(update(TaskScheduleModel).where(TaskScheduleModel.id == schedule.id).values(**values))

    def _save_run(self, connection, run):
        """Update JSON and relational state atomically, preserving unique-index enforcement."""
        record = run.model_dump(mode=C_JSON_MODE)
        values = {field: record[field] for field in C_RUN_FIELDS}
        for field in C_RUN_TIMESTAMP_FIELDS:
            values[field] = self._stamp(getattr(run, field))
        values[C_RECORD] = record
        connection.execute(update(TaskRunModel).where(TaskRunModel.id == run.id).values(**values))

    def _new_run(self, connection, schedule, now, source, **fields):
        """Insert an execution and snapshot with identity allocated by SQLite."""
        snapshot = ClaimSnapshot(**schedule.model_dump(include=C_DEFINITION_FIELDS),
                                 schedule_id=schedule.id, revision=schedule.revision)
        run = RunRecord(id=scheduler_constants.C_ONE, schedule_id=schedule.id,
                        revision=schedule.revision, source=source, queued_at=now,
                        claim_snapshot=snapshot, **fields)
        record = run.model_dump(mode=C_JSON_MODE)
        values = {field: record[field] for field in C_RUN_FIELDS}
        for field in C_RUN_TIMESTAMP_FIELDS:
            values[field] = self._stamp(getattr(run, field))
        result = connection.execute(insert(TaskRunModel).values(**values, record=record))
        run.id = result.inserted_primary_key[scheduler_constants.C_ZERO]
        self._save_run(connection, run)
        return run

    def _run(self, connection, run_id):
        """Load and validate a retained execution snapshot."""
        record = connection.execute(select(TaskRunModel.record).where(TaskRunModel.id == run_id)).scalar_one_or_none()
        if record is None:
            raise SchedulerError(scheduler_constants.C_ERROR_NOT_FOUND, C_MESSAGE_NOT_FOUND)
        return RunRecord.model_validate(record)

    def create(self, request, now):
        """Revalidate future time, live preference and maximum count under one writer lock."""
        with self.transaction(True) as connection:
            try:
                request.require_future_anchor(now)
            except ValueError as exception:
                raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, scheduler_constants.C_FUTURE_ERROR) from exception
            self._validate_preference(connection, request.payload)
            count = connection.execute(select(func.count()).select_from(TaskScheduleModel).where(
                TaskScheduleModel.deleted.is_(False))).scalar_one()
            if count >= scheduler_constants.C_MAX_SCHEDULES:
                raise SchedulerError(scheduler_constants.C_ERROR_LIMIT, C_MESSAGE_LIMIT)
            schedule = ScheduleRecord(**request.model_dump(), id=scheduler_constants.C_ONE,
                                      revision=scheduler_constants.C_ONE, enabled=True,
                                      next_run_at=TriggerCalculator.anchor(request.trigger), created_at=now, updated_at=now)
            result = connection.execute(insert(TaskScheduleModel).values(
                preference_id=request.payload.preference_id, revision=schedule.revision,
                enabled=True, deleted=False, next_run_at=self._stamp(schedule.next_run_at),
                record=schedule.model_dump(mode=C_JSON_MODE)))
            schedule.id = result.inserted_primary_key[scheduler_constants.C_ZERO]
            self._save_schedule(connection, schedule)
            return schedule

    def get(self, schedule_id):
        """Read a live schedule with consistent active/latest execution summaries."""
        with self.transaction() as connection:
            return self._schedule(connection, schedule_id)

    @staticmethod
    def _page(items, total, pagination):
        """Build the frozen page envelope, including zero pages for empty collections."""
        return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size,
                    total_pages=(total + pagination.page_size - scheduler_constants.C_ONE) // pagination.page_size)

    def list_schedules(self, pagination):
        """Read stable ID-ordered schedules and totals in one transaction."""
        with self.transaction() as connection:
            query = select(TaskScheduleModel.id).where(TaskScheduleModel.deleted.is_(False))
            total = connection.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            identifiers = connection.execute(query.order_by(TaskScheduleModel.id).limit(pagination.page_size).offset(
                (pagination.page - scheduler_constants.C_ONE) * pagination.page_size)).scalars()
            return self._page([self._schedule(connection, identifier) for identifier in identifiers], total, pagination)

    def replace(self, schedule_id, request, now):
        """Replace editable fields while preserving unchanged recurrence and enabled state."""
        with self.transaction(True) as connection:
            schedule = self._schedule(connection, schedule_id)
            self._revision(schedule, request.revision)
            self._validate_preference(connection, request.payload)
            try:
                request.validate_against(schedule, now)
            except ValueError as exception:
                raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, scheduler_constants.C_FUTURE_ERROR) from exception
            if request.trigger != schedule.trigger and schedule.enabled:
                schedule.next_run_at = TriggerCalculator.anchor(request.trigger)
            for field in C_DEFINITION_FIELDS:
                setattr(schedule, field, getattr(request, field))
            schedule.revision += scheduler_constants.C_ONE
            schedule.updated_at = now
            self._save_schedule(connection, schedule)
            return schedule

    def set_enabled(self, schedule_id, revision, enabled, now):
        """Pause or resume with optimistic revision checking and no catch-up replay."""
        with self.transaction(True) as connection:
            schedule = self._schedule(connection, schedule_id)
            self._revision(schedule, revision)
            if enabled and not schedule.enabled:
                following = TriggerCalculator.future(schedule.trigger, now)
                if following <= now:
                    raise SchedulerError(scheduler_constants.C_ERROR_VALIDATION, scheduler_constants.C_FUTURE_ERROR)
                schedule.next_run_at = following
            if not enabled:
                schedule.next_run_at = None
            schedule.enabled = enabled
            schedule.revision += scheduler_constants.C_ONE
            schedule.updated_at = now
            self._save_schedule(connection, schedule)
            return schedule

    def tombstone(self, schedule_id, revision, now):
        """Clear live preference references while retaining historical snapshots."""
        with self.transaction(True) as connection:
            schedule = self._schedule(connection, schedule_id)
            self._revision(schedule, revision)
            schedule.enabled = False
            schedule.deleted = True
            schedule.next_run_at = None
            schedule.revision += scheduler_constants.C_ONE
            schedule.updated_at = now
            self._save_schedule(connection, schedule)

    def referencing_schedule_ids(self, preference_id):
        """List live references for advisory display; deletion uses its own transaction."""
        with self.transaction() as connection:
            return list(connection.execute(ScheduleQueries.references(preference_id)).scalars())

    def request_manual(self, schedule_id, request, now):
        """Deduplicate retained keys before checking revision or active work."""
        with self.transaction(True) as connection:
            schedule = self._schedule(connection, schedule_id)
            record = connection.execute(select(TaskRunModel.record).where(
                TaskRunModel.schedule_id == schedule_id, TaskRunModel.idempotency_key == request.idempotency_key,
            )).scalar_one_or_none()
            if record is not None:
                run = RunRecord.model_validate(record)
                if run.revision != request.revision:
                    raise SchedulerError(scheduler_constants.C_ERROR_IDEMPOTENCY, C_MESSAGE_KEY)
                return run, True
            self._revision(schedule, request.revision)
            if schedule.active_run_id is not None:
                raise SchedulerError(scheduler_constants.C_ERROR_ACTIVE_RUN, C_MESSAGE_ACTIVE)
            return self._new_run(connection, schedule, now, scheduler_constants.C_SOURCE_MANUAL,
                                 state=scheduler_constants.C_RUN_QUEUED, idempotency_key=request.idempotency_key,
                                 expires_at=now + timedelta(seconds=scheduler_constants.C_MANUAL_EXPIRY_SECONDS)), False

    def get_run(self, run_id):
        """Read a retained run even if its schedule has been tombstoned."""
        with self.transaction() as connection:
            return self._run(connection, run_id)

    def list_runs(self, schedule_id, pagination):
        """Read newest-first history and count including tombstoned schedules."""
        with self.transaction() as connection:
            self._schedule(connection, schedule_id, True)
            query = select(TaskRunModel.record).where(TaskRunModel.schedule_id == schedule_id)
            total = connection.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            records = connection.execute(query.order_by(TaskRunModel.queued_at.desc(), TaskRunModel.id.desc()).limit(
                pagination.page_size).offset((pagination.page - scheduler_constants.C_ONE) * pagination.page_size)).scalars()
            return self._page([RunRecord.model_validate(record) for record in records], total, pagination)

    def list_due(self, now, limit):
        """Read due definitions without taking ownership of executor capacity."""
        with self.transaction() as connection:
            identifiers = connection.execute(select(TaskScheduleModel.id).where(
                TaskScheduleModel.enabled.is_(True), TaskScheduleModel.deleted.is_(False),
                TaskScheduleModel.next_run_at <= self._stamp(now),
            ).order_by(TaskScheduleModel.next_run_at, TaskScheduleModel.id).limit(limit)).scalars()
            return [self._schedule(connection, identifier) for identifier in identifiers]

    def list_queued_manual(self, now, limit):
        """Read unowned, unexpired manual requests in FIFO order."""
        with self.transaction() as connection:
            records = connection.execute(select(TaskRunModel.record).where(
                TaskRunModel.source == scheduler_constants.C_SOURCE_MANUAL,
                TaskRunModel.state == scheduler_constants.C_RUN_QUEUED,
                TaskRunModel.owner_token.is_(None), TaskRunModel.expires_at > self._stamp(now),
            ).order_by(TaskRunModel.queued_at, TaskRunModel.id).limit(limit)).scalars()
            return [RunRecord.model_validate(record) for record in records]

    def claim_timed(self, claim, owner_token, now):
        """Recalculate and compare under lock, then snapshot/advance/claim atomically."""
        with self.transaction(True) as connection:
            schedule = self._schedule(connection, claim.schedule_id, True)
            if (schedule.deleted or not schedule.enabled or schedule.revision != claim.revision
                    or schedule.next_run_at != claim.expected_next_run_at or schedule.next_run_at > now):
                return None
            actual = TriggerCalculator.due(schedule, now)
            if actual != claim:
                return None
            terminal = claim.disposition != scheduler_constants.C_RUN_QUEUED
            run = self._new_run(connection, schedule, now, scheduler_constants.C_SOURCE_TIMED,
                                state=claim.disposition, scheduled_for=claim.scheduled_for,
                                owner_token=owner_token, skipped_count=claim.skipped_count,
                                finished_at=now if terminal else None)
            schedule.next_run_at = claim.next_run_at
            if terminal and claim.next_run_at is None:
                schedule.enabled = False
            self._save_schedule(connection, schedule)
            return run

    def claim_manual(self, run_id, owner_token, now):
        """Assign only unowned current manual requests; final invocation still has a gate."""
        with self.transaction(True) as connection:
            run = self._run(connection, run_id)
            if (run.source != scheduler_constants.C_SOURCE_MANUAL or run.state != scheduler_constants.C_RUN_QUEUED
                    or run.owner_token is not None or run.expires_at <= now):
                return None
            run.owner_token = owner_token
            self._save_run(connection, run)
            return run

    @staticmethod
    def _owned(run, owner_token, states):
        """Fence stale worker transitions even after a later process recovered ownership."""
        if run.owner_token != owner_token or run.state not in states:
            raise SchedulerError(scheduler_constants.C_ERROR_ACTIVE_RUN, C_MESSAGE_ACTIVE)

    def _terminate(self, connection, run, now, state, code, message):
        """Persist a terminal non-handler outcome and its safe diagnostic."""
        run.state = state
        run.finished_at = now
        run.error = self._error(code, message)
        self._save_run(connection, run)
        return run

    def start_run(self, run_id, owner_token, now):
        """Atomically cancel invalidated work or enter running immediately before execution."""
        with self.transaction(True) as connection:
            run = self._run(connection, run_id)
            self._owned(run, owner_token, {scheduler_constants.C_RUN_QUEUED})
            schedule = self._schedule(connection, run.schedule_id, True)
            if run.expires_at is not None and now >= run.expires_at:
                return self._terminate(connection, run, now, scheduler_constants.C_RUN_MISSED,
                                       scheduler_constants.C_ERROR_EXPIRED, C_MESSAGE_EXPIRED)
            if (schedule.deleted or schedule.revision != run.revision
                    or (run.source == scheduler_constants.C_SOURCE_TIMED and not schedule.enabled)):
                return self._terminate(connection, run, now, scheduler_constants.C_RUN_CANCELLED,
                                       scheduler_constants.C_ERROR_INVALIDATED, C_MESSAGE_CANCELLED)
            run.state = scheduler_constants.C_RUN_RUNNING
            run.started_at = now
            self._save_run(connection, run)
            return run

    def record_effective_preference(self, run_id, owner_token, preference: PreferenceSnapshot, now):
        """Persist the exact criteria used by the handler once before any network work."""
        with self.transaction(True) as connection:
            run = self._run(connection, run_id)
            self._owned(run, owner_token, {scheduler_constants.C_RUN_RUNNING})
            if run.effective_preference is not None and run.effective_preference != preference:
                raise SchedulerError(scheduler_constants.C_ERROR_ACTIVE_RUN, C_MESSAGE_ACTIVE)
            run.effective_preference = preference.model_copy(deep=True)
            self._save_run(connection, run)

    def complete(self, run_id, owner_token, result, now):
        """Persist an owned result; consume only the current revision's timed one-shot."""
        with self.transaction(True) as connection:
            run = self._run(connection, run_id)
            if run.state in scheduler_constants.C_TERMINAL_STATES and run.owner_token == owner_token and run.result == result:
                return run
            self._owned(run, owner_token, {scheduler_constants.C_RUN_RUNNING})
            run.state = result.state
            run.result = result.model_copy(deep=True)
            run.error = result.error
            run.finished_at = now
            self._save_run(connection, run)
            schedule = self._schedule(connection, run.schedule_id, True)
            if (run.source == scheduler_constants.C_SOURCE_TIMED and schedule.revision == run.revision
                    and schedule.trigger.kind == scheduler_constants.C_TRIGGER_ONCE):
                schedule.enabled = False
                schedule.next_run_at = None
                self._save_schedule(connection, schedule)
            return run

    def cancel_submission(self, run_id, owner_token, now):
        """Make executor rejection terminal without rewinding the claimed occurrence."""
        with self.transaction(True) as connection:
            run = self._run(connection, run_id)
            self._owned(run, owner_token, {scheduler_constants.C_RUN_QUEUED})
            return self._terminate(connection, run, now, scheduler_constants.C_RUN_CANCELLED,
                                   scheduler_constants.C_ERROR_SUBMISSION, C_MESSAGE_SUBMISSION)

    def expire_manual(self, now, limit):
        """Expire a bounded queue batch even while all executor slots are occupied."""
        with self.transaction(True) as connection:
            identifiers = list(connection.execute(select(TaskRunModel.id).where(
                TaskRunModel.state == scheduler_constants.C_RUN_QUEUED,
                TaskRunModel.source == scheduler_constants.C_SOURCE_MANUAL,
                TaskRunModel.expires_at <= self._stamp(now),
            ).order_by(TaskRunModel.expires_at, TaskRunModel.id).limit(limit)).scalars())
            for identifier in identifiers:
                self._terminate(connection, self._run(connection, identifier), now, scheduler_constants.C_RUN_MISSED,
                                scheduler_constants.C_ERROR_EXPIRED, C_MESSAGE_EXPIRED)
            return len(identifiers)

    def recover(self, worker, now):
        """Under the singleton lock, interrupt old owned work and replace health ownership."""
        with self.transaction(True) as connection:
            identifiers = list(connection.execute(select(TaskRunModel.id).where(
                TaskRunModel.state.in_(scheduler_constants.C_ACTIVE_STATES),
                TaskRunModel.owner_token.is_not(None), TaskRunModel.owner_token != worker.owner_token,
            )).scalars())
            for identifier in identifiers:
                run = self._run(connection, identifier)
                self._terminate(connection, run, now, scheduler_constants.C_RUN_INTERRUPTED,
                                scheduler_constants.C_ERROR_INTERRUPTED, C_MESSAGE_INTERRUPTED)
                schedule = self._schedule(connection, run.schedule_id, True)
                if (run.source == scheduler_constants.C_SOURCE_TIMED and schedule.revision == run.revision
                        and schedule.trigger.kind == scheduler_constants.C_TRIGGER_ONCE):
                    schedule.enabled = False
                    self._save_schedule(connection, schedule)
            connection.execute(delete(SchedulerWorkerModel))
            record = worker.model_dump(mode=C_JSON_MODE)
            record.update({C_HEARTBEAT: None, C_STOPPED: None})
            connection.execute(insert(SchedulerWorkerModel).values(
                id=scheduler_constants.C_ONE, owner_token=worker.owner_token, record=record))
            return len(identifiers)

    def _worker_update(self, owner_token, field, now):
        """Update only the currently registered worker's health metadata."""
        with self.transaction(True) as connection:
            predicate = SchedulerWorkerModel.owner_token == owner_token
            record = connection.execute(select(SchedulerWorkerModel.record).where(predicate)).scalar_one_or_none()
            if record is not None:
                record[field] = self._stamp(now)
                connection.execute(update(SchedulerWorkerModel).where(predicate).values(record=record))

    def heartbeat(self, owner_token, now):
        """Refresh health only after successful dispatch progress."""
        self._worker_update(owner_token, C_HEARTBEAT, now)

    def stop_worker(self, owner_token, now):
        """Mark this owner stopped after its executor has drained."""
        self._worker_update(owner_token, C_STOPPED, now)

    def worker_status(self, now):
        """Compute stopped/stale/fresh independently of whether there are schedules."""
        with self.transaction() as connection:
            record = connection.execute(select(SchedulerWorkerModel.record)).scalar_one_or_none()
            counts = dict(connection.execute(select(TaskRunModel.state, func.count()).where(
                TaskRunModel.state.in_(scheduler_constants.C_ACTIVE_STATES)).group_by(TaskRunModel.state)).all())
            state = scheduler_constants.C_WORKER_STOPPED
            heartbeat = UtcTimestampCodec.parse(record[C_HEARTBEAT]) if record and record[C_HEARTBEAT] else None
            if record and not record[C_STOPPED]:
                state = scheduler_constants.C_WORKER_STALE
                if heartbeat and (now - heartbeat).total_seconds() <= scheduler_constants.C_FRESHNESS_SECONDS:
                    state = scheduler_constants.C_WORKER_FRESH
            return WorkerStatus(state=state, heartbeat_at=heartbeat,
                                started_at=record[C_STARTED] if record else None,
                                stopped_at=record[C_STOPPED] if record else None,
                                queued_count=counts.get(scheduler_constants.C_RUN_QUEUED, scheduler_constants.C_ZERO),
                                running_count=counts.get(scheduler_constants.C_RUN_RUNNING, scheduler_constants.C_ZERO))

    def prune_terminal(self, before, limit):
        """Delete bounded oldest terminal history; retained keys define the dedupe window."""
        with self.transaction(True) as connection:
            identifiers = select(TaskRunModel.id).where(
                TaskRunModel.state.in_(scheduler_constants.C_TERMINAL_STATES),
                TaskRunModel.finished_at < self._stamp(before),
            ).order_by(TaskRunModel.finished_at, TaskRunModel.id).limit(limit)
            return connection.execute(delete(TaskRunModel).where(TaskRunModel.id.in_(identifiers))).rowcount

    def get_board_cooldown(self, site):
        """Read a persisted cooldown without keeping a transaction open during scraping."""
        with self.transaction() as connection:
            deadline = connection.execute(select(JobBoardStateModel.cooldown_until).where(JobBoardStateModel.site == site)).scalar_one_or_none()
            return UtcTimestampCodec.parse(deadline) if deadline else None

    def extend_board_cooldown(self, site, until):
        """Extend but never shorten a persisted rate-limit deadline."""
        with self.transaction(True) as connection:
            predicate = JobBoardStateModel.site == site
            current = connection.execute(select(JobBoardStateModel.cooldown_until).where(predicate)).scalar_one_or_none()
            deadline = self._stamp(until)
            if current is None:
                connection.execute(insert(JobBoardStateModel).values(site=site, cooldown_until=deadline))
            elif current < deadline:
                connection.execute(update(JobBoardStateModel).where(predicate).values(cooldown_until=deadline))

    def close(self):
        """Dispose connection resources without changing durable ownership."""
        self.engine.dispose()
