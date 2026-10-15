"""Regression tests for the standalone Jira coding worker without external writes."""

import ast
import csv
import importlib
import io
import json
import os
import runpy
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote
from unittest.mock import Mock, patch

from coding_agent.jira_agent import jira_agent

C_TEST_ENVIRONMENT = {
    jira_agent.C_ENV_JIRA_URL: "https://example.atlassian.net/",
    jira_agent.C_ENV_JIRA_EMAIL: "worker@example.com",
    jira_agent.C_ENV_JIRA_TOKEN: "jira-test-secret",
    jira_agent.C_ENV_JIRA_PROJECT: "Project Name",
}
C_ISSUE_KEY = "PROJ-123"
C_SUMMARY = "Fix parser"
C_DESCRIPTION = "Preserve quoted input."
C_PROMPT = "Quotes: 'single', \"double\"; braces {value}\nUnicode: Grüße"
C_WINDOWS_EXECUTABLE = r"C:\Program Files\Agent\agent.exe"
C_WINDOWS_COMMAND = '"' + C_WINDOWS_EXECUTABLE + '" -p "{prompt}"'
C_EXECUTABLE_ARGUMENT_INDEX = 0
C_PROMPT_ARGUMENT_INDEX = 2
C_QUOTED_PROJECT_QUERY = 'project = "Project Name"'
C_INVALID_DURATIONS = ("0", "-1", "invalid")
C_EMPTY_ENVIRONMENT = {}
C_ERROR = "request failed"
C_SUCCESS_CODE = 0
C_FAILURE_CODE = 7
C_EMPTY_OUTPUT = ""
C_FIRST_CALL_INDEX = 0
C_LAST_CALL_INDEX = -1
C_METHOD_RUN = "run"
C_TIMEOUT_KEY = "timeout"
C_PARAMETERS_KEY = "params"
C_ENCODING = "utf-8-sig"
C_DOCSTRING_PREFIX = "Missing docstring: "
C_CONSTANT_PREFIX = "C_"
C_LITERAL_ERROR = "Runtime literal outside a named constant at line "
C_MAIN_MODULE = "__main__"
C_SECOND_ISSUE_KEY = "PROJ-124"
C_METHOD_WRITE = "write"
C_METHOD_REPLACE = "replace"
C_METHOD_FINGERPRINT = "workspace_fingerprint"
C_METHOD_IMPLEMENT = "implement_issue"
C_BEFORE = b"before"
C_AFTER = b"after"
C_INVALID_KEY = "bad key"
C_NULL = "\0"
C_UNTRACKED_FILE = "source.txt"
C_JIRA_STATUS = 'Ready "for" development'
C_JIRA_STATUS_QUERY = "status = {status}"
C_JIRA_LABEL_FILTER = "labels"
C_METHOD_WORKER = "JiraAgentWorker"
C_METHOD_SCHEDULER = "JiraAgentScheduler"
C_METHOD_BATCH = "run_batch"
C_TEST_POLL_INTERVAL = 1
C_TEST_SCHEDULER_TIMEOUT = 5
C_EXPECTED_RECURRING_CALLS = 2
C_METHOD_FIND_ISSUES = "find_ready_issues"
C_JOB_TRIGGER = "trigger"
C_JOB_SECONDS = "seconds"
C_JOB_ID = "id"
C_JOB_MAX_INSTANCES = "max_instances"
C_JOB_COALESCE = "coalesce"
C_JOB_REPLACE_EXISTING = "replace_existing"
C_JOB_NEXT_RUN_TIME = "next_run_time"
C_PROJECT_ROOT_PARENT_INDEX = 3
C_MODULE_ENTRY_POINT = "coding_agent.jira_agent.__main__"
C_METHOD_MAIN = "main"
C_METHOD_DOTENV_VALUES = "dotenv_values"
C_ENV_FILE_PATH_ATTRIBUTE = "C_ENV_FILE_PATH"
C_TEST_ENV_FILE_CONTENT = (
    "# Local development settings\n"
    "JIRA_URL=https://example.atlassian.net/\n"
    "JIRA_EMAIL=worker@example.com\n"
    "JIRA_API_TOKEN='jira-test-secret'\n"
    "JIRA_PROJECT=\"Project Name\"\n"
    "JIRA_STATUS='Ready for testing' # Inline comment\n"
    "POLL_INTERVAL=45\n"
)
C_FILE_JIRA_STATUS = "Ready for testing"
C_FILE_POLL_INTERVAL = 45
C_PROCESS_JIRA_PROJECT = "PROCESS_PROJECT"
C_MISSING_ENV_FILE = "missing.env"
C_VALUELESS_ENV_FILE_CONTENT = "JIRA_API_TOKEN\n"
C_PROGRESS_TEST_INTERVAL = 0.01
C_PROGRESS_TEST_TIMEOUT = 2
C_METHOD_LOG = "log"
C_TEST_REDACTION_TOKEN = "test/token+secret"
C_MESSAGE_SEPARATOR = " "
C_TIMESTAMP_PATTERN = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\] "
C_METHOD_VERIFY_CONNECTION = "verify_connection"
C_METHOD_CONFIGURATION = "from_local_environment"
C_TEST_ACCOUNT_ID = "test-account"
C_VALID_USER_PROFILE = {jira_agent.C_KEY_ACCOUNT_ID: C_TEST_ACCOUNT_ID, jira_agent.C_KEY_ACTIVE: True}
C_HTTP_RATE_LIMITED = 429
C_HTTP_SERVER_ERROR = 500
C_UNEXPECTED_USER_PROFILES = ({}, [], None, {jira_agent.C_KEY_ACCOUNT_ID: C_EMPTY_OUTPUT})
C_INVALID_JSON = "<html>Login</html>"
C_JSON_ERROR_POSITION = 0


