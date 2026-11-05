"""Private service runner with authenticated loopback lifecycle control."""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import signal
from threading import Lock, Thread

import portalocker
import psutil

from . import constants as constants
from .models import LauncherConfiguration, ProcessRecord
from .services import ServiceRegistry


class ServiceControlServer(ThreadingHTTPServer):
    """Expose a per-launch secret-protected endpoint on an ephemeral loopback port."""

    daemon_threads = True

    def __init__(self, configuration, name, token):
        """Publish process identity before loading the potentially slow service adapter."""
        super().__init__((constants.C_DEFAULT_HOST, constants.C_EPHEMERAL_PORT), ServiceControlHandler)
        self.configuration = configuration
        self.runtime = None
        self.state_lock = Lock()
        self.record = ProcessRecord(name, os.getpid(), psutil.Process().create_time(), token,
                                    self.server_address[constants.C_ONE], secrets.token_hex(constants.C_TOKEN_BYTES))
        self.record.write(configuration.state_path(name))

    def request_stop(self, signal_number=None, frame=None):
        """Persist intentional stop before asking the application to drain work."""
        with self.state_lock:
            self.record.stop_requested = True
            self.record.write(self.configuration.state_path(self.record.name))
            if self.runtime is not None:
                self.runtime.request_stop()

    def status(self):
        """Return verifiable identity plus application health without changing storage."""
        state, health = constants.C_STARTING, constants.C_UNAVAILABLE
        if self.runtime is not None:
            try:
                state, health = self.runtime.health()
            except Exception:
                state, health = constants.C_UNHEALTHY, constants.C_UNAVAILABLE
        if self.record.stop_requested:
            state = constants.C_STOPPING
        return {constants.C_FIELD_TOKEN: self.record.token, constants.C_FIELD_PID: self.record.pid,
                constants.C_FIELD_STATE: state, constants.C_FIELD_HEALTH: health}


class ServiceControlHandler(BaseHTTPRequestHandler):
    """Handle authenticated status and POST-only shutdown requests without access logs."""

    def _authorized(self):
        """Compare secrets in constant time and reject unauthenticated local callers."""
        supplied = self.headers.get(constants.C_AUTHORIZATION, constants.C_EMPTY)
        expected = constants.C_BEARER.format(token=self.server.record.control_secret)
        return hmac.compare_digest(supplied, expected)

    def _respond(self, code, payload):
        """Write a bounded JSON response and close broken client connections quietly."""
        encoded = json.dumps(payload).encode(constants.C_ENCODING)
        try:
            self.send_response(code)
            self.send_header(constants.C_CONTENT_TYPE, constants.C_JSON_CONTENT_TYPE)
            self.send_header(constants.C_CONTENT_LENGTH, str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        """Expose status only to the holder of this service instance's secret."""
        if not self._authorized():
            self._respond(constants.C_HTTP_FORBIDDEN, {})
        elif self.path == constants.C_STATUS_PATH:
            self._respond(constants.C_HTTP_OK, self.server.status())
        else:
            self._respond(constants.C_HTTP_NOT_FOUND, {})

    def do_POST(self):
        """Accept cooperative shutdown only on the dedicated authenticated route."""
        if not self._authorized():
            self._respond(constants.C_HTTP_FORBIDDEN, {})
        elif self.path == constants.C_STOP_PATH:
            self.server.request_stop()
            self._respond(constants.C_HTTP_OK, {constants.C_FIELD_ACCEPTED: True})
        else:
            self._respond(constants.C_HTTP_NOT_FOUND, {})

    def log_message(self, format_string, *arguments):
        """Avoid exposing control requests or credentials in application logs."""


class ServiceRunner:
    """Hold singleton ownership and execute one registered application in the foreground."""

    def run(self, name, token):
        """Serve control requests throughout startup and stop through the service adapter."""
        configuration = LauncherConfiguration.from_environment()
        runtime_lock = configuration.state_directory / constants.C_RUNTIME_LOCK_FILENAME.format(name=name)
        with portalocker.Lock(runtime_lock, mode=constants.C_LOCK_MODE, timeout=constants.C_ZERO):
            with ServiceControlServer(configuration, name, token) as control:
                control_thread = Thread(target=control.serve_forever, daemon=True)
                control_thread.start()
                previous_handlers = {}
                try:
                    for signal_number in (signal.SIGINT, signal.SIGTERM):
                        previous_handlers[signal_number] = signal.signal(signal_number, control.request_stop)
                    runtime = ServiceRegistry().definitions[name].runtime_type(configuration)
                    with control.state_lock:
                        control.runtime = runtime
                        if control.record.stop_requested:
                            runtime.request_stop()
                    runtime.run()
                finally:
                    control.shutdown()
                    control_thread.join()
                    for signal_number, previous_handler in previous_handlers.items():
                        signal.signal(signal_number, previous_handler)
        return constants.C_SUCCESS


def main():
    """Parse the internal runner arguments; public users should invoke launcher.py."""
    parser = argparse.ArgumentParser()
    parser.add_argument(constants.C_SERVICE_FLAG, choices=ServiceRegistry().definitions, required=True)
    parser.add_argument(constants.C_TOKEN_FLAG, required=True)
    arguments = parser.parse_args()
    return ServiceRunner().run(arguments.service, arguments.token)


if __name__ == constants.C_MAIN_MODULE:
    raise SystemExit(main())
