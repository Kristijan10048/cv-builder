"""Offline launcher verification using isolated storage and actual managed processes."""

from dataclasses import replace
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
import time
from unittest.mock import Mock

import httpx
import psutil
import pytest

from app.launcher import constants as constants
from app.launcher.cli import LauncherApplication
from app.launcher.manager import ServiceManager
from app.launcher.models import LauncherConfiguration, ProcessRecord
from app.launcher.processes import PosixProcessController, WindowsProcessController, create_process_controller
from app.launcher.runner import ServiceControlServer
from app.launcher.services import ServiceDefinition, ServiceRegistry, WebServiceRuntime

C_TEST_DATABASE = "launcher-test.db"
C_TEST_STATE = "state with spaces"
C_TEST_TOKEN = "test-token"
C_TEST_SECRET = "test-secret"
C_WRONG_TOKEN = "wrong-token"
C_TEST_CREATED_AT = 123.0
C_TEST_PID = 12345
C_TEST_PORT = 12345
C_BAD_PORTS = ("0", "-1", "65536", "abc")
C_BAD_TIMEOUTS = ("0", "-1", "nan", "inf", "abc")
C_CLI_PATH = constants.C_PROJECT_ROOT / "launcher.py"
C_TEST_TIMEOUT = 60
C_TEST_STOP_TIMEOUT = 10
C_SHORT_TIMEOUT = 0.15
C_TEST_DEPENDENT = "dependent"
C_TEST_CYCLE = "cycle"
C_INVALID_JSON = "{invalid"
C_TEST_ARGUMENT_ERROR = 2
C_FOREGROUND_READY_TIMEOUT = 40
C_ENV_DATABASE = "CV_BUILDER_DATABASE_PATH"
C_START_OPTION = "-start"
C_STOP_OPTION = "-stop"
C_STATUS_OPTION = "-status"
C_RESTART_OPTION = "-restart"
C_LONG_START_OPTION = "--start"
C_LONG_STOP_OPTION = "--stop"
C_OMITTED_SERVICE = "jira"
C_PYTEST_VALUE = "value"
C_PYTEST_ARGUMENTS = "arguments"


@pytest.fixture
def launcher_configuration(tmp_path, monkeypatch):
    """Supply isolated absolute paths inherited by every spawned service."""
    monkeypatch.setenv(constants.C_ENV_STATE_DIR, str(tmp_path / C_TEST_STATE))
    monkeypatch.setenv(C_ENV_DATABASE, str(tmp_path / C_TEST_DATABASE))
    monkeypatch.setenv(constants.C_ENV_START_TIMEOUT, str(constants.C_DEFAULT_START_TIMEOUT))
    monkeypatch.setenv(constants.C_ENV_STOP_TIMEOUT, str(C_TEST_STOP_TIMEOUT))
    with socket.socket() as listener:
        listener.bind((constants.C_DEFAULT_HOST, constants.C_EPHEMERAL_PORT))
        monkeypatch.setenv(constants.C_ENV_PORT, str(listener.getsockname()[constants.C_ONE]))
    return LauncherConfiguration.from_environment()


@pytest.fixture
def manager(launcher_configuration):
    """Clean up only test-owned process identities even if an assertion fails."""
    service_manager = ServiceManager(launcher_configuration)
    yield service_manager
    for name in service_manager.registry.definitions:
        record = service_manager.record(name)
        if record is not None:
            service_manager.controller.force_stop(record)
    service_manager._reap_children()


def run_cli(arguments, timeout=C_TEST_TIMEOUT):
    """Invoke the real public CLI in an unrelated working directory."""
    return subprocess.run([sys.executable, str(C_CLI_PATH), *arguments],
                          cwd=Path(sys.executable).parent, capture_output=True, text=True, timeout=timeout)


