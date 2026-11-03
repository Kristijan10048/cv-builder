"""Explicit, side-effect-free settings shared by the web application and worker."""

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import Mapping

from . import constants as scheduler_constants
from .errors import SchedulerConfigurationError

C_ISRESERVED = 'isreserved'


@dataclass(frozen=True)
class SchedulerConfiguration:
    """Resolved local paths and bounded worker settings; loading creates no files."""

    database_path: Path
    lock_directory: Path
    log_directory: Path
    max_workers: int
    poll_seconds: int
    retention_days: int

    def __post_init__(self) -> None:
        """Reject path collisions that would make a database file serve as a directory."""
        for directory in (self.lock_directory, self.log_directory):
            if self.database_path == directory or self.database_path in directory.parents:
                raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(
                    name=scheduler_constants.C_ENV_DATABASE_PATH,
                ))

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None, project_root: Path | None = None,
    ) -> "SchedulerConfiguration":
        """Resolve relative paths against the source root, independently of cwd."""
        settings = dict(os.environ if environment is None else environment)
        # Canonical settings win, including invalid values that must be rejected.
        for setting_name, legacy_name in scheduler_constants.C_LEGACY_ENVIRONMENT_NAMES.items():
            if setting_name not in settings and legacy_name in settings:
                settings[setting_name] = settings[legacy_name]
        root = project_root or Path(__file__).resolve().parents[scheduler_constants.C_PROJECT_PARENT_INDEX]
        if not root.is_absolute():
            raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(name=__name__))
        return cls(
            database_path=cls._resolve_path(settings, root, scheduler_constants.C_ENV_DATABASE_PATH,
                                            scheduler_constants.C_DEFAULT_DATABASE_PATH, False),
            lock_directory=cls._resolve_path(settings, root, scheduler_constants.C_ENV_LOCK_DIR,
                                             scheduler_constants.C_DEFAULT_LOCK_DIR, True),
            log_directory=cls._resolve_path(settings, root, scheduler_constants.C_ENV_LOG_DIR,
                                            scheduler_constants.C_DEFAULT_LOG_DIR, True),
            max_workers=cls._read_integer(settings, scheduler_constants.C_ENV_MAX_WORKERS,
                                          scheduler_constants.C_DEFAULT_MAX_WORKERS, scheduler_constants.C_MAX_WORKERS),
            poll_seconds=cls._read_integer(settings, scheduler_constants.C_ENV_POLL_SECONDS,
                                           scheduler_constants.C_DEFAULT_POLL_SECONDS, scheduler_constants.C_MAX_POLL_SECONDS),
            retention_days=cls._read_integer(settings, scheduler_constants.C_ENV_RETENTION_DAYS,
                                             scheduler_constants.C_DEFAULT_RETENTION_DAYS, scheduler_constants.C_MAX_RETENTION_DAYS),
        )

    @staticmethod
    def _resolve_path(settings: Mapping[str, str], root: Path, name: str, default: str, directory: bool) -> Path:
        """Reject blank, ambiguous, network, or wrong-kind paths without creating them."""
        value = settings.get(name, default)
        try:
            if (not isinstance(value, str) or not value.strip() or value != value.strip()
                    or scheduler_constants.C_NUL_CHARACTER in value):
                raise ValueError
            candidate = Path(value)
            # Windows drive-relative/root-relative and UNC paths are not local absolute identities.
            if (candidate.drive or candidate.root) and not candidate.is_absolute():
                raise ValueError
            if value.startswith(scheduler_constants.C_NETWORK_PATH_PREFIXES):
                raise ValueError
            if hasattr(os.path, C_ISRESERVED) and os.path.isreserved(value):
                raise ValueError
            resolved_path = (candidate if candidate.is_absolute() else root / candidate).resolve()
            if resolved_path.exists() and resolved_path.is_dir() != directory:
                raise ValueError
            if any(parent.exists() and not parent.is_dir() for parent in resolved_path.parents):
                raise ValueError
            return resolved_path
        except (OSError, ValueError, RuntimeError) as exception:
            raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(name=name)) from exception

    @staticmethod
    def _read_integer(settings: Mapping[str, str], name: str, default: int, maximum: int) -> int:
        """Accept decimal environment strings only, with explicit operational bounds."""
        value = settings.get(name, str(default))
        if not isinstance(value, str) or re.fullmatch(scheduler_constants.C_INTEGER_PATTERN, value) is None:
            raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(name=name))
        number = int(value)
        if not scheduler_constants.C_ONE <= number <= maximum:
            raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(name=name))
        return number

    @property
    def database_identity(self) -> str:
        """Hash the resolved platform-normalized path so all processes use one identity."""
        normalized_path = os.path.normcase(str(self.database_path.resolve()))
        return sha256(normalized_path.encode(scheduler_constants.C_PATH_ENCODING)).hexdigest()

    def lock_path(self, purpose: str) -> Path:
        """Return separate worker, migration, or board locks keyed by database identity."""
        if re.fullmatch(scheduler_constants.C_LOCK_PURPOSE_PATTERN, purpose) is None:
            raise SchedulerConfigurationError(scheduler_constants.C_CONFIGURATION_ERROR.format(name=purpose))
        filename = scheduler_constants.C_LOCK_FILENAME_TEMPLATE.format(identity=self.database_identity, purpose=purpose)
        return self.lock_directory / filename

    @property
    def log_path(self) -> Path:
        """Return the worker-only log file, distinct from the application log."""
        return self.log_directory / scheduler_constants.C_LOG_FILENAME
