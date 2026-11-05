"""Serialized lifecycle commands, health inspection, and foreground supervision."""

from contextlib import contextmanager
import secrets
import signal
from threading import Event
import time

import httpx
import portalocker
import psutil

from . import constants as constants
from .models import ProcessRecord, ServiceStatus
from .output import LauncherOutput
from .processes import create_process_controller
from .services import ServiceRegistry


class ServiceManager:
    """Coordinate registered processes without taking ownership of manually started services."""

    def __init__(self, configuration, registry=None, controller=None, output=None):
        """Inject registry and OS process behavior for deterministic verification."""
        self.configuration = configuration
        self.registry = registry or ServiceRegistry()
        self.controller = controller or create_process_controller()
        self.output = output or LauncherOutput(self.registry.definitions)
        self.children = []

    @contextmanager
    def lifecycle_lock(self, timeout=constants.C_LOCK_TIMEOUT):
        """Serialize mutations while allowing read-only status in another terminal."""
        self.configuration.state_directory.mkdir(parents=True, exist_ok=True, mode=constants.C_DIRECTORY_MODE)
        lock_path = self.configuration.state_directory / constants.C_LOCK_FILENAME
        with portalocker.Lock(lock_path, mode=constants.C_LOCK_MODE, timeout=timeout):
            yield

    def record(self, name):
        """Read an optional service record without creating or cleaning state files."""
        path = self.configuration.state_path(name)
        try:
            record = ProcessRecord.read(path)
        except FileNotFoundError:
            return None
        if record.name != name:
            raise ValueError(constants.C_STATE_ERROR.format(path=path))
        return record

    def _request(self, record, path, method=constants.C_GET):
        """Contact only the stored loopback endpoint, bypassing ambient proxy settings."""
        headers = {constants.C_AUTHORIZATION: constants.C_BEARER.format(token=record.control_secret)}
        with httpx.Client(timeout=constants.C_CONTROL_TIMEOUT, trust_env=False) as client:
            response = client.request(method, constants.C_CONTROL_URL.format(port=record.control_port, path=path),
                                      headers=headers)
            response.raise_for_status()
            return response.json()

    def status(self, name):
        """Report stopped, starting, healthy, unhealthy, or unverifiable ownership."""
        try:
            record = self.record(name)
            if record is None or self.controller.identify(record) is None:
                return ServiceStatus(name, constants.C_STOPPED, detail=constants.C_NOT_MANAGED)
            try:
                payload = self._request(record, constants.C_STATUS_PATH)
                if payload[constants.C_FIELD_TOKEN] != record.token or payload[constants.C_FIELD_PID] != record.pid:
                    raise ValueError(constants.C_IDENTITY_ERROR)
                return ServiceStatus(name, payload[constants.C_FIELD_STATE], payload[constants.C_FIELD_HEALTH], record.pid)
            except (httpx.HTTPError, ValueError, KeyError):
                return ServiceStatus(name, constants.C_UNHEALTHY, pid=record.pid, detail=constants.C_CONTROL_ERROR)
        except (OSError, ValueError, psutil.Error) as exception:
            return ServiceStatus(name, constants.C_UNKNOWN, detail=str(exception))

    def start(self, name):
        """Start a missing service and wait for application readiness within a deadline."""
        status = self.status(name)
        if status.state == constants.C_RUNNING:
            return constants.C_ALREADY_RUNNING
        if status.state != constants.C_STOPPED:
            raise RuntimeError(constants.C_IDENTITY_ERROR if status.state == constants.C_UNKNOWN else status.state)
        token = secrets.token_hex(constants.C_TOKEN_BYTES)
        log_path = self.configuration.log_path(name)
        with log_path.open(constants.C_APPEND_BINARY_MODE) as log_stream:
            child = self.controller.spawn(name, token, log_stream)
        self.children.append(child)
        deadline = time.monotonic() + self.configuration.start_timeout
        while time.monotonic() < deadline:
            record = self.record(name)
            if record is not None and record.token == token:
                status = self.status(name)
                if status.state == constants.C_RUNNING:
                    return constants.C_RUNNING
            if child.poll() is not None:
                break
            time.sleep(constants.C_POLL_SECONDS)
        # Retain a still-starting owned process for explicit inspection/stop; do not
        # unexpectedly kill a service whose initialization is merely taking longer.
        raise RuntimeError(constants.C_START_FAILED.format(path=log_path))

    def stop(self, name, force=False):
        """Request graceful draining, then force only when explicitly selected."""
        record = self.record(name)
        if record is None or self.controller.identify(record) is None:
            return constants.C_STOPPED
        try:
            self._request(record, constants.C_STOP_PATH, constants.C_POST)
        except (httpx.HTTPError, ValueError):
            if not force:
                raise RuntimeError(constants.C_CONTROL_ERROR)
        deadline = time.monotonic() + self.configuration.stop_timeout
        while time.monotonic() < deadline:
            if self.controller.identify(record) is None:
                self._reap_children()
                return constants.C_STOPPED
            time.sleep(constants.C_POLL_SECONDS)
        if not force:
            raise RuntimeError(constants.C_STOP_TIMEOUT)
        # Persist intentional termination even if the unresponsive control endpoint
        # could not do so, allowing foreground supervision to distinguish a crash.
        record.stop_requested = True
        record.write(self.configuration.state_path(name))
        self.controller.force_stop(record)
        self._reap_children()
        return constants.C_STOPPED

    def _reap_children(self):
        """Reap exited subprocesses when the launcher remains as a foreground supervisor."""
        self.children = [child for child in self.children if child.poll() is None]

    def execute(self, action, names, force=False):
        """Report every selected service result and preserve successful partial starts."""
        succeeded = True
        ordered_names = self.registry.ordered(names)
        with self.lifecycle_lock():
            stopped_names = set()
            if action in (constants.C_STOP, constants.C_RESTART):
                for name in reversed(ordered_names):
                    try:
                        detail = self.stop(name, force)
                        stopped_names.add(name)
                        self.output.result(name, detail)
                    except (OSError, ValueError, RuntimeError, psutil.Error) as exception:
                        succeeded = False
                        self.output.result(name, exception)
            if action in (constants.C_START, constants.C_RESTART):
                for name in ordered_names:
                    if action == constants.C_RESTART and name not in stopped_names:
                        continue
                    try:
                        for dependency in self.registry.definitions[name].dependencies:
                            if self.status(dependency).state != constants.C_RUNNING:
                                raise RuntimeError(dependency)
                        detail = self.start(name)
                        self.output.result(name, detail)
                    except (OSError, ValueError, RuntimeError, psutil.Error) as exception:
                        succeeded = False
                        self.output.result(name, exception)
        return constants.C_SUCCESS if succeeded else constants.C_FAILURE

    def supervise(self, names):
        """Own fresh services until requested shutdown or an unexpected service exit."""
        stop_requested = Event()
        previous_handlers = {}
        owned_records = {}
        exit_code = constants.C_SUCCESS

        def request_stop(signal_number, frame):
            """Defer signal handling to the supervisor loop and normal service drain path."""
            stop_requested.set()

        try:
            for signal_number in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signal_number] = signal.signal(signal_number, request_stop)
            with self.lifecycle_lock():
                if any(self.status(name).state != constants.C_STOPPED for name in names):
                    raise RuntimeError(constants.C_FOREGROUND_OWNERSHIP_ERROR)
                for name in names:
                    if stop_requested.is_set():
                        break
                    try:
                        detail = self.start(name)
                        self.output.result(name, detail)
                    finally:
                        record = self.record(name)
                        if record is not None:
                            owned_records[name] = record
            while not stop_requested.wait(constants.C_SUPERVISOR_POLL_SECONDS):
                self._reap_children()
                try:
                    # Inspect only between commands, so an intentional restart's
                    # temporary downtime is never mistaken for a service crash.
                    with self.lifecycle_lock(timeout=constants.C_ZERO):
                        active_records = []
                        for name in owned_records:
                            current_record = self.record(name)
                            if current_record is None:
                                exit_code = constants.C_FAILURE
                                stop_requested.set()
                                break
                            if self.controller.identify(current_record) is not None:
                                owned_records[name] = current_record
                                active_records.append(current_record)
                            elif not current_record.stop_requested:
                                self.output.result(name, constants.C_UNEXPECTED_EXIT)
                                exit_code = constants.C_FAILURE
                                stop_requested.set()
                                break
                        if not active_records:
                            stop_requested.set()
                except portalocker.exceptions.LockException:
                    continue
        finally:
            try:
                cleanup_timeout = len(names) * (self.configuration.start_timeout + self.configuration.stop_timeout)
                with self.lifecycle_lock(timeout=cleanup_timeout + constants.C_LOCK_TIMEOUT):
                    for name in reversed(tuple(owned_records)):
                        try:
                            current_record = self.record(name)
                            if current_record is not None:
                                self.stop(name)
                        except (OSError, RuntimeError, ValueError, psutil.Error) as exception:
                            self.output.result(name, exception)
                            exit_code = constants.C_FAILURE
                self._reap_children()
            finally:
                for signal_number, previous_handler in previous_handlers.items():
                    signal.signal(signal_number, previous_handler)
        return exit_code