def wait_for_service(manager, name):
    """Wait for foreground-supervised test startup without touching production storage."""
    deadline = time.monotonic() + C_FOREGROUND_READY_TIMEOUT
    while time.monotonic() < deadline:
        if manager.status(name).state == constants.C_RUNNING:
            return
        time.sleep(constants.C_POLL_SECONDS)
    pytest.fail(constants.C_START_FAILED.format(path=manager.configuration.log_path(name)))


class TestLauncherConfiguration:
    """Exercise input validation and read-only status guarantees."""

    @pytest.mark.parametrize(C_PYTEST_VALUE, C_BAD_PORTS)
    def test_invalid_port(self, launcher_configuration, monkeypatch, value):
        """Reject ports that cannot identify a usable listening endpoint."""
        monkeypatch.setenv(constants.C_ENV_PORT, value)
        with pytest.raises(ValueError):
            LauncherConfiguration.from_environment()

    @pytest.mark.parametrize(C_PYTEST_VALUE, C_BAD_TIMEOUTS)
    def test_invalid_timeout(self, launcher_configuration, monkeypatch, value):
        """Reject nonfinite or nonpositive lifecycle deadlines."""
        monkeypatch.setenv(constants.C_ENV_STOP_TIMEOUT, value)
        with pytest.raises(ValueError):
            LauncherConfiguration.from_environment()

    def test_status_creates_no_storage(self, launcher_configuration):
        """An initial status command must create neither state nor the application DB."""
        result = run_cli([constants.C_LONG_FLAG.format(constants.C_STATUS)])
        assert result.returncode == constants.C_SUCCESS, result.stderr
        assert constants.C_WEB in result.stdout
        assert constants.C_SCHEDULER in result.stdout
        assert not launcher_configuration.state_directory.exists()
        assert not Path(os.environ[C_ENV_DATABASE]).exists()

    @pytest.mark.parametrize(C_PYTEST_ARGUMENTS, [
        [C_START_OPTION], [C_STOP_OPTION], [C_START_OPTION, constants.C_ALL_FLAG, constants.C_FORCE_FLAG],
        [C_STATUS_OPTION, constants.C_FOREGROUND_FLAG], [C_START_OPTION, C_STOP_OPTION, constants.C_ALL_FLAG],
        [C_START_OPTION, constants.C_SERVICE_FLAG, C_OMITTED_SERVICE],
        [C_START_OPTION, constants.C_ALL_FLAG, constants.C_SERVICE_FLAG, constants.C_WEB],
    ])
    def test_invalid_cli(self, arguments):
        """Reject ambiguous or unsupported command combinations before any launch."""
        with pytest.raises(SystemExit) as exception:
            LauncherApplication().run(arguments)
        assert exception.value.code == C_TEST_ARGUMENT_ERROR


class TestProcessOwnership:
    """Prove stale process metadata cannot target an unrelated live process."""

    def test_current_process_with_wrong_command_is_not_owned(self, launcher_configuration):
        """Even a matching PID and birth time must carry the exact runner command nonce."""
        process = psutil.Process()
        record = ProcessRecord(constants.C_WEB, process.pid, process.create_time(), C_TEST_TOKEN, C_TEST_PORT, C_TEST_SECRET)
        controller = create_process_controller()
        assert controller.identify(record) is None
        controller.force_stop(record)
        assert process.is_running()

    def test_reused_pid_is_not_owned(self):
        """A PID with a different creation time is stale and cannot be terminated."""
        process = psutil.Process()
        record = ProcessRecord(constants.C_WEB, process.pid, C_TEST_CREATED_AT, C_TEST_TOKEN, C_TEST_PORT, C_TEST_SECRET)
        assert create_process_controller().identify(record) is None

    def test_corrupt_state_is_unknown_and_preserved(self, manager):
        """Corrupt state blocks mutations instead of silently discarding ownership."""
        with manager.lifecycle_lock():
            path = manager.configuration.state_path(constants.C_WEB)
            path.write_text(C_INVALID_JSON, encoding=constants.C_ENCODING)
            assert manager.status(constants.C_WEB).state == constants.C_UNKNOWN
            with pytest.raises(RuntimeError):
                manager.start(constants.C_WEB)
            assert path.read_text(encoding=constants.C_ENCODING) == C_INVALID_JSON
            path.unlink()

    def test_stale_state_is_read_only(self, manager):
        """Stale PID records report stopped without being modified by status."""
        with manager.lifecycle_lock():
            process = psutil.Process()
            record = ProcessRecord(constants.C_WEB, process.pid, C_TEST_CREATED_AT, C_TEST_TOKEN, C_TEST_PORT, C_TEST_SECRET)
            path = manager.configuration.state_path(constants.C_WEB)
            record.write(path)
            original = path.read_bytes()
            assert manager.status(constants.C_WEB).state == constants.C_STOPPED
            assert path.read_bytes() == original

    def test_platform_spawn_options(self):
        """Unix detaches sessions and Windows never opens a visible console window."""
        assert PosixProcessController().spawn_options() == dict(start_new_session=True)
        if os.name == constants.C_WINDOWS:
            assert WindowsProcessController().spawn_options() == dict(creationflags=subprocess.CREATE_NO_WINDOW)