class JiraAgentTests(unittest.TestCase):
    """Exercise configuration, subprocess arguments, HTTP calls, and reporting."""

    def setUp(self) -> None:
        """Construct a worker with mocked collaborators and inert test credentials."""
        self.configuration = jira_agent.AgentConfiguration.from_environment(C_TEST_ENVIRONMENT)
        self.report_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.report_directory.cleanup)
        self.report_path = Path(self.report_directory.name) / jira_agent.C_DEFAULT_TICKET_CSV_PATH
        self.configuration = replace(
            self.configuration, ticket_csv_path=str(self.report_path),
            repository_directory=self.report_directory.name,
        )
        self.jira_client = Mock(spec=jira_agent.JiraClient)
        self.command_runner = Mock(spec=jira_agent.CommandRunner)
        self.worker = jira_agent.JiraAgentWorker(
            self.configuration, self.jira_client, self.command_runner,
        )
        self.issue = jira_agent.JiraIssue(C_ISSUE_KEY, C_SUMMARY, C_DESCRIPTION)

    def read_ticket_rows(self) -> list[dict[str, str]]:
        """Read the persisted CSV rather than relying on report object state."""
        with self.report_path.open(encoding=jira_agent.C_ENCODING, newline=C_EMPTY_OUTPUT) as report_file:
            reader = csv.DictReader(report_file)
            self.assertEqual(reader.fieldnames, list(jira_agent.C_CSV_COLUMNS))
            return list(reader)

    def write_environment_file(self, content: str = C_TEST_ENV_FILE_CONTENT) -> Path:
        """Create a local fixture with a Windows-compatible UTF-8 byte order mark."""
        environment_file = Path(self.report_directory.name) / jira_agent.C_ENV_FILE_PATH.name
        environment_file.write_text(content, encoding=jira_agent.C_ENV_FILE_ENCODING)
        return environment_file

    def test_local_environment_loads_file_without_exporting_credentials(self) -> None:
        """Read quoted settings and comments without changing the process environment."""
        environment_file = self.write_environment_file()
        with patch.dict(os.environ, C_EMPTY_ENVIRONMENT, clear=True):
            configuration = jira_agent.AgentConfiguration.from_local_environment(
                os.environ, environment_file,
            )
            self.assertEqual(dict(os.environ), C_EMPTY_ENVIRONMENT)
        self.assertEqual(configuration.jira_token, C_TEST_ENVIRONMENT[jira_agent.C_ENV_JIRA_TOKEN])
        self.assertEqual(configuration.jira_project, C_TEST_ENVIRONMENT[jira_agent.C_ENV_JIRA_PROJECT])
        self.assertEqual(configuration.jira_status, C_FILE_JIRA_STATUS)
        self.assertEqual(configuration.poll_interval, C_FILE_POLL_INTERVAL)

    def test_local_environment_preserves_process_overrides(self) -> None:
        """Use explicit process values ahead of file settings while filling missing keys."""
        environment = {jira_agent.C_ENV_JIRA_PROJECT: C_PROCESS_JIRA_PROJECT}
        configuration = jira_agent.AgentConfiguration.from_local_environment(
            environment, self.write_environment_file(),
        )
        self.assertEqual(configuration.jira_project, C_PROCESS_JIRA_PROJECT)
        self.assertEqual(configuration.jira_email, C_TEST_ENVIRONMENT[jira_agent.C_ENV_JIRA_EMAIL])
        self.assertEqual(environment, {jira_agent.C_ENV_JIRA_PROJECT: C_PROCESS_JIRA_PROJECT})

    def test_local_environment_preserves_explicit_empty_process_values(self) -> None:
        """An invalid explicit override must still be rejected by configuration validation."""
        with self.assertRaisesRegex(ValueError, jira_agent.C_ENV_JIRA_TOKEN):
            jira_agent.AgentConfiguration.from_local_environment(
                {jira_agent.C_ENV_JIRA_TOKEN: C_EMPTY_OUTPUT}, self.write_environment_file(),
            )

    def test_local_environment_allows_missing_file(self) -> None:
        """Keep normal environment-only startup working when the local file is absent."""
        environment_file = Path(self.report_directory.name) / C_MISSING_ENV_FILE
        configuration = jira_agent.AgentConfiguration.from_local_environment(
            C_TEST_ENVIRONMENT, environment_file,
        )
        self.assertEqual(configuration, jira_agent.AgentConfiguration.from_environment(C_TEST_ENVIRONMENT))
        with self.assertRaisesRegex(ValueError, jira_agent.C_ENV_JIRA_URL):
            jira_agent.AgentConfiguration.from_local_environment(C_EMPTY_ENVIRONMENT, environment_file)

    def test_local_environment_ignores_valueless_entries(self) -> None:
        """A bare dotenv key must be handled as missing and produce the usual validation error."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment.pop(jira_agent.C_ENV_JIRA_TOKEN)
        with self.assertRaisesRegex(ValueError, jira_agent.C_ENV_JIRA_TOKEN):
            jira_agent.AgentConfiguration.from_local_environment(
                environment, self.write_environment_file(C_VALUELESS_ENV_FILE_CONTENT),
            )

    def test_configuration_accepts_csv_path(self) -> None:
        """Allow the report location to be configured without changing source code."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_TICKET_CSV_PATH] = str(self.report_path)
        configuration = jira_agent.AgentConfiguration.from_environment(environment)
        self.assertEqual(Path(configuration.ticket_csv_path), self.report_path.resolve())

    def test_default_repository_is_project_root(self) -> None:
        """Moving the worker must preserve the checkout it edits by default."""
        configuration = jira_agent.AgentConfiguration.from_environment(C_TEST_ENVIRONMENT)
        project_directory = Path(__file__).resolve().parents[C_PROJECT_ROOT_PARENT_INDEX]
        self.assertEqual(Path(configuration.repository_directory), project_directory)
        self.assertEqual(
            Path(configuration.ticket_csv_path),
            project_directory / jira_agent.C_DEFAULT_TICKET_CSV_PATH,
        )

    def test_relative_csv_path_uses_configured_repository(self) -> None:
        """An external checkout must retain its own report regardless of script location."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_REPOSITORY_DIRECTORY] = self.report_directory.name
        environment[jira_agent.C_ENV_TICKET_CSV_PATH] = jira_agent.C_DEFAULT_TICKET_CSV_PATH
        configuration = jira_agent.AgentConfiguration.from_environment(environment)
        self.assertEqual(Path(configuration.repository_directory), Path(self.report_directory.name).resolve())
        self.assertEqual(Path(configuration.ticket_csv_path), self.report_path.resolve())

    def test_csv_shows_current_ticket_then_implemented_ticket(self) -> None:
        """Publish active work before coding and move it to completed history on success."""

        def check_active_report(issue: jira_agent.JiraIssue) -> None:
            """Inspect the file at the moment implementation begins."""
            self.assertEqual(issue, self.issue)
            self.assertEqual(self.read_ticket_rows(), [{
                jira_agent.C_CSV_IMPLEMENTED_TICKET: C_EMPTY_OUTPUT,
                jira_agent.C_CSV_CURRENT_TICKET: C_ISSUE_KEY,
            }])

        with patch.object(self.worker, C_METHOD_IMPLEMENT, side_effect=check_active_report):
            self.worker.process_issue(self.issue)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])

    def test_csv_clears_failed_ticket_and_keeps_completed_history(self) -> None:
        """An implementation error must retain earlier successes without listing the failure."""
        self.worker.ticket_report.record_finished(C_SECOND_ISSUE_KEY, implemented=True)
        with patch.object(self.worker, C_METHOD_IMPLEMENT, side_effect=RuntimeError(C_ERROR)):
            self.worker.process_issue(self.issue)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_SECOND_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])

    def test_csv_restart_preserves_history_and_discards_stale_current_ticket(self) -> None:
        """Restarting must retain unique completed tickets and remove interrupted active work."""
        self.worker.ticket_report.record_finished(C_ISSUE_KEY, implemented=True)
        self.worker.ticket_report.record_started(C_SECOND_ISSUE_KEY)
        report = jira_agent.TicketCsvReport(str(self.report_path))
        report.write()
        report.record_finished(C_ISSUE_KEY, implemented=True)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])


    def test_failed_atomic_replace_preserves_previous_csv_and_cleans_temp_file(self) -> None:
        """An interrupted report replacement must retain the previous valid file."""
        self.worker.ticket_report.record_finished(C_ISSUE_KEY, implemented=True)
        with patch.object(jira_agent.os, C_METHOD_REPLACE, side_effect=OSError(C_ERROR)):
            with self.assertRaises(OSError):
                self.worker.ticket_report.record_started(C_SECOND_ISSUE_KEY)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])
        self.assertEqual(list(self.report_path.parent.iterdir()), [self.report_path])

    def test_import_does_not_require_environment_credentials(self) -> None:
        """Importing the worker must not read required settings or contact services."""
        with patch.dict(os.environ, C_EMPTY_ENVIRONMENT, clear=True):
            importlib.reload(jira_agent)

    def test_configuration_rejects_missing_settings(self) -> None:
        """Report a useful configuration error instead of an import-time KeyError."""
        with self.assertRaisesRegex(ValueError, jira_agent.C_ENV_JIRA_URL):
            jira_agent.AgentConfiguration.from_environment(C_EMPTY_ENVIRONMENT)

    def test_configuration_rejects_invalid_durations(self) -> None:
        """Prevent invalid subprocess timeouts."""
        for setting in (jira_agent.C_ENV_AGENT_TIMEOUT, jira_agent.C_ENV_POLL_INTERVAL):
            for duration in C_INVALID_DURATIONS:
                with self.subTest(setting=setting, duration=duration):
                    environment = dict(C_TEST_ENVIRONMENT)
                    environment[setting] = duration
                    with self.assertRaisesRegex(ValueError, setting):
                        jira_agent.AgentConfiguration.from_environment(environment)

    def test_configuration_rejects_missing_prompt(self) -> None:
        """Reject CLI templates that silently omit the Jira task."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_AGENT_COMMAND] = jira_agent.C_GIT_EXECUTABLE
        with self.assertRaises(ValueError):
            jira_agent.AgentConfiguration.from_environment(environment)

    def test_configuration_repr_hides_credentials(self) -> None:
        """Dataclass diagnostics must not print the Jira API credential."""
        representation = repr(self.configuration)
        self.assertNotIn(self.configuration.jira_token, representation)

    def test_posix_prompt_remains_one_argument(self) -> None:
        """Ticket quotes and newlines must not alter argument boundaries."""
        arguments = self.worker.build_agent_arguments(C_PROMPT, windows=False)
        self.assertEqual(arguments[C_LAST_CALL_INDEX], C_PROMPT)

    def test_windows_executable_preserves_backslashes(self) -> None:
        """A quoted Windows executable path must retain spaces and backslashes."""
        self.worker.configuration = replace(self.configuration, agent_command=C_WINDOWS_COMMAND)
        arguments = self.worker.build_agent_arguments(C_PROMPT, windows=True)
        self.assertEqual(arguments[C_EXECUTABLE_ARGUMENT_INDEX], C_WINDOWS_EXECUTABLE)
        self.assertEqual(arguments[C_PROMPT_ARGUMENT_INDEX], C_PROMPT)


    def test_search_quotes_project_names(self) -> None:
        """Spaces in a Jira project name must not produce malformed JQL."""
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.return_value = {jira_agent.C_KEY_ISSUES: []}
        client = jira_agent.JiraClient(self.configuration, session)
        self.assertEqual(client.find_ready_issues(), [])
        parameters = session.request.call_args.kwargs
        self.assertEqual(parameters[C_TIMEOUT_KEY], jira_agent.C_HTTP_TIMEOUT)
        self.assertIn(C_QUOTED_PROJECT_QUERY, parameters[C_PARAMETERS_KEY][jira_agent.C_KEY_QUERY])

    def test_connection_check_uses_authenticated_current_user_endpoint(self) -> None:
        """Verify credentials without querying tickets, following redirects, or changing Jira."""
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.return_value = C_VALID_USER_PROFILE
        client = jira_agent.JiraClient(self.configuration, session)
        client.verify_connection()
        self.assertEqual(session.auth, (self.configuration.jira_email, self.configuration.jira_token))
        session.request.assert_called_once_with(
            jira_agent.C_METHOD_GET,
            self.configuration.jira_url + jira_agent.C_API_PATH + jira_agent.C_CURRENT_USER_PATH,
            timeout=jira_agent.C_HTTP_TIMEOUT, allow_redirects=False,
        )

    def test_connection_check_reports_authentication_and_http_failures(self) -> None:
        """Distinguish rejected credentials and access restrictions from other HTTP failures."""
        for status_code, expected_message in (
            (jira_agent.C_HTTP_UNAUTHORIZED, jira_agent.C_ERROR_JIRA_UNAUTHORIZED),
            (jira_agent.C_HTTP_FORBIDDEN, jira_agent.C_ERROR_JIRA_FORBIDDEN),
            (C_HTTP_RATE_LIMITED, jira_agent.C_ERROR_JIRA_HTTP.format(status_code=C_HTTP_RATE_LIMITED)),
            (C_HTTP_SERVER_ERROR, jira_agent.C_ERROR_JIRA_HTTP.format(status_code=C_HTTP_SERVER_ERROR)),
        ):
            with self.subTest(status_code=status_code):
                response = jira_agent.requests.Response()
                response.status_code = status_code
                session = Mock()
                session.request.return_value = response
                with self.assertRaises(RuntimeError) as error_context:
                    jira_agent.JiraClient(self.configuration, session).verify_connection()
                self.assertEqual(str(error_context.exception), expected_message)

    def test_connection_check_reports_network_and_invalid_json_failures(self) -> None:
        """Never label transport errors or login-page responses as a valid API token."""
        for failure, expected_message in (
            (jira_agent.requests.Timeout(C_ERROR), jira_agent.C_ERROR_JIRA_TIMEOUT.format(
                seconds=jira_agent.C_HTTP_TIMEOUT,
            )),
            (jira_agent.requests.ConnectionError(C_ERROR), jira_agent.C_ERROR_JIRA_CONNECTION),
            (jira_agent.requests.RequestException(C_ERROR), jira_agent.C_ERROR_JIRA_REQUEST),
            (jira_agent.requests.exceptions.JSONDecodeError(
                C_ERROR, C_INVALID_JSON, C_JSON_ERROR_POSITION,
            ), jira_agent.C_ERROR_JIRA_RESPONSE),
        ):
            with self.subTest(failure_type=type(failure)):
                session = Mock()
                session.request.side_effect = failure
                with self.assertRaises(RuntimeError) as error_context:
                    jira_agent.JiraClient(self.configuration, session).verify_connection()
                self.assertEqual(str(error_context.exception), expected_message)

    def test_connection_check_rejects_unexpected_or_inactive_profiles(self) -> None:
        """Require a real user identity and reject explicitly inactive accounts."""
        for profile in (*C_UNEXPECTED_USER_PROFILES, {
            jira_agent.C_KEY_ACCOUNT_ID: C_TEST_ACCOUNT_ID, jira_agent.C_KEY_ACTIVE: False,
        }):
            with self.subTest(profile=profile):
                session = Mock()
                session.request.return_value.content = True
                session.request.return_value.json.return_value = profile
                with self.assertRaises(RuntimeError):
                    jira_agent.JiraClient(self.configuration, session).verify_connection()


    def test_empty_http_response_is_not_decoded(self) -> None:
        """Empty HTTP response bodies must not be decoded as JSON."""
        session = Mock()
        session.request.return_value.content = C_EMPTY_OUTPUT
        client = jira_agent.BaseHttpClient(session)
        self.assertEqual(client.request(jira_agent.C_METHOD_GET, self.configuration.jira_url), {})
        session.request.return_value.raise_for_status.assert_called_once()
        session.request.return_value.json.assert_not_called()


    def test_command_failure_preserves_diagnostic_output(self) -> None:
        """A CLI failure that writes to stdout must retain the relevant diagnostic."""
        result = subprocess.CompletedProcess(
            [], C_FAILURE_CODE, stdout=C_ERROR, stderr=C_EMPTY_OUTPUT,
        )
        with patch.object(subprocess, C_METHOD_RUN, return_value=result):
            with self.assertRaisesRegex(RuntimeError, C_ERROR):
                jira_agent.CommandRunner().run([jira_agent.C_GIT_EXECUTABLE])


    def test_runtime_literals_are_named_constants(self) -> None:
        """Check the reviewed module for hardcoded runtime strings or numbers."""
        syntax_tree = ast.parse(Path(jira_agent.__file__).read_text(encoding=C_ENCODING))
        for node in ast.walk(syntax_tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if node.body and isinstance(node.body[C_FIRST_CALL_INDEX], ast.Expr):
                    if ast.get_docstring(node):
                        node.body = node.body[jira_agent.C_ONE:]
        constant_assignments = [
            node for node in syntax_tree.body
            if isinstance(node, ast.Assign)
            and all(
                isinstance(target, ast.Name) and target.id.startswith(C_CONSTANT_PREFIX)
                for target in node.targets
            )
        ]
        for node in constant_assignments:
            syntax_tree.body.remove(node)
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (str, int, float)) and not isinstance(node.value, bool):
                    self.fail(C_LITERAL_ERROR + str(node.lineno))

    def test_every_class_and_function_has_description(self) -> None:
        """Ensure the reviewed module meets the required documentation convention."""
        source_path = Path(jira_agent.__file__)
        syntax_tree = ast.parse(source_path.read_text(encoding=C_ENCODING))
        for node in ast.walk(syntax_tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertTrue(ast.get_docstring(node), C_DOCSTRING_PREFIX + node.name)


    def test_run_once_fetches_one_batch_and_exits(self) -> None:
        """An idle scheduled invocation must fetch once, write headers, and return."""
        self.jira_client.find_ready_issues.return_value = []
        self.assertEqual(self.worker.run_once(), jira_agent.C_ZERO)
        self.jira_client.find_ready_issues.assert_called_once_with([])
        self.assertEqual(self.read_ticket_rows(), [])

    def test_empty_batch_reports_search_result_and_completion(self) -> None:
        """An idle batch must explain that no tickets matched and it completed normally."""
        self.jira_client.find_ready_issues.return_value = []
        console_output = io.StringIO()
        with redirect_stdout(console_output):
            self.assertEqual(self.worker.run_once(), jira_agent.C_ZERO)
        messages = console_output.getvalue()
        self.assertIn(jira_agent.C_LOG_SEARCH.format(
            project=self.configuration.jira_project, status=self.configuration.jira_status,
            limit=jira_agent.C_SEARCH_LIMIT,
        ), messages)
        self.assertIn(jira_agent.C_LOG_NO_TICKETS, messages)
        self.assertIn(jira_agent.C_LOG_BATCH_FINISHED.format(
            total=jira_agent.C_ZERO, failures=jira_agent.C_ZERO,
        ), messages)

    def test_failed_jira_search_reports_error_and_failed_batch(self) -> None:
        """A failed search must never be reported as an empty successful batch."""
        self.jira_client.find_ready_issues.side_effect = RuntimeError(C_ERROR)
        console_output = io.StringIO()
        with redirect_stdout(console_output):
            self.assertEqual(self.worker.run_once(), jira_agent.C_ONE)
        messages = console_output.getvalue()
        self.assertIn(jira_agent.C_LOG_BATCH_FAILURE.format(error=C_ERROR), messages)
        self.assertIn(jira_agent.C_LOG_BATCH_FINISHED.format(
            total=jira_agent.C_ZERO, failures=jira_agent.C_ONE,
        ), messages)
        self.assertNotIn(jira_agent.C_LOG_NO_TICKETS, messages)

    def test_console_messages_have_timestamp_and_redact_tokens(self) -> None:
        """Shared worker and scheduler output must redact plain and encoded credentials."""
        configuration = replace(self.configuration, jira_token=C_TEST_REDACTION_TOKEN)
        console_output = io.StringIO()
        with redirect_stdout(console_output):
            jira_agent.BaseConsoleReporter(configuration).log(C_MESSAGE_SEPARATOR.join((
                C_TEST_REDACTION_TOKEN, quote(C_TEST_REDACTION_TOKEN, safe=C_EMPTY_OUTPUT),
            )))
        messages = console_output.getvalue()
        self.assertRegex(messages, C_TIMESTAMP_PATTERN)
        self.assertNotIn(C_TEST_REDACTION_TOKEN, messages)
        self.assertNotIn(quote(C_TEST_REDACTION_TOKEN, safe=C_EMPTY_OUTPUT), messages)
        self.assertIn(jira_agent.C_REDACTED, messages)

    def test_command_progress_reports_activity_and_stops_on_exit(self) -> None:
        """Long commands must produce progress without leaving a reporter thread running."""
        progress_received = threading.Event()
        progress = jira_agent.CommandProgressReporter(
            self.worker, C_ISSUE_KEY, interval=C_PROGRESS_TEST_INTERVAL,
        )
        def observe_progress(message: str) -> None:
            """Signal that the background reporter has produced an activity message."""
            progress_received.set()

        with patch.object(self.worker, C_METHOD_LOG, side_effect=observe_progress) as log_message:
            with progress:
                self.assertTrue(progress_received.wait(C_PROGRESS_TEST_TIMEOUT))
        self.assertTrue(progress.finished.is_set())
        self.assertFalse(progress.progress_thread.is_alive())
        self.assertIn(C_ISSUE_KEY, log_message.call_args.args[C_FIRST_CALL_INDEX])

    def test_command_progress_stops_after_command_failure(self) -> None:
        """A failed command must release its progress reporter while preserving the exception."""
        progress = jira_agent.CommandProgressReporter(self.worker, C_ISSUE_KEY)
        with self.assertRaisesRegex(RuntimeError, C_ERROR):
            with progress:
                raise RuntimeError(C_ERROR)
        self.assertTrue(progress.finished.is_set())
        self.assertFalse(progress.progress_thread.is_alive())

    def test_completed_tickets_are_excluded_from_jira_query(self) -> None:
        """Completed keys must be filtered before the Jira batch limit is applied."""
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.return_value = {jira_agent.C_KEY_ISSUES: []}
        client = jira_agent.JiraClient(self.configuration, session)
        client.find_ready_issues([C_ISSUE_KEY])
        query = session.request.call_args.kwargs[C_PARAMETERS_KEY][jira_agent.C_KEY_QUERY]
        self.assertIn(jira_agent.C_JQL_EXCLUSION.format(keys=json.dumps(C_ISSUE_KEY)), query)
        self.assertEqual(session.request.call_args.args[C_FIRST_CALL_INDEX], jira_agent.C_METHOD_GET)

    def test_already_completed_ticket_is_not_implemented_again(self) -> None:
        """A stale Jira response must not rerun a ticket persisted as completed."""
        self.worker.ticket_report.record_finished(C_ISSUE_KEY, implemented=True)
        with patch.object(self.worker, C_METHOD_IMPLEMENT) as implement:
            self.assertTrue(self.worker.process_issue(self.issue))
        implement.assert_not_called()

    def test_csv_failure_returns_failed_invocation(self) -> None:
        """A failed completion write must be visible in the scheduler exit code."""
        with patch.object(self.worker.ticket_report, C_METHOD_WRITE, side_effect=[None, OSError(C_ERROR)]):
            with patch.object(self.worker, C_METHOD_IMPLEMENT):
                self.assertFalse(self.worker.process_issue(self.issue))

    def test_agent_requires_confirmation_and_new_changes(self) -> None:
        """Mark complete only after agent confirmation and new workspace changes."""
        result = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE,
            stdout=jira_agent.C_SUCCESS_MARKER_TEMPLATE.format(issue_key=C_ISSUE_KEY),
            stderr=C_EMPTY_OUTPUT,
        )
        self.command_runner.run.return_value = result
        with patch.object(self.worker, C_METHOD_FINGERPRINT, side_effect=[C_BEFORE, C_AFTER]):
            self.worker.implement_issue(self.issue)
        arguments = self.command_runner.run.call_args.args[C_FIRST_CALL_INDEX]
        self.assertIn(self.issue.build_prompt(), arguments)
        self.assertEqual(
            self.command_runner.run.call_args.kwargs[C_TIMEOUT_KEY],
            self.configuration.agent_timeout,
        )

    def test_agent_without_confirmation_is_not_completed(self) -> None:
        """A zero exit code alone cannot establish successful implementation."""
        self.command_runner.run.return_value = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=C_EMPTY_OUTPUT, stderr=C_EMPTY_OUTPUT,
        )
        with patch.object(self.worker, C_METHOD_FINGERPRINT, return_value=C_BEFORE):
            with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_INCOMPLETE):
                self.worker.implement_issue(self.issue)

    def test_unchanged_dirty_workspace_is_not_completed(self) -> None:
        """Existing changes must not be mistaken for this ticket's implementation."""
        self.command_runner.run.return_value = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE,
            stdout=jira_agent.C_SUCCESS_MARKER_TEMPLATE.format(issue_key=C_ISSUE_KEY),
            stderr=C_EMPTY_OUTPUT,
        )
        with patch.object(self.worker, C_METHOD_FINGERPRINT, return_value=C_BEFORE):
            with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_NO_CHANGES):
                self.worker.implement_issue(self.issue)

    def test_fingerprint_detects_edits_to_existing_untracked_file(self) -> None:
        """Changing content must change the fingerprint even when status is unchanged."""
        untracked_path = Path(self.report_directory.name) / C_UNTRACKED_FILE
        untracked_path.write_bytes(C_BEFORE)
        diff_result = subprocess.CompletedProcess([], C_SUCCESS_CODE, stdout=C_EMPTY_OUTPUT)
        untracked_result = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=C_UNTRACKED_FILE + C_NULL,
        )
        self.command_runner.run.side_effect = [
            diff_result, untracked_result, diff_result, untracked_result,
        ]
        before_fingerprint = self.worker.workspace_fingerprint()
        untracked_path.write_bytes(C_AFTER)
        self.assertNotEqual(before_fingerprint, self.worker.workspace_fingerprint())

    def test_batch_continues_after_malformed_ticket_and_returns_failure(self) -> None:
        """One malformed response must not prevent a later valid implementation."""
        self.jira_client.find_ready_issues.return_value = [
            {jira_agent.C_KEY_ISSUE_KEY: C_INVALID_KEY},
            {
                jira_agent.C_KEY_ISSUE_KEY: C_ISSUE_KEY,
                jira_agent.C_KEY_FIELDS: {
                    jira_agent.C_KEY_SUMMARY: C_SUMMARY,
                    jira_agent.C_KEY_DESCRIPTION: C_DESCRIPTION,
                },
            },
        ]
        with patch.object(self.worker, C_METHOD_IMPLEMENT) as implement:
            self.assertEqual(self.worker.run_once(), jira_agent.C_ONE)
        implement.assert_called_once_with(self.issue)
        self.assertEqual(self.worker.ticket_report.implemented_tickets, [C_ISSUE_KEY])

    def test_repository_lock_blocks_overlap_and_releases_after_exit(self) -> None:
        """Overlapping invocations must skip before clearing another run's CSV."""
        with jira_agent.RepositoryRunLock(self.report_directory.name):
            with self.assertRaises(BlockingIOError):
                with jira_agent.RepositoryRunLock(self.report_directory.name):
                    self.fail(C_ERROR)
        with jira_agent.RepositoryRunLock(self.report_directory.name):
            pass

    def test_agent_environment_excludes_jira_credentials(self) -> None:
        """The coding CLI must not receive the worker's Jira credentials."""
        with patch.dict(os.environ, C_TEST_ENVIRONMENT, clear=True):
            environment = self.worker.build_process_environment()
        self.assertNotIn(jira_agent.C_ENV_JIRA_TOKEN, environment)
        self.assertNotIn(jira_agent.C_ENV_JIRA_EMAIL, environment)

    def test_configuration_accepts_status_and_poll_interval(self) -> None:
        """Allow Jira selection and scheduling cadence to be configured independently."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_JIRA_STATUS] = C_JIRA_STATUS
        environment[jira_agent.C_ENV_POLL_INTERVAL] = str(C_TEST_POLL_INTERVAL)
        configuration = jira_agent.AgentConfiguration.from_environment(environment)
        self.assertEqual(configuration.jira_status, C_JIRA_STATUS)
        self.assertEqual(configuration.poll_interval, C_TEST_POLL_INTERVAL)

    def test_configuration_rejects_empty_status(self) -> None:
        """An explicitly empty status must not silently select unrelated work."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_JIRA_STATUS] = C_EMPTY_OUTPUT
        with self.assertRaisesRegex(ValueError, jira_agent.C_ENV_JIRA_STATUS):
            jira_agent.AgentConfiguration.from_environment(environment)

    def test_jira_query_quotes_status_and_does_not_require_labels(self) -> None:
        """Selecting a board status must work without the previous agent-ready label."""
        configuration = replace(self.configuration, jira_status=C_JIRA_STATUS)
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.return_value = {jira_agent.C_KEY_ISSUES: []}
        client = jira_agent.JiraClient(configuration, session)
        client.find_ready_issues([C_ISSUE_KEY])
        query = session.request.call_args.kwargs[C_PARAMETERS_KEY][jira_agent.C_KEY_QUERY]
        self.assertIn(C_JIRA_STATUS_QUERY.format(status=json.dumps(C_JIRA_STATUS)), query)
        self.assertNotIn(C_JIRA_LABEL_FILTER, query)
        self.assertIn(json.dumps(C_ISSUE_KEY), query)

    def test_scheduler_registers_immediate_recurring_job_and_shuts_down(self) -> None:
        """Schedule one nonoverlapping batch immediately, then at the configured interval."""
        scheduler = Mock(spec=jira_agent.BlockingScheduler)
        scheduler.running = True
        scheduler.start.side_effect = KeyboardInterrupt
        runtime = jira_agent.JiraAgentScheduler(self.configuration, scheduler)
        runtime.start()
        scheduler.add_job.assert_called_once()
        job_arguments = scheduler.add_job.call_args.kwargs
        self.assertEqual(scheduler.add_job.call_args.args, (runtime.run_batch,))
        self.assertEqual(job_arguments[C_JOB_TRIGGER], jira_agent.C_SCHEDULER_TRIGGER)
        self.assertEqual(job_arguments[C_JOB_SECONDS], self.configuration.poll_interval)
        self.assertEqual(job_arguments[C_JOB_ID], jira_agent.C_SCHEDULER_JOB_ID)
        self.assertEqual(job_arguments[C_JOB_MAX_INSTANCES], jira_agent.C_ONE)
        self.assertTrue(job_arguments[C_JOB_COALESCE])
        self.assertTrue(job_arguments[C_JOB_REPLACE_EXISTING])
        self.assertLessEqual(job_arguments[C_JOB_NEXT_RUN_TIME], jira_agent.datetime.now(jira_agent.timezone.utc))
        scheduler.shutdown.assert_called_once_with(wait=True)

    def test_scheduler_failure_does_not_prevent_next_batch(self) -> None:
        """A transient batch error must not terminate future scheduled runs."""
        runtime = jira_agent.JiraAgentScheduler(self.configuration)
        with patch.object(jira_agent, C_METHOD_WORKER) as worker_type:
            worker_type.return_value.run_once.side_effect = [RuntimeError(C_ERROR), jira_agent.C_ZERO]
            self.assertEqual(runtime.run_batch(), jira_agent.C_ONE)
            self.assertEqual(runtime.run_batch(), jira_agent.C_ZERO)
        self.assertEqual(worker_type.call_count, C_EXPECTED_RECURRING_CALLS)

    def test_scheduler_reload_preserves_csv_updates_between_batches(self) -> None:
        """Each batch must reload history rather than overwrite another run's completion."""
        runtime = jira_agent.JiraAgentScheduler(self.configuration)
        with patch.object(jira_agent.JiraClient, C_METHOD_FIND_ISSUES, return_value=[]):
            self.assertEqual(runtime.run_batch(), jira_agent.C_ZERO)
            self.worker.ticket_report.record_finished(C_ISSUE_KEY, implemented=True)
            self.assertEqual(runtime.run_batch(), jira_agent.C_ZERO)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])

    def test_overlapping_scheduler_does_not_clear_active_csv(self) -> None:
        """A second process must skip before touching the first process's current ticket."""
        self.worker.ticket_report.record_started(C_ISSUE_KEY)
        runtime = jira_agent.JiraAgentScheduler(self.configuration)
        with jira_agent.RepositoryRunLock(self.report_directory.name):
            with patch.object(jira_agent, C_METHOD_WORKER) as worker_type:
                self.assertEqual(runtime.run_batch(), jira_agent.C_ZERO)
                worker_type.assert_not_called()
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_EMPTY_OUTPUT,
            jira_agent.C_CSV_CURRENT_TICKET: C_ISSUE_KEY,
        }])

    def test_real_scheduler_executes_multiple_batches_and_stops(self) -> None:
        """Exercise actual APScheduler timing and shutdown without Jira or CLI execution."""
        configuration = replace(self.configuration, poll_interval=C_TEST_POLL_INTERVAL)
        runtime = jira_agent.JiraAgentScheduler(configuration)
        recurring_run = threading.Event()
        batch_count = jira_agent.C_ZERO

        def observe_batch() -> int:
            """Signal when the immediate run and a later interval have both executed."""
            nonlocal batch_count
            batch_count += jira_agent.C_ONE
            if batch_count >= C_EXPECTED_RECURRING_CALLS:
                recurring_run.set()
            return jira_agent.C_ZERO

        with patch.object(runtime, C_METHOD_BATCH, side_effect=observe_batch):
            scheduler_thread = threading.Thread(target=runtime.start, daemon=True)
            scheduler_thread.start()
            try:
                self.assertTrue(recurring_run.wait(C_TEST_SCHEDULER_TIMEOUT))
            finally:
                if runtime.scheduler.running:
                    runtime.scheduler.shutdown(wait=True)
                scheduler_thread.join(C_TEST_SCHEDULER_TIMEOUT)
            self.assertFalse(scheduler_thread.is_alive())
        self.assertGreaterEqual(batch_count, C_EXPECTED_RECURRING_CALLS)

    def test_main_starts_scheduler_without_running_a_batch_directly(self) -> None:
        """Launching the script must hand lifecycle control to APScheduler."""
        with patch.dict(os.environ, C_TEST_ENVIRONMENT, clear=True):
            with patch.object(jira_agent, C_METHOD_DOTENV_VALUES, return_value={}):
                with (
                    patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type,
                    patch.object(jira_agent.JiraClient, C_METHOD_VERIFY_CONNECTION) as verify_connection,
                ):
                    console_output = io.StringIO()
                    with redirect_stdout(console_output):
                        self.assertEqual(jira_agent.main(), jira_agent.C_ZERO)
                    messages = console_output.getvalue()
                    self.assertIn(jira_agent.C_LOG_JIRA_URL.format(url=self.configuration.jira_url), messages)
                    self.assertIn(jira_agent.C_LOG_JIRA_EMAIL.format(email=self.configuration.jira_email), messages)
                    self.assertIn(jira_agent.C_LOG_JIRA_PROJECT.format(project=self.configuration.jira_project), messages)
                    self.assertIn(jira_agent.C_LOG_API_TOKEN_LOADED, messages)
                    self.assertNotIn(self.configuration.jira_token, messages)
                    verify_connection.assert_called_once_with()
                    scheduler_type.return_value.start.assert_called_once_with()

    def test_main_loads_worker_local_file_before_starting_scheduler(self) -> None:
        """The entry point must resolve its local dotenv path and apply file configuration."""
        with patch.dict(os.environ, C_EMPTY_ENVIRONMENT, clear=True):
            with patch.object(jira_agent, C_ENV_FILE_PATH_ATTRIBUTE, self.write_environment_file()):
                with (
                    patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type,
                    patch.object(jira_agent.JiraClient, C_METHOD_VERIFY_CONNECTION) as verify_connection,
                ):
                    console_output = io.StringIO()
                    with redirect_stdout(console_output):
                        self.assertEqual(jira_agent.main(), jira_agent.C_ZERO)
                    verify_connection.assert_called_once_with()
                    configuration = scheduler_type.call_args.args[C_FIRST_CALL_INDEX]
                    messages = console_output.getvalue()
                    self.assertIn(jira_agent.C_LOG_JIRA_URL.format(url=configuration.jira_url), messages)
                    self.assertIn(jira_agent.C_LOG_JIRA_EMAIL.format(email=configuration.jira_email), messages)
                    self.assertIn(jira_agent.C_LOG_JIRA_PROJECT.format(project=configuration.jira_project), messages)
                    self.assertIn(jira_agent.C_LOG_API_TOKEN_LOADED, messages)
                    self.assertNotIn(configuration.jira_token, messages)
                    self.assertEqual(configuration.jira_status, C_FILE_JIRA_STATUS)
                    self.assertEqual(configuration.poll_interval, C_FILE_POLL_INTERVAL)
                    scheduler_type.return_value.start.assert_called_once_with()

    def test_main_checks_connection_before_constructing_scheduler(self) -> None:
        """No scheduler instance may exist until the startup authentication test succeeds."""
        with (
            patch.object(jira_agent.AgentConfiguration, C_METHOD_CONFIGURATION, return_value=self.configuration),
            patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type,
            patch.object(jira_agent.JiraClient, C_METHOD_VERIFY_CONNECTION) as verify_connection,
        ):
            def verify_before_scheduling() -> None:
                """Assert the scheduler has not been created when authentication is checked."""
                scheduler_type.assert_not_called()

            verify_connection.side_effect = verify_before_scheduling
            console_output = io.StringIO()
            with redirect_stdout(console_output):
                self.assertEqual(jira_agent.main(), jira_agent.C_ZERO)
            self.assertIn(jira_agent.C_LOG_CONNECTION_VALID, console_output.getvalue())
            scheduler_type.return_value.start.assert_called_once_with()

    def test_main_stops_without_ticket_activity_when_startup_check_fails(self) -> None:
        """A failed preflight must exit nonzero without starting scheduling or writing a CSV."""
        failure_message = C_MESSAGE_SEPARATOR.join((
            jira_agent.C_ERROR_JIRA_UNAUTHORIZED, self.configuration.jira_token,
        ))
        with (
            patch.object(jira_agent.AgentConfiguration, C_METHOD_CONFIGURATION, return_value=self.configuration),
            patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type,
            patch.object(jira_agent.JiraClient, C_METHOD_VERIFY_CONNECTION,
                         side_effect=RuntimeError(failure_message)),
            patch.object(jira_agent, C_METHOD_WORKER) as worker_type,
        ):
            console_output = io.StringIO()
            with redirect_stdout(console_output):
                self.assertEqual(jira_agent.main(), jira_agent.C_ONE)
            scheduler_type.assert_not_called()
            worker_type.assert_not_called()
        messages = console_output.getvalue()
        self.assertIn(jira_agent.C_ERROR_JIRA_UNAUTHORIZED, messages)
        self.assertNotIn(jira_agent.C_LOG_CONNECTION_VALID, messages)
        self.assertNotIn(self.configuration.jira_token, messages)
        self.assertIn(jira_agent.C_REDACTED, messages)
        self.assertFalse(self.report_path.exists())

    def test_module_entry_point_calls_main(self) -> None:
        """The documented module command must dispatch to the scheduler's main function."""
        with patch.object(jira_agent, C_METHOD_MAIN, return_value=C_SUCCESS_CODE) as entry_point:
            with self.assertRaises(SystemExit) as exit_context:
                runpy.run_module(C_MODULE_ENTRY_POINT, run_name=C_MAIN_MODULE)
        self.assertEqual(exit_context.exception.code, C_SUCCESS_CODE)
        entry_point.assert_called_once_with()


if __name__ == C_MAIN_MODULE:
    unittest.main()
