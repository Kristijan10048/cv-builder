"""Shared OS-backed locks for processes using one local application database."""

from dataclasses import replace
from pathlib import Path

import portalocker

from .scheduler.configuration import SchedulerConfiguration
from .scheduler import constants as scheduler_constants

C_LOCK_MODE = "a"


class DatabaseLock:
    """Retain an exclusive file handle; never unlink a potentially owned lock file."""

    def __init__(self, configuration: SchedulerConfiguration, purpose: str,
                 timeout: int = scheduler_constants.C_ZERO) -> None:
        """Configure nonblocking ownership or bounded migration-lock retry."""
        self.path = configuration.lock_path(purpose)
        self.timeout = timeout
        self.lock = None

    def __enter__(self):
        """Create the lock directory and acquire the operating-system lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = portalocker.Lock(
            str(self.path), mode=C_LOCK_MODE, timeout=self.timeout,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )
        self.lock.acquire()
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        """Release ownership even when protected startup or execution fails."""
        if self.lock is not None:
            self.lock.release()


def configuration_for_database(database_path: Path) -> SchedulerConfiguration:
    """Respect explicit connection paths, including disposable test databases."""
    return replace(SchedulerConfiguration.from_environment(), database_path=Path(database_path).resolve())
