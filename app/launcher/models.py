"""Validated configuration and durable process identity for the launcher."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

from app.scheduler.configuration import SchedulerConfiguration
from . import constants as constants


@dataclass(frozen=True)
class LauncherConfiguration:
    """Resolve launcher settings without creating directories or databases."""

    state_directory: Path
    host: str
    port: int
    start_timeout: float
    stop_timeout: float

    @classmethod
    def from_environment(cls):
        """Validate settings and isolate default process records by database identity."""
        scheduler = SchedulerConfiguration.from_environment()
        default_directory = scheduler.lock_directory / constants.C_DEFAULT_STATE_DIRECTORY / scheduler.database_identity
        state_directory = Path(os.environ.get(constants.C_ENV_STATE_DIR, str(default_directory)))
        if not state_directory.is_absolute():
            state_directory = constants.C_PROJECT_ROOT / state_directory
        host = os.environ.get(constants.C_ENV_HOST, constants.C_DEFAULT_HOST)
        if not host.strip():
            raise ValueError(constants.C_CONFIGURATION_ERROR.format(name=constants.C_ENV_HOST))
        port = cls._number(constants.C_ENV_PORT, constants.C_DEFAULT_PORT, int)
        if port > constants.C_MAX_PORT:
            raise ValueError(constants.C_CONFIGURATION_ERROR.format(name=constants.C_ENV_PORT))
        return cls(
            state_directory.resolve(), host, port,
            cls._number(constants.C_ENV_START_TIMEOUT, constants.C_DEFAULT_START_TIMEOUT, float),
            cls._number(constants.C_ENV_STOP_TIMEOUT, constants.C_DEFAULT_STOP_TIMEOUT, float),
        )

    @staticmethod
    def _number(name, default, converter):
        """Require positive finite timeout and port settings."""
        try:
            value = converter(os.environ.get(name, default))
            if not math.isfinite(value) or value <= constants.C_ZERO:
                raise ValueError
            return value
        except (ValueError, OverflowError) as exception:
            raise ValueError(constants.C_CONFIGURATION_ERROR.format(name=name)) from exception

    def state_path(self, name):
        """Locate one registered service's process record."""
        return self.state_directory / constants.C_STATE_FILENAME.format(name=name)

    def log_path(self, name):
        """Locate captured startup and console diagnostics for a service."""
        return self.state_directory / constants.C_LOG_FILENAME.format(name=name)


@dataclass
class ProcessRecord:
    """Bind a PID to its birth time, service, command nonce, and control endpoint."""

    name: str
    pid: int
    created_at: float
    token: str
    control_port: int
    control_secret: str
    stop_requested: bool = False

    @classmethod
    def read(cls, path):
        """Reject corrupt records rather than guessing which process to control."""
        try:
            record = cls(**json.loads(path.read_text(encoding=constants.C_ENCODING)))
            if (not isinstance(record.pid, int) or record.pid <= constants.C_ZERO
                    or not isinstance(record.created_at, (int, float)) or not math.isfinite(record.created_at)
                    or not isinstance(record.token, str) or not record.token
                    or not isinstance(record.control_secret, str) or not record.control_secret
                    or not isinstance(record.name, str)
                    or not isinstance(record.control_port, int)
                    or not constants.C_ZERO < record.control_port <= constants.C_MAX_PORT
                    or not isinstance(record.stop_requested, bool)):
                raise ValueError
            return record
        except (TypeError, ValueError) as exception:
            raise ValueError(constants.C_STATE_ERROR.format(path=path)) from exception

    def write(self, path):
        """Atomically publish private state so concurrent status never sees partial JSON."""
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=constants.C_TEMP_SUFFIX)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, constants.C_WRITE_MODE, encoding=constants.C_ENCODING) as stream:
                json.dump(asdict(self), stream)
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class ServiceStatus:
    """Separate verified process liveness from readiness and application health."""

    name: str
    state: str
    health: str = constants.C_UNAVAILABLE
    pid: int | None = None
    detail: str = constants.C_EMPTY
