"""Settings, import safety and dependency smoke tests using isolated local paths."""

from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

import portalocker
import pytest
from apscheduler.schedulers.blocking import BlockingScheduler

from app.scheduler.configuration import SchedulerConfiguration
from app.scheduler import constants as scheduler_constants
from app.scheduler.errors import SchedulerConfigurationError

C_NAME = 'name'
C_VALUE = 'value'
C_RELATIVE_DATABASE_ALIAS = 'data/../data/test.db'
C_MAXIMUM = 'maximum'
C_EMPTY_TEXT = ''
C_BLANK_PATH = ' '
C_NUL_PATH = '\x00'
C_SERVER_SHARE_DB = '//server/share/db'
C_WHITESPACE_PATH = ' C:/test.db'
C_UNTRUSTED = '../untrusted'
C_UTC = 'UTC'
C_INTERVAL = 'interval'
C_UPPERCASE_DATABASE_FILENAME = "ISOLATED.DB"
C_WINDOWS_PLATFORM = "nt"
C_WINDOWS_PATH_CASES = ["C:relative.db", "\\relative.db", "NUL", "bad?.db"]

C_ROOT = Path(__file__).resolve().parents[1]
C_PROCESS_TIMEOUT_SECONDS = 15
C_PROCESS_COMMAND = "-c"
C_ENV_PYTHON_PATH = "PYTHONPATH"
C_ENV_NO_BYTECODE = "PYTHONDONTWRITEBYTECODE"
C_ENV_TEST_LOCK_PATH = "SCH01_TEST_LOCK_PATH"
C_DATABASE_FILENAME = "isolated.db"
C_LOCK_DIRECTORY = "locks"
C_LOG_DIRECTORY = "logs"
C_FILE_MODE = "a"
C_ZERO = 0
C_ONE = 1
C_LOCK_BUSY_EXIT_CODE = 23
C_LOCK_FLAGS = portalocker.LOCK_EX | portalocker.LOCK_NB
C_REQUIRED_VERSIONS = {"APScheduler": "3.11.3", "portalocker": "3.2.0"}
C_INVALID_INTEGERS = ["", "true", "0", "-1", "1.5", "2.0", " 2", "+2", "NaN", True]
C_IDENTITY_PROBE = '''
import json
import os
from app.scheduler.configuration import SchedulerConfiguration
C_REQUIRED = ("CV_BUILDER_DATABASE_PATH", "CV_BUILDER_LOCK_DIR", "CV_BUILDER_SCHEDULER_LOG_DIR")
assert all(os.environ.get(name) for name in C_REQUIRED)
configuration = SchedulerConfiguration.from_environment()
print(json.dumps([str(configuration.database_path), configuration.database_identity,
                  str(configuration.lock_path("worker")), str(configuration.log_path)]))
'''
C_LOCK_PROBE = '''
import os
import sys
import portalocker
C_REQUIRED = ("CV_BUILDER_DATABASE_PATH", "CV_BUILDER_LOCK_DIR", "CV_BUILDER_SCHEDULER_LOG_DIR", "SCH01_TEST_LOCK_PATH")
C_BUSY = 23
assert all(os.environ.get(name) for name in C_REQUIRED)
try:
    with portalocker.Lock(os.environ["SCH01_TEST_LOCK_PATH"], mode="a", timeout=0,
                         flags=portalocker.LOCK_EX | portalocker.LOCK_NB):
        pass
except portalocker.exceptions.LockException:
    sys.exit(C_BUSY)
'''
C_IMPORT_PROBE = '''
import os
import sys
C_REQUIRED = ("CV_BUILDER_DATABASE_PATH", "CV_BUILDER_LOCK_DIR", "CV_BUILDER_SCHEDULER_LOG_DIR")
assert all(os.environ.get(name) for name in C_REQUIRED)
class ImportGuard:
    """Reject database, network, process, and filesystem mutations during import."""
    @staticmethod
    def audit(event, arguments):
        """Fail loudly on side effects rather than merely checking absent files."""
        if event.startswith(("sqlite3.connect", "socket.connect", "socket.bind", "subprocess.Popen")):
            raise AssertionError(event)
        if event in ("os.mkdir", "os.remove", "os.rename"):
            raise AssertionError(event)
        if event == "open":
            mode = arguments[1]
            flags = arguments[2]
            if (isinstance(mode, str) and any(marker in mode for marker in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                raise AssertionError(event)
sys.addaudithook(ImportGuard.audit)
import app.scheduler
import app.scheduler.contracts
import app.scheduler.configuration
import app.scheduler.constants
import app.scheduler.errors
assert "app.main" not in sys.modules
assert "jobspy" not in sys.modules
assert "apscheduler" not in sys.modules
assert "app.database" not in sys.modules
'''
C_CRASH_LOCK_PROBE = '''
import os
import portalocker
C_REQUIRED = ("CV_BUILDER_DATABASE_PATH", "CV_BUILDER_LOCK_DIR", "CV_BUILDER_SCHEDULER_LOG_DIR", "SCH01_TEST_LOCK_PATH")
assert all(os.environ.get(name) for name in C_REQUIRED)
with portalocker.Lock(os.environ["SCH01_TEST_LOCK_PATH"], mode="a", timeout=0,
                     flags=portalocker.LOCK_EX | portalocker.LOCK_NB):
    os._exit(0)
'''


