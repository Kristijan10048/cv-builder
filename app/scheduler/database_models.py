"""Mapped durable scheduler records with database-enforced execution uniqueness."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database_models import DatabaseModel
from . import constants as scheduler_constants

C_SCHEDULE_TABLE = "task_schedules"
C_RUN_TABLE = "task_runs"
C_WORKER_TABLE = "scheduler_workers"
C_BOARD_TABLE = "job_board_state"
C_PREFERENCE_REFERENCE = "job_search_preferences.id"
C_SCHEDULE_REFERENCE = "task_schedules.id"
C_RESTRICT = "RESTRICT"
C_AUTOINCREMENT = "sqlite_autoincrement"
C_SCHEDULE_ID = "schedule_id"
C_REVISION = "revision"
C_SCHEDULED_FOR = "scheduled_for"
C_IDEMPOTENCY_KEY = "idempotency_key"
C_ACTIVE_INDEX = "task_runs_one_active"
C_HISTORY_INDEX = "task_runs_history"
C_RETENTION_INDEX = "task_runs_retention"


class TaskScheduleModel(DatabaseModel):
    """Store a detached definition plus indexed eligibility and a live preference FK."""

    __tablename__ = C_SCHEDULE_TABLE
    __table_args__ = {C_AUTOINCREMENT: True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    preference_id: Mapped[int | None] = mapped_column(ForeignKey(C_PREFERENCE_REFERENCE, ondelete=C_RESTRICT))
    revision: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    deleted: Mapped[bool] = mapped_column(Boolean)
    next_run_at: Mapped[str | None] = mapped_column(Text, index=True)
    record: Mapped[dict] = mapped_column(JSON)


class TaskRunModel(DatabaseModel):
    """Keep immutable snapshots and enforce one active execution per schedule."""

    __tablename__ = C_RUN_TABLE
    __table_args__ = (
        UniqueConstraint(C_SCHEDULE_ID, C_REVISION, C_SCHEDULED_FOR),
        UniqueConstraint(C_SCHEDULE_ID, C_IDEMPOTENCY_KEY),
        {C_AUTOINCREMENT: True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    schedule_id: Mapped[int] = mapped_column(ForeignKey(C_SCHEDULE_REFERENCE))
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    scheduled_for: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    owner_token: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[str] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(Text)
    record: Mapped[dict] = mapped_column(JSON)


Index(C_ACTIVE_INDEX, TaskRunModel.schedule_id, unique=True,
      sqlite_where=TaskRunModel.state.in_(scheduler_constants.C_ACTIVE_STATES))
Index(C_HISTORY_INDEX, TaskRunModel.schedule_id, TaskRunModel.queued_at, TaskRunModel.id)
Index(C_RETENTION_INDEX, TaskRunModel.finished_at, TaskRunModel.id)


class SchedulerWorkerModel(DatabaseModel):
    """Maintain one fenced observational health slot per database."""

    __tablename__ = C_WORKER_TABLE
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_token: Mapped[str] = mapped_column(Text)
    record: Mapped[dict] = mapped_column(JSON)


class JobBoardStateModel(DatabaseModel):
    """Persist rate-limit deadlines independently of web and worker lifetimes."""

    __tablename__ = C_BOARD_TABLE
    site: Mapped[str] = mapped_column(Text, primary_key=True)
    cooldown_until: Mapped[str] = mapped_column(Text)


C_SCHEDULER_TABLES = (
    TaskScheduleModel.__table__, TaskRunModel.__table__,
    SchedulerWorkerModel.__table__, JobBoardStateModel.__table__,
)
