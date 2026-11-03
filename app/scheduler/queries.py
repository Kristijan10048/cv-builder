"""Parameterized scheduler query construction shared with preference deletion."""

from sqlalchemy import select

from .database_models import TaskScheduleModel, TaskRunModel
from . import constants as scheduler_constants


class ScheduleQueries:
    """Keep common predicates consistent across readers and transactional guards."""

    @staticmethod
    def references(preference_id: int):
        """Select live references using the deletion caller's existing transaction."""
        return select(TaskScheduleModel.id).where(
            TaskScheduleModel.preference_id == preference_id,
            TaskScheduleModel.deleted.is_(False),
        ).order_by(TaskScheduleModel.id)

    @staticmethod
    def active(schedule_id: int):
        """Select the unique queued/running execution for a schedule."""
        return select(TaskRunModel.record).where(
            TaskRunModel.schedule_id == schedule_id,
            TaskRunModel.state.in_(scheduler_constants.C_ACTIVE_STATES),
        )
