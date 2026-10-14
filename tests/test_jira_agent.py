"""Regression tests for the standalone Jira coding worker without external writes."""

import ast
import csv
import importlib
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import jira_agent

C_TEST_ENVIRONMENT = {
    jira_agent.C_ENV_JIRA_URL: "https://example.atlassian.net/",
    jira_agent.C_ENV_JIRA_EMAIL: "worker@example.com",
    jira_agent.C_ENV_JIRA_TOKEN: "jira-test-secret",
    jira_agent.C_ENV_JIRA_PROJECT: "Project Name",
    jira_agent.C_ENV_GITHUB_TOKEN: "github-test-secret",
    jira_agent.C_ENV_GITHUB_REPOSITORY: "example/repository",
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
C_COMMENT_ERROR = "comment failed"
C_PULL_REQUEST_URL = "https://github.com/example/repository/pull/123"
C_SUCCESS_CODE = 0
C_FAILURE_CODE = 7
C_CHANGED_STATUS = " M source.py\n"
C_EMPTY_OUTPUT = ""
C_PADDING_CHARACTER = "x"
C_REDACTION_FAILURE = "Command diagnostics were truncated before credential redaction."
C_FIRST_CALL_INDEX = 0
C_LAST_CALL_INDEX = -1
C_ENVIRONMENT_KEY = "environment"
C_METHOD_CREATE_PULL_REQUEST = "create_pull_request"
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
C_METHOD_SLEEP = "sleep"


class JiraAgentTests(unittest.TestCase):
    """Exercise configuration, subprocess arguments, HTTP calls, and reporting."""

    def setUp(self) -> None:
        """Construct a worker with mocked collaborators and inert test credentials."""
        self.configuration = jira_agent.AgentConfiguration.from_environment(C_TEST_ENVIRONMENT)
        self.report_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.report_directory.cleanup)
        self.report_path = Path(self.report_directory.name) / jira_agent.C_DEFAULT_TICKET_CSV_PATH
        self.configuration = replace(self.configuration, ticket_csv_path=str(self.report_path))
        self.jira_client = Mock(spec=jira_agent.JiraClient)
        self.github_client = Mock(spec=jira_agent.GitHubClient)
        self.command_runner = Mock(spec=jira_agent.CommandRunner)
        self.worker = jira_agent.JiraAgentWorker(
            self.configuration, self.jira_client, self.github_client, self.command_runner,
        )
        self.issue = jira_agent.JiraIssue(C_ISSUE_KEY, C_SUMMARY, C_DESCRIPTION)

    def read_ticket_rows(self) -> list[dict[str, str]]:
        """Read the persisted CSV rather than relying on report object state."""
        with self.report_path.open(encoding=jira_agent.C_ENCODING, newline=C_EMPTY_OUTPUT) as report_file:
            reader = csv.DictReader(report_file)
            self.assertEqual(reader.fieldnames, list(jira_agent.C_CSV_COLUMNS))
            return list(reader)

    def test_configuration_accepts_csv_path(self) -> None:
        """Allow the report location to be configured without changing source code."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_TICKET_CSV_PATH] = str(self.report_path)
        configuration = jira_agent.AgentConfiguration.from_environment(environment)
        self.assertEqual(configuration.ticket_csv_path, str(self.report_path))

    def test_csv_shows_current_ticket_then_implemented_ticket(self) -> None:
        """Publish active work before coding and move it to completed history on success."""
        self.jira_client.claim_issue.return_value = True

        def check_active_report(issue: jira_agent.JiraIssue) -> str:
            """Inspect the file at the moment implementation begins."""
            self.assertEqual(issue, self.issue)
            self.assertEqual(self.read_ticket_rows(), [{
                jira_agent.C_CSV_IMPLEMENTED_TICKET: C_EMPTY_OUTPUT,
                jira_agent.C_CSV_CURRENT_TICKET: C_ISSUE_KEY,
            }])
            return C_PULL_REQUEST_URL

        with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST, side_effect=check_active_report):
            self.worker.process_issue(self.issue)
        self.assertEqual(self.read_ticket_rows(), [{
            jira_agent.C_CSV_IMPLEMENTED_TICKET: C_ISSUE_KEY,
            jira_agent.C_CSV_CURRENT_TICKET: C_EMPTY_OUTPUT,
        }])

    def test_csv_clears_failed_ticket_and_keeps_completed_history(self) -> None:
        """An implementation error must retain earlier successes without listing the failure."""
        self.worker.ticket_report.record_finished(C_SECOND_ISSUE_KEY, implemented=True)
        self.jira_client.claim_issue.return_value = True
        with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST, side_effect=RuntimeError(C_ERROR)):
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

    def test_poll_creates_empty_csv_without_ready_tickets(self) -> None:
        """An idle worker still creates a report with the requested columns."""
        self.jira_client.find_ready_issues.return_value = []
        with patch.object(jira_agent.time, C_METHOD_SLEEP, side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.worker.poll_forever()
        self.assertEqual(self.read_ticket_rows(), [])

    def test_unclaimed_ticket_does_not_write_csv(self) -> None:
        """Stale search results must not appear as work started by this worker."""
        self.jira_client.claim_issue.return_value = False
        with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST) as create_request:
            self.worker.process_issue(self.issue)
        create_request.assert_not_called()
        self.assertFalse(self.report_path.exists())

    def test_csv_failure_after_pr_creation_keeps_review_label(self) -> None:
        """A local report write failure must not turn a published PR into an agent failure."""
        self.jira_client.claim_issue.return_value = True
        with patch.object(self.worker.ticket_report, C_METHOD_WRITE, side_effect=[None, OSError(C_ERROR)]):
            with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST, return_value=C_PULL_REQUEST_URL):
                self.worker.process_issue(self.issue)
        self.jira_client.swap_label.assert_called_once_with(
            C_ISSUE_KEY, jira_agent.C_LABEL_IN_PROGRESS, jira_agent.C_LABEL_REVIEW,
        )

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
        """Prevent zero polling intervals and invalid subprocess timeouts."""
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
        """Dataclass diagnostics must not print either API credential."""
        representation = repr(self.configuration)
        self.assertNotIn(self.configuration.github_token, representation)
        self.assertNotIn(self.configuration.jira_token, representation)

    def test_posix_prompt_remains_one_argument(self) -> None:
        """Ticket quotes and newlines must not alter argument boundaries."""
        arguments = self.worker.build_agent_arguments(C_PROMPT, windows=False)
        self.assertEqual(arguments[C_PROMPT_ARGUMENT_INDEX], C_PROMPT)

    def test_windows_executable_preserves_backslashes(self) -> None:
        """A quoted Windows executable path must retain spaces and backslashes."""
        self.worker.configuration = replace(self.configuration, agent_command=C_WINDOWS_COMMAND)
        arguments = self.worker.build_agent_arguments(C_PROMPT, windows=True)
        self.assertEqual(arguments[C_EXECUTABLE_ARGUMENT_INDEX], C_WINDOWS_EXECUTABLE)
        self.assertEqual(arguments[C_PROMPT_ARGUMENT_INDEX], C_PROMPT)

    def test_branch_without_slug_uses_issue_key(self) -> None:
        """Non-Latin summaries must not create a branch ending in a hyphen."""
        issue = jira_agent.JiraIssue(C_ISSUE_KEY, C_EMPTY_OUTPUT, None)
        self.assertEqual(issue.build_branch_name(), C_ISSUE_KEY)

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

    def test_stale_search_result_is_not_claimed(self) -> None:
        """Live review/in-progress labels must override a stale ready search result."""
        for labels in (
            [jira_agent.C_LABEL_REVIEW],
            [jira_agent.C_LABEL_READY, jira_agent.C_LABEL_IN_PROGRESS],
        ):
            with self.subTest(labels=labels):
                session = Mock()
                session.request.return_value.content = True
                session.request.return_value.json.return_value = {
                    jira_agent.C_KEY_FIELDS: {jira_agent.C_KEY_LABELS: labels},
                }
                client = jira_agent.JiraClient(self.configuration, session)
                self.assertFalse(client.claim_issue(C_ISSUE_KEY))
                session.request.assert_called_once()

    def test_empty_http_response_is_not_decoded(self) -> None:
        """Successful Jira updates commonly return no JSON response body."""
        session = Mock()
        session.request.return_value.content = C_EMPTY_OUTPUT
        client = jira_agent.BaseHttpClient(session)
        self.assertEqual(client.request(jira_agent.C_METHOD_PUT, self.configuration.jira_url), {})
        session.request.return_value.raise_for_status.assert_called_once()
        session.request.return_value.json.assert_not_called()

    def test_failed_claim_does_not_modify_ticket(self) -> None:
        """A claim request error must leave existing labels alone."""
        self.jira_client.claim_issue.side_effect = requests.RequestException(C_ERROR)
        with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST) as create_request:
            self.worker.process_issue(self.issue)
        create_request.assert_not_called()
        self.jira_client.swap_label.assert_not_called()
        self.jira_client.add_comment.assert_not_called()

    def test_failed_comment_does_not_mark_created_pr_failed(self) -> None:
        """Reporting a published PR must retain the review state when comments fail."""
        self.jira_client.claim_issue.return_value = True
        self.jira_client.add_comment.side_effect = requests.RequestException(C_COMMENT_ERROR)
        with patch.object(self.worker, C_METHOD_CREATE_PULL_REQUEST, return_value=C_PULL_REQUEST_URL):
            self.worker.process_issue(self.issue)
        self.jira_client.swap_label.assert_called_once_with(
            C_ISSUE_KEY, jira_agent.C_LABEL_IN_PROGRESS, jira_agent.C_LABEL_REVIEW,
        )

    def test_failed_label_update_still_attempts_comment(self) -> None:
        """Independent reporting keeps the PR URL available despite a label API failure."""
        self.jira_client.swap_label.side_effect = requests.RequestException(C_ERROR)
        self.worker.report_result(C_ISSUE_KEY, jira_agent.C_LABEL_REVIEW, C_PULL_REQUEST_URL)
        self.jira_client.add_comment.assert_called_once_with(C_ISSUE_KEY, C_PULL_REQUEST_URL)

    def test_agent_failure_redacts_credentials_and_sets_failure_label(self) -> None:
        """Error reports must redact credentials and still attempt a failed transition."""
        self.jira_client.claim_issue.return_value = True
        self.jira_client.add_comment.side_effect = requests.RequestException(C_COMMENT_ERROR)
        with patch.object(
            self.worker, C_METHOD_CREATE_PULL_REQUEST, side_effect=RuntimeError(self.configuration.github_token),
        ):
            self.worker.process_issue(self.issue)
        self.jira_client.swap_label.assert_called_once_with(
            C_ISSUE_KEY, jira_agent.C_LABEL_IN_PROGRESS, jira_agent.C_LABEL_FAILED,
        )
        comment = self.jira_client.add_comment.call_args.args[C_LAST_CALL_INDEX]
        self.assertNotIn(self.configuration.github_token, comment)
        self.assertIn(jira_agent.C_REDACTED, comment)

    def test_process_environments_keep_secrets_out_of_agent(self) -> None:
        """Only clone/push receive ephemeral Git headers; the agent receives no API tokens."""
        with patch.dict(os.environ, C_TEST_ENVIRONMENT, clear=True):
            agent_environment = self.worker.build_process_environment()
            git_environment = self.worker.build_process_environment(authenticate_git=True)
        self.assertNotIn(jira_agent.C_ENV_GITHUB_TOKEN, agent_environment)
        self.assertNotIn(jira_agent.C_ENV_JIRA_TOKEN, agent_environment)
        self.assertNotIn(jira_agent.C_GIT_AUTH_CONFIG_VALUE, agent_environment)
        self.assertEqual(
            git_environment[jira_agent.C_GIT_HELPER_CONFIG_VALUE], jira_agent.C_EMPTY_TEXT,
        )
        self.assertIn(jira_agent.C_GIT_AUTH_CONFIG_VALUE, git_environment)

    def test_create_pr_uses_clean_remote_and_redacted_output(self) -> None:
        """The complete workflow must keep credentials out of Git arguments and the PR."""
        successful_command = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=C_EMPTY_OUTPUT, stderr=C_EMPTY_OUTPUT,
        )
        agent_result = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=self.configuration.github_token, stderr=C_EMPTY_OUTPUT,
        )
        status_result = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=C_CHANGED_STATUS, stderr=C_EMPTY_OUTPUT,
        )
        self.command_runner.run.side_effect = [
            successful_command, successful_command, agent_result, status_result,
            successful_command, successful_command, successful_command,
        ]
        self.github_client.open_pull_request.return_value = C_PULL_REQUEST_URL
        self.assertEqual(self.worker.create_pull_request(self.issue), C_PULL_REQUEST_URL)
        for command_call in self.command_runner.run.call_args_list:
            self.assertNotIn(self.configuration.github_token, repr(command_call.args))
        first_call = self.command_runner.run.call_args_list[C_FIRST_CALL_INDEX]
        self.assertIn(jira_agent.C_GIT_AUTH_CONFIG_VALUE, first_call.kwargs[C_ENVIRONMENT_KEY])
        body = self.github_client.open_pull_request.call_args.args[C_LAST_CALL_INDEX]
        self.assertNotIn(self.configuration.github_token, body)
        self.assertIn(jira_agent.C_REDACTED, body)

    def test_no_changes_does_not_commit_or_open_pr(self) -> None:
        """An unchanged repository must fail before staging, pushing, or publishing."""
        self.command_runner.run.return_value = subprocess.CompletedProcess(
            [], C_SUCCESS_CODE, stdout=C_EMPTY_OUTPUT, stderr=C_EMPTY_OUTPUT,
        )
        with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_NO_CHANGES):
            self.worker.create_pull_request(self.issue)
        self.github_client.open_pull_request.assert_not_called()

    def test_command_failure_preserves_diagnostic_output(self) -> None:
        """A CLI failure that writes to stdout must retain the relevant diagnostic."""
        result = subprocess.CompletedProcess(
            [], C_FAILURE_CODE, stdout=C_ERROR, stderr=C_EMPTY_OUTPUT,
        )
        with patch.object(subprocess, C_METHOD_RUN, return_value=result):
            with self.assertRaisesRegex(RuntimeError, C_ERROR):
                jira_agent.CommandRunner().run([jira_agent.C_GIT_EXECUTABLE])


    def test_long_command_error_is_redacted_before_truncation(self) -> None:
        """Redact entire command output before trimming the Jira failure report."""
        diagnostic = self.configuration.github_token + C_PADDING_CHARACTER * jira_agent.C_OUTPUT_LIMIT
        result = subprocess.CompletedProcess(
            [], C_FAILURE_CODE, stdout=diagnostic, stderr=C_EMPTY_OUTPUT,
        )
        with patch.object(subprocess, C_METHOD_RUN, return_value=result):
            with self.assertRaises(RuntimeError) as failure:
                jira_agent.CommandRunner().run([jira_agent.C_GIT_EXECUTABLE])
        self.jira_client.claim_issue.return_value = True
        with patch.object(
            self.worker, C_METHOD_CREATE_PULL_REQUEST, side_effect=failure.exception,
        ):
            self.worker.process_issue(self.issue)
        comment = self.jira_client.add_comment.call_args.args[C_LAST_CALL_INDEX]
        self.assertIn(jira_agent.C_REDACTED, comment, C_REDACTION_FAILURE)
        self.assertNotIn(self.configuration.github_token, comment)

    def test_runtime_literals_are_named_constants(self) -> None:
        """Check the reviewed module for hardcoded runtime strings or numbers."""
        syntax_tree = ast.parse(Path(jira_agent.__file__).read_text(encoding=C_ENCODING))
        for node in ast.walk(syntax_tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if node.body and isinstance(node.body[C_FIRST_CALL_INDEX], ast.Expr):
                    if ast.get_docstring(node):
                        node.body = node.body[jira_agent.C_QUOTE_LENGTH:]
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


if __name__ == C_MAIN_MODULE:
    unittest.main()