class TestControlProtocol:
    """Ensure local requests cannot stop a service without its per-launch credential."""

    def test_authentication_and_post_only_shutdown(self, launcher_configuration):
        """Reject wrong credentials and GET shutdown while accepting an authenticated POST."""
        launcher_configuration.state_directory.mkdir(parents=True)
        with ServiceControlServer(launcher_configuration, constants.C_WEB, C_TEST_TOKEN) as control:
            thread = Thread(target=control.serve_forever, daemon=True)
            thread.start()
            try:
                address = constants.C_CONTROL_URL.format(port=control.record.control_port, path=constants.C_STOP_PATH)
                with httpx.Client(trust_env=False) as client:
                    assert client.post(address).status_code == constants.C_HTTP_FORBIDDEN
                    headers = {constants.C_AUTHORIZATION: constants.C_BEARER.format(token=C_WRONG_TOKEN)}
                    assert client.post(address, headers=headers).status_code == constants.C_HTTP_FORBIDDEN
                    headers[constants.C_AUTHORIZATION] = constants.C_BEARER.format(token=C_TEST_TOKEN)
                    assert client.post(address, headers=headers).status_code == constants.C_HTTP_FORBIDDEN
                    headers[constants.C_AUTHORIZATION] = constants.C_BEARER.format(token=control.record.control_secret)
                    assert client.get(address, headers=headers).status_code == constants.C_HTTP_NOT_FOUND
                    assert not control.record.stop_requested
                    assert client.post(address, headers=headers).status_code == constants.C_HTTP_OK
                assert control.record.stop_requested
            finally:
                control.shutdown()
                thread.join()