class IsolatedProcess:
    """Launch bounded ticket-local probes with explicit throwaway storage settings."""

    @staticmethod
    def environment(directory: Path) -> dict[str, str]:
        """Pass isolation into each child before it imports any application module."""
        environment = os.environ.copy()
        environment.update({
            scheduler_constants.C_ENV_DATABASE_PATH: str(directory / C_DATABASE_FILENAME),
            scheduler_constants.C_ENV_LOCK_DIR: str(directory / C_LOCK_DIRECTORY),
            scheduler_constants.C_ENV_LOG_DIR: str(directory / C_LOG_DIRECTORY),
            C_ENV_PYTHON_PATH: str(C_ROOT), C_ENV_NO_BYTECODE: str(C_ONE),
        })
        return environment

    @staticmethod
    def run(source: str, directory: Path, environment: dict[str, str]) -> subprocess.CompletedProcess:
        """Wait at most the probe timeout; subprocess.run terminates its own timed-out child."""
        return subprocess.run([sys.executable, C_PROCESS_COMMAND, source], cwd=directory,
                              env=environment, capture_output=True, text=True,
                              timeout=C_PROCESS_TIMEOUT_SECONDS, check=False)


class TestSchedulerConfiguration:
    """Verify deterministic settings without creating real databases or workers."""

    def test_defaults_create_nothing(self, tmp_path):
        """Loading resolves paths and leaves all directories and files untouched."""
        configuration = SchedulerConfiguration.from_environment({}, tmp_path)
        assert configuration.database_path == tmp_path / scheduler_constants.C_DEFAULT_DATABASE_PATH
        assert configuration.max_workers == scheduler_constants.C_DEFAULT_MAX_WORKERS
        assert configuration.poll_seconds == scheduler_constants.C_DEFAULT_POLL_SECONDS
        assert configuration.retention_days == scheduler_constants.C_DEFAULT_RETENTION_DAYS
        assert list(tmp_path.iterdir()) == []

    def test_relative_identity_ignores_cwd(self, tmp_path, monkeypatch):
        """Web and worker launched from different directories resolve the same identity."""
        settings = {scheduler_constants.C_ENV_DATABASE_PATH: C_RELATIVE_DATABASE_ALIAS}
        first = SchedulerConfiguration.from_environment(settings, C_ROOT)
        monkeypatch.chdir(tmp_path)
        second = SchedulerConfiguration.from_environment(settings, C_ROOT)
        assert first == second
        assert first.database_identity == second.database_identity
        assert first.lock_path(scheduler_constants.C_LOCK_WORKER) == second.lock_path(scheduler_constants.C_LOCK_WORKER)

    def test_independent_process_identity(self, tmp_path):
        """Two processes share explicit temporary database/lock/log identities despite cwd."""
        environment = IsolatedProcess.environment(tmp_path)
        first = IsolatedProcess.run(C_IDENTITY_PROBE, tmp_path, environment)
        second = IsolatedProcess.run(C_IDENTITY_PROBE, C_ROOT, environment)
        assert first.returncode == C_ZERO, first.stderr
        assert second.returncode == C_ZERO, second.stderr
        assert json.loads(first.stdout) == json.loads(second.stdout)

    @pytest.mark.parametrize(C_NAME, [scheduler_constants.C_ENV_MAX_WORKERS,
                                      scheduler_constants.C_ENV_POLL_SECONDS,
                                      scheduler_constants.C_ENV_RETENTION_DAYS])
    @pytest.mark.parametrize(C_VALUE, C_INVALID_INTEGERS)
    def test_reject_invalid_numeric_settings(self, name, value, tmp_path):
        """Never silently fall back when a provided worker setting is invalid."""
        with pytest.raises(SchedulerConfigurationError):
            SchedulerConfiguration.from_environment({name: value}, tmp_path)

    @pytest.mark.parametrize((C_NAME, C_MAXIMUM), [
        (scheduler_constants.C_ENV_MAX_WORKERS, scheduler_constants.C_MAX_WORKERS),
        (scheduler_constants.C_ENV_POLL_SECONDS, scheduler_constants.C_MAX_POLL_SECONDS),
        (scheduler_constants.C_ENV_RETENTION_DAYS, scheduler_constants.C_MAX_RETENTION_DAYS),
    ])
    def test_upper_setting_bounds(self, name, maximum, tmp_path):
        """Accept the largest documented value and reject the next one."""
        SchedulerConfiguration.from_environment({name: str(maximum)}, tmp_path)
        with pytest.raises(SchedulerConfigurationError):
            SchedulerConfiguration.from_environment({name: str(maximum + C_ONE)}, tmp_path)

    @pytest.mark.parametrize(C_VALUE, [C_EMPTY_TEXT, C_BLANK_PATH, C_NUL_PATH, C_SERVER_SHARE_DB, C_WHITESPACE_PATH])
    def test_reject_invalid_paths(self, value, tmp_path):
        """Reject blank, malformed and unsupported network paths at startup."""
        with pytest.raises(SchedulerConfigurationError):
            SchedulerConfiguration.from_environment({scheduler_constants.C_ENV_DATABASE_PATH: value}, tmp_path)

    def test_reject_wrong_path_kinds(self, tmp_path):
        """Directories cannot be database files and files cannot be lock directories."""
        temporary_file = tmp_path / C_DATABASE_FILENAME
        temporary_file.touch()
        for settings in ({scheduler_constants.C_ENV_DATABASE_PATH: str(tmp_path)},
                         {scheduler_constants.C_ENV_LOCK_DIR: str(temporary_file)},
                         {scheduler_constants.C_ENV_LOG_DIR: str(temporary_file / C_LOG_DIRECTORY)}):
            with pytest.raises(SchedulerConfigurationError):
                SchedulerConfiguration.from_environment(settings, tmp_path)

    def test_distinct_database_and_lock_purposes(self, tmp_path):
        """Locks for separate databases/purposes never accidentally alias."""
        first = SchedulerConfiguration.from_environment({}, tmp_path)
        second = SchedulerConfiguration.from_environment({scheduler_constants.C_ENV_DATABASE_PATH: C_DATABASE_FILENAME}, tmp_path)
        assert first.database_identity != second.database_identity
        assert first.lock_path(scheduler_constants.C_LOCK_WORKER) != first.lock_path(scheduler_constants.C_LOCK_MIGRATION)
        with pytest.raises(SchedulerConfigurationError):
            first.lock_path(C_UNTRUSTED)

    def test_reject_database_directory_collisions(self, tmp_path):
        """Even nonexistent paths cannot make the database file a lock/log directory."""
        for directory in (tmp_path / C_DATABASE_FILENAME, tmp_path / C_DATABASE_FILENAME / C_LOCK_DIRECTORY):
            with pytest.raises(SchedulerConfigurationError):
                SchedulerConfiguration.from_environment({
                    scheduler_constants.C_ENV_DATABASE_PATH: str(tmp_path / C_DATABASE_FILENAME),
                    scheduler_constants.C_ENV_LOCK_DIR: str(directory),
                }, tmp_path)

    @pytest.mark.skipif(os.name != C_WINDOWS_PLATFORM, reason=C_WINDOWS_PLATFORM)
    @pytest.mark.parametrize(C_VALUE, C_WINDOWS_PATH_CASES)
    def test_windows_paths_and_case_identity(self, value, tmp_path):
        """Reject ambiguous Windows paths and normalize path casing for lock identities."""
        with pytest.raises(SchedulerConfigurationError):
            SchedulerConfiguration.from_environment({scheduler_constants.C_ENV_DATABASE_PATH: value}, tmp_path)
        first = SchedulerConfiguration.from_environment({scheduler_constants.C_ENV_DATABASE_PATH: C_DATABASE_FILENAME}, tmp_path)
        second = SchedulerConfiguration.from_environment({scheduler_constants.C_ENV_DATABASE_PATH: C_UPPERCASE_DATABASE_FILENAME}, tmp_path)
        assert first.database_identity == second.database_identity

    def test_import_has_no_database_network_or_write_side_effects(self, tmp_path):
        """A fresh interpreter audits imports, with bytecode writes disabled."""
        result = IsolatedProcess.run(C_IMPORT_PROBE, tmp_path, IsolatedProcess.environment(tmp_path))
        assert result.returncode == C_ZERO, result.stderr
        assert list(tmp_path.iterdir()) == []

    def test_selected_dependency_versions_and_dispatch_options(self):
        """Configure the pinned APScheduler API without starting its event loop."""
        for distribution, expected_version in C_REQUIRED_VERSIONS.items():
            assert version(distribution) == expected_version
        scheduler = BlockingScheduler(timezone=C_UTC)
        dispatcher = scheduler.add_job(self.fake_dispatch, trigger=C_INTERVAL,
                                       seconds=scheduler_constants.C_DEFAULT_POLL_SECONDS,
                                       coalesce=True, max_instances=C_ONE)
        assert dispatcher.coalesce is True
        assert dispatcher.max_instances == C_ONE
        assert scheduler.running is False

    @staticmethod
    def fake_dispatch() -> None:
        """Provide an inert callable; this test never executes scheduled jobs."""
        return None

    def test_windows_compatible_lock_excludes_and_releases(self, tmp_path):
        """Prove exclusion and release after normal scope exit, exception and process death."""
        environment = IsolatedProcess.environment(tmp_path)
        configuration = SchedulerConfiguration.from_environment(environment)
        configuration.lock_directory.mkdir()
        lock_path = configuration.lock_path(scheduler_constants.C_LOCK_WORKER)
        environment[C_ENV_TEST_LOCK_PATH] = str(lock_path)
        with portalocker.Lock(lock_path, mode=C_FILE_MODE, timeout=C_ZERO, flags=C_LOCK_FLAGS):
            blocked = IsolatedProcess.run(C_LOCK_PROBE, tmp_path, environment)
            assert blocked.returncode == C_LOCK_BUSY_EXIT_CODE, blocked.stderr
        released = IsolatedProcess.run(C_LOCK_PROBE, tmp_path, environment)
        assert released.returncode == C_ZERO, released.stderr
        with pytest.raises(RuntimeError):
            with portalocker.Lock(lock_path, mode=C_FILE_MODE, timeout=C_ZERO, flags=C_LOCK_FLAGS):
                raise RuntimeError
        released = IsolatedProcess.run(C_LOCK_PROBE, tmp_path, environment)
        assert released.returncode == C_ZERO, released.stderr
        crashed = IsolatedProcess.run(C_CRASH_LOCK_PROBE, tmp_path, environment)
        assert crashed.returncode == C_ZERO, crashed.stderr
        released = IsolatedProcess.run(C_LOCK_PROBE, tmp_path, environment)
        assert released.returncode == C_ZERO, released.stderr
