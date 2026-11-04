"""UTC elapsed-time calculations independent of persistence and wall-clock sleeps."""

from datetime import datetime, timedelta, timezone

from . import constants as scheduler_constants
from .contracts import BaseClock, IntervalTrigger, ScheduleRecord, TimedClaim


class SystemClock(BaseClock):
    """Provide aware UTC instants at explicit lifecycle boundaries."""

    def now(self) -> datetime:
        """Return the current UTC wall-clock instant."""
        return datetime.now(timezone.utc)


class TriggerCalculator:
    """Preserve interval anchors and summarize missed/overlapping occurrences."""

    @staticmethod
    def anchor(trigger) -> datetime:
        """Return the first occurrence of either supported trigger."""
        return trigger.starts_at if isinstance(trigger, IntervalTrigger) else trigger.run_at

    @classmethod
    def future(cls, trigger, now: datetime) -> datetime:
        """Advance an interval strictly past now without replaying paused time."""
        anchor = cls.anchor(trigger)
        if isinstance(trigger, IntervalTrigger) and anchor <= now:
            count = int((now - anchor).total_seconds() // trigger.seconds) + scheduler_constants.C_ONE
            return anchor + timedelta(seconds=count * trigger.seconds)
        return anchor

    @staticmethod
    def due(schedule: ScheduleRecord, now: datetime) -> TimedClaim:
        """Coalesce to the latest due occurrence; active overlap takes precedence over lateness."""
        latest = schedule.next_run_at
        count = scheduler_constants.C_ONE
        following = None
        if isinstance(schedule.trigger, IntervalTrigger):
            count += int((now - latest).total_seconds() // schedule.trigger.seconds)
            latest += timedelta(seconds=(count - scheduler_constants.C_ONE) * schedule.trigger.seconds)
            following = latest + timedelta(seconds=schedule.trigger.seconds)
        disposition = scheduler_constants.C_RUN_QUEUED
        skipped = count - scheduler_constants.C_ONE
        if schedule.active_run_id is not None:
            disposition = scheduler_constants.C_RUN_SKIPPED_OVERLAP
            skipped = count
        elif (now - latest).total_seconds() > scheduler_constants.C_LATENESS_SECONDS:
            disposition = scheduler_constants.C_RUN_MISSED
            skipped = count
        return TimedClaim(
            schedule_id=schedule.id, revision=schedule.revision,
            expected_next_run_at=schedule.next_run_at, scheduled_for=latest,
            next_run_at=following, disposition=disposition, skipped_count=skipped,
        )