class TestLifecyclePolicies:
    """Exercise failure and timeout policies without waiting for production deadlines."""

    def test_stop_timeout_requires_force(self, launcher_configuration):
        """Never escalate a timed-out graceful stop unless the user selected force."""
        controller = Mock()
        controller.identify.return_value = object()
        manager = ServiceManager(replace(launcher_configuration, stop_timeout=C_SHORT_TIMEOUT), controller=controller)
        record = ProcessRecord(constants.C_WEB, C_TEST_PID, C_TEST_CREATED_AT, C_TEST_TOKEN, C_TEST_PORT, C_TEST_SECRET)
        manager.record = Mock(return_value=record)
        manager._request = Mock(return_value={})
        with pytest.raises(RuntimeError, match=constants.C_STOP_TIMEOUT):
            manager.stop(constants.C_WEB)
        controller.force_stop.assert_not_called()
        launcher_configuration.state_directory.mkdir(parents=True)
        assert manager.stop(constants.C_WEB, force=True) == constants.C_STOPPED
        controller.force_stop.assert_called_once_with(record)
        assert ProcessRecord.read(launcher_configuration.state_path(constants.C_WEB)).stop_requested

    def test_restart_never_starts_after_failed_stop(self, launcher_configuration):
        """A failed stop blocks restart of that service but does not skip other results."""
        manager = ServiceManager(launcher_configuration)
        manager.stop = Mock(side_effect=RuntimeError(constants.C_STOP_TIMEOUT))
        manager.start = Mock()
        assert manager.execute(constants.C_RESTART, [constants.C_WEB]) == constants.C_FAILURE
        manager.start.assert_not_called()

    def test_partial_start_preserves_success(self, launcher_configuration):
        """Continue across independent startup failures without rolling back successful services."""
        manager = ServiceManager(launcher_configuration)
        manager.start = Mock(side_effect=[RuntimeError(constants.C_START_FAILED), constants.C_RUNNING])
        manager.stop = Mock()
        assert manager.execute(constants.C_START, list(manager.registry.definitions)) == constants.C_FAILURE
        assert manager.start.call_count == len(manager.registry.definitions)
        manager.stop.assert_not_called()

    def test_registry_dependencies_and_cycle_detection(self):
        """A new service can declare dependencies without adding CLI-specific branches."""
        registry = ServiceRegistry([
            ServiceDefinition(constants.C_WEB, WebServiceRuntime),
            ServiceDefinition(C_TEST_DEPENDENT, WebServiceRuntime, (constants.C_WEB,)),
        ])
        assert registry.ordered([C_TEST_DEPENDENT]) == [constants.C_WEB, C_TEST_DEPENDENT]
        registry.definitions[C_TEST_CYCLE] = ServiceDefinition(C_TEST_CYCLE, WebServiceRuntime, (C_TEST_CYCLE,))
        with pytest.raises(ValueError):
            registry.ordered([C_TEST_CYCLE])


