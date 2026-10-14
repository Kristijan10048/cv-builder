"""Regression tests for the standalone Jira coding worker without external writes."""

import ast
import csv
import importlib
import json
import os
import subprocess
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import jira_agent

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

    def test_configuration_accepts_csv_path(self) -> None:
        """Allow the report location to be configured without changing source code."""
        environment = dict(C_TEST_ENVIRONMENT)
        environment[jira_agent.C_ENV_TICKET_CSV_PATH] = str(self.report_path)
        configuration = jira_agent.AgentConfiguration.from_environment(environment)
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
            with patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type:
                self.assertEqual(jira_agent.main(), jira_agent.C_ZERO)
                scheduler_type.return_value.start.assert_called_once_with()


if __name__ == C_MAIN_MODULE:
    unittest.main()
