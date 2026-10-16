"""Exercise the Windows launcher with inert workers instead of Jira or coding CLIs."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

C_WINDOWS_PLATFORM = "nt"
C_POWERSHELL_EXECUTABLE = shutil.which("powershell.exe")
C_SKIP_REASON = "The launcher requires Windows PowerShell."
C_LAUNCHER_NAME = "Run-JiraAgent.ps1"
C_WORKER_NAME = "jira_agent.py"
C_AGENT_DIRECTORY = "coding_agent/jira_agent"
C_CALLER_DIRECTORY = "caller"
C_LOG_PATH = "logs/jira-agent.log"
C_TEMPORARY_PREFIX = "jira launcher tests "
C_ENCODING = "utf-8"
C_ENCODING_ERRORS = "replace"
C_TIMEOUT = 30
C_SUCCESS_CODE = 0
C_FAILURE_CODE = 7
C_ARGUMENTS = ("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File")
C_PYTHON_ARGUMENT = "-PythonExecutable"
C_TEST_ENVIRONMENT = {
    "JIRA_URL": "https://launcher-test.invalid",
    "JIRA_EMAIL": "launcher-test@example.invalid",
    "JIRA_API_TOKEN": "inert-launcher-test-token",
    "JIRA_PROJECT": "TEST",
}
C_WORKER_SUCCESS = (
    "import os\n"
    "print('worker started', flush=True)\n"
    "print(os.environ['JIRA_URL'], flush=True)\n"
)
C_WORKER_FAILURE = (
    "import sys\n"
    "print('worker started', flush=True)\n"
    "print('Traceback (most recent call last):', file=sys.stderr, flush=True)\n"
    "print('  File fake_worker.py, line 1', file=sys.stderr, flush=True)\n"
    "print('ValueError: complete failure details', file=sys.stderr, flush=True)\n"
    "sys.exit(7)\n"
)
C_STARTED_MESSAGE = "worker started"
C_FAILURE_MESSAGE = "ValueError: complete failure details"
C_EXIT_MESSAGE = "Jira agent exited with code 7."
C_NATIVE_ERROR = "NativeCommandError"
C_JIRA_URL_SETTING = "JIRA_URL"
C_TICKETS_SWITCH = "-Tickets"
C_PROJECTS_SWITCH = "-Projects"
C_PROJECT_SWITCH = "-Project"
C_PROJECT_NAME = "Project With Spaces"
C_TICKETS_ARGUMENT = "--tickets"
C_PROJECTS_ARGUMENT = "--projects"
C_WORKER_ARGUMENTS = "import json\nimport sys\nprint(json.dumps(sys.argv[1:]), flush=True)\n"


@unittest.skipUnless(os.name == C_WINDOWS_PLATFORM and C_POWERSHELL_EXECUTABLE, C_SKIP_REASON)
class JiraLauncherTests(unittest.TestCase):
    """Check native stderr handling, exit codes, and paths in real Windows PowerShell."""

    def setUp(self) -> None:
        """Copy the launcher into an isolated checkout layout with a harmless worker."""
        temporary_directory = tempfile.TemporaryDirectory(prefix=C_TEMPORARY_PREFIX)
        self.addCleanup(temporary_directory.cleanup)
        self.repository_directory = Path(temporary_directory.name)
        self.agent_directory = self.repository_directory / C_AGENT_DIRECTORY
        self.agent_directory.mkdir(parents=True)
        self.caller_directory = self.repository_directory / C_CALLER_DIRECTORY
        self.caller_directory.mkdir()
        self.launcher_path = self.agent_directory / C_LAUNCHER_NAME
        source_launcher = Path(__file__).resolve().parent.parent / C_LAUNCHER_NAME
        shutil.copyfile(source_launcher, self.launcher_path)

    def run_launcher(
        self, worker_source: str, arguments: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        """Launch a fake worker with inert process settings and no network operations."""
        worker_path = self.agent_directory / C_WORKER_NAME
        worker_path.write_text(worker_source, encoding=C_ENCODING)
        environment = dict(os.environ)
        environment.update(C_TEST_ENVIRONMENT)
        return subprocess.run(
            [C_POWERSHELL_EXECUTABLE, *C_ARGUMENTS, str(self.launcher_path),
             C_PYTHON_ARGUMENT, sys.executable, *arguments],
            cwd=self.caller_directory, env=environment, capture_output=True,
            text=True, encoding=C_ENCODING, errors=C_ENCODING_ERRORS, timeout=C_TIMEOUT,
        )

    def test_success_from_another_directory_preserves_process_settings(self) -> None:
        """The launcher must find its worker and use settings supplied in the terminal."""
        result = self.run_launcher(C_WORKER_SUCCESS)
        self.assertEqual(result.returncode, C_SUCCESS_CODE, result.stdout + result.stderr)
        self.assertIn(C_STARTED_MESSAGE, result.stdout)
        self.assertIn(C_TEST_ENVIRONMENT[C_JIRA_URL_SETTING], result.stdout)
        log_output = (self.agent_directory / C_LOG_PATH).read_text(encoding=C_ENCODING)
        self.assertIn(C_STARTED_MESSAGE, log_output)

    def test_stderr_is_fully_logged_and_exit_code_is_preserved(self) -> None:
        """A traceback must reach the console and log without stopping at its first line."""
        result = self.run_launcher(C_WORKER_FAILURE)
        self.assertEqual(result.returncode, C_FAILURE_CODE, result.stdout + result.stderr)
        self.assertIn(C_FAILURE_MESSAGE, result.stdout)
        self.assertIn(C_EXIT_MESSAGE, result.stdout)
        self.assertNotIn(C_NATIVE_ERROR, result.stderr)
        log_output = (self.agent_directory / C_LOG_PATH).read_text(encoding=C_ENCODING)
        self.assertIn(C_STARTED_MESSAGE, log_output)
        self.assertIn(C_FAILURE_MESSAGE, log_output)

    def test_listing_flags_and_project_are_forwarded_to_python(self) -> None:
        """Forward listing requests and preserve a project containing spaces as one argument."""
        for arguments, expected_arguments in (
            ((C_PROJECTS_SWITCH,), [C_PROJECTS_ARGUMENT]),
            ((C_TICKETS_SWITCH,), [C_TICKETS_ARGUMENT]),
            ((C_TICKETS_SWITCH, C_PROJECT_SWITCH, C_PROJECT_NAME), [C_TICKETS_ARGUMENT, C_PROJECT_NAME]),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_launcher(C_WORKER_ARGUMENTS, arguments)
                self.assertEqual(result.returncode, C_SUCCESS_CODE, result.stdout + result.stderr)
                self.assertIn(json.dumps(expected_arguments), result.stdout)