class TestActualServiceProcesses:
    """Exercise the public commands with real web and scheduler subprocesses offline."""

    def test_all_lifecycle_and_scheduler_independence(self, manager):
        """Start both, stop web, verify scheduler health, restart all, and stop idempotently."""
        result = run_cli([C_START_OPTION, constants.C_ALL_FLAG])
        assert result.returncode == constants.C_SUCCESS, result.stdout + result.stderr
        web_record = manager.record(constants.C_WEB)
        scheduler_record = manager.record(constants.C_SCHEDULER)
        assert web_record.control_secret not in manager.controller.identify(web_record).cmdline()
        for name in manager.registry.definitions:
            assert manager.status(name).state == constants.C_RUNNING
        result = run_cli([C_LONG_START_OPTION, constants.C_ALL_FLAG])
        assert result.returncode == constants.C_SUCCESS, result.stdout + result.stderr
        assert manager.record(constants.C_WEB).token == web_record.token
        assert run_cli([C_STOP_OPTION, constants.C_SERVICE_FLAG, constants.C_WEB]).returncode == constants.C_SUCCESS
        assert manager.status(constants.C_WEB).state == constants.C_STOPPED
        assert manager.status(constants.C_SCHEDULER).health == constants.C_HEALTHY
        result = run_cli([C_RESTART_OPTION, constants.C_ALL_FLAG])
        assert result.returncode == constants.C_SUCCESS, result.stdout + result.stderr
        assert manager.record(constants.C_SCHEDULER).token != scheduler_record.token
        assert run_cli([C_STOP_OPTION, constants.C_ALL_FLAG]).returncode == constants.C_SUCCESS
        assert run_cli([C_LONG_STOP_OPTION, constants.C_ALL_FLAG]).returncode == constants.C_SUCCESS
        for name in manager.registry.definitions:
            assert manager.status(name).state == constants.C_STOPPED

    def test_port_conflict_retains_scheduler(self, manager):
        """A port already occupied by another app must not prevent the independent worker starting."""
        with socket.socket() as listener:
            listener.bind((constants.C_DEFAULT_HOST, manager.configuration.port))
            listener.listen()
            result = run_cli([C_START_OPTION, constants.C_ALL_FLAG])
            assert result.returncode == constants.C_FAILURE, result.stdout + result.stderr
            assert manager.status(constants.C_SCHEDULER).state == constants.C_RUNNING
            assert manager.status(constants.C_WEB).state == constants.C_STOPPED

    def test_concurrent_starts_create_one_service(self, manager):
        """Serialized starts must converge on the same process rather than creating duplicates."""
        command = [sys.executable, str(C_CLI_PATH), C_START_OPTION, constants.C_SERVICE_FLAG, constants.C_WEB]
        first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first_output = first.communicate(timeout=C_TEST_TIMEOUT)
        second_output = second.communicate(timeout=C_TEST_TIMEOUT)
        assert first.returncode == constants.C_SUCCESS, first_output
        assert second.returncode == constants.C_SUCCESS, second_output
        assert manager.status(constants.C_WEB).state == constants.C_RUNNING

    def test_foreground_exits_after_intentional_stop(self, manager):
        """A foreground supervisor exits successfully after its managed services are stopped."""
        process = subprocess.Popen([sys.executable, str(C_CLI_PATH), C_START_OPTION,
                                    constants.C_ALL_FLAG, constants.C_FOREGROUND_FLAG],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait_for_service(manager, constants.C_SCHEDULER)
            original_record = manager.record(constants.C_WEB)
            result = run_cli([C_RESTART_OPTION, constants.C_ALL_FLAG])
            assert result.returncode == constants.C_SUCCESS, result.stdout + result.stderr
            assert manager.record(constants.C_WEB).token != original_record.token
            assert process.poll() is None
            web_record = manager.record(constants.C_WEB)
            manager.controller.identify(web_record).suspend()
            manager.configuration = replace(manager.configuration, stop_timeout=C_SHORT_TIMEOUT)
            with manager.lifecycle_lock():
                assert manager.stop(constants.C_WEB, force=True) == constants.C_STOPPED
            time.sleep(constants.C_SUPERVISOR_POLL_SECONDS)
            assert process.poll() is None
            assert manager.status(constants.C_SCHEDULER).state == constants.C_RUNNING
            result = run_cli([C_STOP_OPTION, constants.C_ALL_FLAG])
            assert result.returncode == constants.C_SUCCESS, result.stdout + result.stderr
            output = process.communicate(timeout=C_TEST_TIMEOUT)
            assert process.returncode == constants.C_SUCCESS, output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=C_TEST_TIMEOUT)

    def test_foreground_cleans_other_service_after_crash(self, manager):
        """An unexpected required-service exit shuts down siblings and returns failure."""
        process = subprocess.Popen([sys.executable, str(C_CLI_PATH), C_START_OPTION,
                                    constants.C_ALL_FLAG, constants.C_FOREGROUND_FLAG],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait_for_service(manager, constants.C_SCHEDULER)
            manager.controller.force_stop(manager.record(constants.C_WEB))
            output = process.communicate(timeout=C_TEST_TIMEOUT)
            assert process.returncode == constants.C_FAILURE, output
            assert manager.status(constants.C_SCHEDULER).state == constants.C_STOPPED
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=C_TEST_TIMEOUT)

    def test_force_stops_unresponsive_owned_process(self, manager):
        """An unresponsive service remains alive without force and is terminated with force."""
        assert manager.execute(constants.C_START, [constants.C_WEB]) == constants.C_SUCCESS
        record = manager.record(constants.C_WEB)
        process = manager.controller.identify(record)
        process.suspend()
        manager.configuration = replace(manager.configuration, stop_timeout=C_SHORT_TIMEOUT)
        try:
            with pytest.raises(RuntimeError, match=constants.C_CONTROL_ERROR):
                manager.stop(constants.C_WEB)
            assert process.is_running()
            assert manager.stop(constants.C_WEB, force=True) == constants.C_STOPPED
            assert manager.controller.identify(record) is None
        finally:
            if manager.controller.identify(record) is not None:
                process.resume()
