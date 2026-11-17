"""Read-only revision lookup and optional terminal capabilities for console output."""

from abc import ABC, abstractmethod
import os
import subprocess

from . import constants as constants


class BaseRevisionProvider(ABC):
    """Supply a display-safe revision independently of service lifecycle operations."""

    @abstractmethod
    def revision(self):
        """Return a short revision or a readable fallback."""


class GitRevisionProvider(BaseRevisionProvider):
    """Resolve the current checkout once, without requiring Git in deployment images."""

    def __init__(self, project_root=constants.C_PROJECT_ROOT, runner=None):
        """Allow isolated repositories and subprocess behavior in tests."""
        self.project_root = project_root
        self.runner = runner or subprocess.run

    def revision(self):
        """Bound Git execution and reject invalid text before it reaches a terminal title."""
        try:
            result = self.runner(
                constants.C_GIT_REVISION_COMMAND, cwd=self.project_root,
                capture_output=True, text=True, timeout=constants.C_GIT_TIMEOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == constants.C_WINDOWS else constants.C_ZERO,
            )
            revision = result.stdout.strip()
            if (result.returncode == constants.C_SUCCESS
                    and constants.C_GIT_HASH_MINIMUM <= len(revision) <= constants.C_GIT_HASH_MAXIMUM
                    and all(character in constants.C_GIT_HASH_CHARACTERS for character in revision)):
                return revision
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass
        return constants.C_REVISION_UNAVAILABLE


class BaseTerminalCapabilities(ABC):
    """Describe terminal support per output destination, independently of formatting."""

    @abstractmethod
    def supports_color(self, stream):
        """Report whether this destination can render colored labels."""

    @abstractmethod
    def supports_title(self, stream):
        """Report whether this destination can accept a terminal title."""


class TerminalCapabilities(BaseTerminalCapabilities):
    """Detect interactive Windows and Linux terminals with safe plain-text fallbacks."""

    def __init__(self, environment=None):
        """Allow capability policy to be tested without modifying host settings."""
        self.environment = os.environ if environment is None else environment

    def _supports_control(self, stream):
        """Never send escape sequences to redirected streams or dumb terminals."""
        try:
            if not stream.isatty() or self.environment.get(constants.C_ENV_TERM) == constants.C_TERM_DUMB:
                return False
            return os.name != constants.C_WINDOWS or self._enable_windows_control(stream)
        except (AttributeError, OSError, ValueError):
            return False

    @staticmethod
    def _enable_windows_control(stream):
        """Enable virtual-terminal processing on the actual Windows console handle."""
        import ctypes
        from ctypes import wintypes
        import msvcrt

        try:
            kernel = ctypes.WinDLL(constants.C_WINDOWS_KERNEL_LIBRARY, use_last_error=True)
            kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel.GetConsoleMode.restype = wintypes.BOOL
            kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.SetConsoleMode.restype = wintypes.BOOL
            handle = msvcrt.get_osfhandle(stream.fileno())
            mode = wintypes.DWORD()
            if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(kernel.SetConsoleMode(handle, mode.value | constants.C_ENABLE_VIRTUAL_TERMINAL_PROCESSING))
        except (AttributeError, OSError, ValueError):
            return False

    def supports_color(self, stream):
        """Honor NO_COLOR independently of title support."""
        return constants.C_ENV_NO_COLOR not in self.environment and self._supports_control(stream)

    def supports_title(self, stream):
        """Restrict title sequences to known supporting terminal families."""
        return self._supports_control(stream) and (
            os.name == constants.C_WINDOWS
            or self.environment.get(constants.C_ENV_TERM, constants.C_EMPTY).startswith(constants.C_TITLE_TERMINALS)
        )
