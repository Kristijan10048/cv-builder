"""Trusted extensible service registry and cooperative application adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from threading import Event, Thread

import httpx

from . import constants as constants


class BaseServiceRuntime(ABC):
    """Adapt a service to foreground execution, health checks, and graceful stopping."""

    def __init__(self, configuration):
        """Retain configuration and a thread-safe cooperative shutdown request."""
        self.configuration = configuration
        self.stop_requested = Event()

    def request_stop(self):
        """Record shutdown without racing service initialization."""
        self.stop_requested.set()

    @abstractmethod
    def run(self):
        """Run the service on the main thread until shutdown completes."""

    @abstractmethod
    def health(self):
        """Return readiness state and health independently of the web application."""


class WebServiceRuntime(BaseServiceRuntime):
    """Run one Uvicorn server without reload workers or a development supervisor."""

    def __init__(self, configuration):
        """Defer application imports to Uvicorn startup in the managed child."""
        super().__init__(configuration)
        import uvicorn

        self.server = uvicorn.Server(uvicorn.Config(
            constants.C_WEB_APPLICATION, host=configuration.host, port=configuration.port,
            log_level=constants.C_WEB_LOG_LEVEL,
        ))

    def _watch_stop(self):
        """Translate cross-platform control requests to Uvicorn's graceful exit flag."""
        self.stop_requested.wait()
        self.server.should_exit = True

    def run(self):
        """Serve HTTP while a daemon watcher relays cooperative stop requests."""
        Thread(target=self._watch_stop, daemon=True).start()
        self.server.run()

    def health(self):
        """Check completed startup and HTTP responsiveness on the configured port."""
        if not self.server.started:
            return constants.C_STARTING, constants.C_UNAVAILABLE
        host = self.configuration.host
        if host == constants.C_IPV6_WILDCARD:
            host = constants.C_IPV6_LOOPBACK
        elif host in constants.C_WILDCARD_HOSTS:
            host = constants.C_DEFAULT_HOST
        if constants.C_IPV6_SEPARATOR in host:
            host = constants.C_IPV6_HOST.format(host=host)
        try:
            with httpx.Client(timeout=constants.C_CONTROL_TIMEOUT, trust_env=False) as client:
                response = client.get(constants.C_WEB_URL.format(host=host, port=self.configuration.port))
            healthy = response.status_code == constants.C_HTTP_OK
        except httpx.HTTPError:
            healthy = False
        return (constants.C_RUNNING, constants.C_HEALTHY) if healthy else (constants.C_UNHEALTHY, constants.C_STALE)


class SchedulerServiceRuntime(BaseServiceRuntime):
    """Run the existing scheduler and inspect its heartbeat through read-only storage."""

    def __init__(self, configuration):
        """Create the scheduler without opening or migrating its database yet."""
        super().__init__(configuration)
        from app.scheduler.runtime import SchedulerRuntime

        self.runtime = SchedulerRuntime()

    def _watch_stop(self):
        """Wait for scheduler initialization before requesting its normal drain path."""
        self.stop_requested.wait()
        while not self.runtime.scheduler.running:
            Event().wait(constants.C_POLL_SECONDS)
        self.runtime.request_stop()

    def run(self):
        """Retain the scheduler's existing locking, recovery, and shutdown semantics."""
        Thread(target=self._watch_stop, daemon=True).start()
        self.runtime.run()

    def _read_connection(self):
        """Open existing SQLite storage read-only, without PRAGMAs or migrations."""
        database_uri = constants.C_SQLITE_READ_URI.format(uri=self.runtime.configuration.database_path.as_uri())
        return sqlite3.connect(database_uri, uri=True, timeout=constants.C_CONTROL_TIMEOUT)

    def health(self):
        """Read scheduler freshness even when no web process is running."""
        if not self.runtime.scheduler.running:
            return constants.C_STARTING, constants.C_UNAVAILABLE
        from app.scheduler import constants as scheduler_constants
        from app.scheduler.repository import ScheduleRepository

        repository = ScheduleRepository(connection_factory=self._read_connection)
        try:
            status = repository.worker_status(datetime.now(timezone.utc))
            if status.state == scheduler_constants.C_WORKER_FRESH:
                return constants.C_RUNNING, constants.C_HEALTHY
            return constants.C_UNHEALTHY, constants.C_STALE
        finally:
            repository.close()


@dataclass(frozen=True)
class ServiceDefinition:
    """Declare a trusted service adapter and optional startup dependencies."""

    name: str
    runtime_type: type[BaseServiceRuntime]
    dependencies: tuple[str, ...] = ()


class ServiceRegistry:
    """Resolve registered services in dependency order without service-specific CLI code."""

    def __init__(self, definitions=None):
        """Register only the web server and scheduler unless explicitly supplied by code."""
        definitions = definitions if definitions is not None else (
            ServiceDefinition(constants.C_WEB, WebServiceRuntime),
            ServiceDefinition(constants.C_SCHEDULER, SchedulerServiceRuntime),
        )
        self.definitions = {definition.name: definition for definition in definitions}

    def ordered(self, names):
        """Include dependencies and reject cycles or missing service definitions."""
        ordered_names = []
        visiting = set()
        for name in names:
            self._visit(name, visiting, ordered_names)
        return ordered_names

    def _visit(self, name, visiting, ordered_names):
        """Perform dependency traversal once per registered service."""
        if name in ordered_names:
            return
        if name in visiting:
            raise ValueError(name)
        visiting.add(name)
        for dependency in self.definitions[name].dependencies:
            self._visit(dependency, visiting, ordered_names)
        visiting.remove(name)
        ordered_names.append(name)
