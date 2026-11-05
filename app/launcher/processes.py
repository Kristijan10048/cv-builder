"""Platform-aware spawning and identity-checked process-tree termination."""

from abc import ABC, abstractmethod
import os
import subprocess
import sys

import psutil

from . import constants as constants


class BaseProcessController(ABC):
    """Define OS-specific spawn options behind a shared lifecycle interface."""

    @abstractmethod
    def spawn_options(self):
        """Return process isolation options for the current platform."""

    def spawn(self, name, token, log_stream):
        """Start a trusted registry runner using the caller's selected interpreter."""
        return subprocess.Popen(
            [sys.executable, constants.C_MODULE_FLAG, constants.C_RUNNER_MODULE,
             constants.C_SERVICE_FLAG, name, constants.C_TOKEN_FLAG, token],
            cwd=constants.C_PROJECT_ROOT, stdin=subprocess.DEVNULL,
            stdout=log_stream, stderr=subprocess.STDOUT, **self.spawn_options(),
        )

    def identify(self, record):
        """Reject reused PIDs and command mismatches before any destructive operation."""
        try:
            process = psutil.Process(record.pid)
            if process.create_time() != record.created_at or process.status() == psutil.STATUS_ZOMBIE:
                return None
            command = process.cmdline()
            expected_arguments = [constants.C_MODULE_FLAG, constants.C_RUNNER_MODULE,
                                  constants.C_SERVICE_FLAG, record.name, constants.C_TOKEN_FLAG, record.token]
            if command[constants.C_ONE:] != expected_arguments:
                return None
            return process
        except psutil.NoSuchProcess:
            return None

    def force_stop(self, record):
        """Kill only the verified process and descendants discovered under its ownership."""
        process = self.identify(record)
        if process is None:
            return
        descendants = process.children(recursive=True)
        # psutil retains creation times and rechecks PID reuse when killing.
        for child in reversed(descendants):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
        _, survivors = psutil.wait_procs(descendants + [process], timeout=constants.C_FORCE_TIMEOUT)
        if survivors:
            raise RuntimeError(constants.C_STOP_TIMEOUT)


class WindowsProcessController(BaseProcessController):
    """Start hidden Windows processes whose lifetime does not depend on a terminal."""

    def spawn_options(self):
        """Suppress console creation; graceful control uses the local endpoint."""
        return dict(creationflags=subprocess.CREATE_NO_WINDOW)


class PosixProcessController(BaseProcessController):
    """Detach local Unix services from the invoking terminal session."""

    def spawn_options(self):
        """Create a fresh session without a shell or inherited terminal streams."""
        return dict(start_new_session=True)


def create_process_controller():
    """Choose the process implementation without affecting service definitions."""
    if os.name == constants.C_WINDOWS:
        return WindowsProcessController()
    return PosixProcessController()
