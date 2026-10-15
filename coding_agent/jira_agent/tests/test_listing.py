"""Verify authenticated listing commands, pagination, and isolation from coding work."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from coding_agent.jira_agent import jira_agent

C_TEST_ENVIRONMENT = {
    jira_agent.C_ENV_JIRA_URL: "https://example.atlassian.net",
    jira_agent.C_ENV_JIRA_EMAIL: "listing@example.com",
    jira_agent.C_ENV_JIRA_TOKEN: "listing-test-secret",
    jira_agent.C_ENV_JIRA_PROJECT: "Project Name",
}
C_FIRST_KEY = "PROJ-1"
C_SECOND_KEY = "PROJ-2"
C_FIRST_SUMMARY = "First ticket"
C_SECOND_SUMMARY = "Completed ticket"
C_STATUS_OPEN = "Open"
C_STATUS_DONE = "Done"
C_PROJECT_KEY = "PROJ"
C_SECOND_PROJECT_KEY = "OTHER"
C_PROJECT_NAME = "Project Name"
C_SECOND_PROJECT_NAME = "Other Project"
C_PROJECT_OVERRIDE = 'Quoted "Project"'
C_VALID_USER = {jira_agent.C_KEY_ACCOUNT_ID: "listing-account", jira_agent.C_KEY_ACTIVE: True}
C_TOKEN = "next-page-token"
C_PAGE_FIRST = 0
C_PAGE_SECOND = 1
C_ARGUMENT_ERROR = 2
C_FLAG_HELP = "--help"
C_FLAG_UNKNOWN = "--unknown-option"
C_METHOD_DOTENV = "dotenv_values"
C_METHOD_SESSION = "Session"
C_METHOD_SCHEDULER = "JiraAgentScheduler"
C_METHOD_WORKER = "JiraAgentWorker"
C_METHOD_REPORT = "TicketCsvReport"
C_METHOD_LOCK = "RepositoryRunLock"
C_PARAMETERS_KEY = "params"
C_STATUS_FILTER = "status ="
C_HISTORY_FILTER = "NOT IN"
C_EMPTY_TEXT = ""
C_ERROR = "Jira listing service failed"
C_TICKET_ROWS = [
    {
        jira_agent.C_KEY_ISSUE_KEY: C_FIRST_KEY,
        jira_agent.C_KEY_FIELDS: {
            jira_agent.C_KEY_SUMMARY: C_FIRST_SUMMARY,
            jira_agent.C_KEY_STATUS: {jira_agent.C_KEY_NAME: C_STATUS_OPEN},
        },
    },
    {
        jira_agent.C_KEY_ISSUE_KEY: C_SECOND_KEY,
        jira_agent.C_KEY_FIELDS: {
            jira_agent.C_KEY_SUMMARY: C_SECOND_SUMMARY,
            jira_agent.C_KEY_STATUS: {jira_agent.C_KEY_NAME: C_STATUS_DONE},
        },
    },
]
C_PROJECT_ROWS = [
    {jira_agent.C_KEY_ISSUE_KEY: C_PROJECT_KEY, jira_agent.C_KEY_NAME: C_PROJECT_NAME},
    {jira_agent.C_KEY_ISSUE_KEY: C_SECOND_PROJECT_KEY, jira_agent.C_KEY_NAME: C_SECOND_PROJECT_NAME},
]


class JiraListingTests(unittest.TestCase):
    """Use fake Jira pages to exercise listing without external requests or workspace changes."""

    def setUp(self) -> None:
        """Create an isolated repository path and inert Jira settings for every test."""
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.repository_directory = Path(temporary_directory.name)
        self.environment = dict(C_TEST_ENVIRONMENT)
        self.environment[jira_agent.C_ENV_REPOSITORY_DIRECTORY] = str(self.repository_directory)
        self.configuration = jira_agent.AgentConfiguration.from_environment(self.environment)

    def create_client(self, pages: list[dict]) -> tuple[jira_agent.JiraClient, Mock]:
        """Return a client whose session supplies deterministic JSON pages."""
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.side_effect = pages
        return jira_agent.JiraClient(self.configuration, session), session

    def run_listing(self, arguments: list[str], pages: list[dict | Exception]) -> tuple[int, str, Mock]:
        """Run the real entry point while forbidding scheduler, worker, CSV, and lock creation."""
        session = Mock()
        session.request.return_value.content = True
        session.request.return_value.json.side_effect = [C_VALID_USER, *pages]
        console_output = io.StringIO()
        with (
            patch.dict(jira_agent.os.environ, self.environment, clear=True),
            patch.object(jira_agent, C_METHOD_DOTENV, return_value={}),
            patch.object(jira_agent.requests, C_METHOD_SESSION, return_value=session),
            patch.object(jira_agent, C_METHOD_SCHEDULER) as scheduler_type,
            patch.object(jira_agent, C_METHOD_WORKER) as worker_type,
            patch.object(jira_agent, C_METHOD_REPORT) as report_type,
            patch.object(jira_agent, C_METHOD_LOCK) as lock_type,
            redirect_stdout(console_output),
        ):
            result = jira_agent.main(arguments)
            scheduler_type.assert_not_called()
            worker_type.assert_not_called()
            report_type.assert_not_called()
            lock_type.assert_not_called()
        self.assertEqual(list(self.repository_directory.iterdir()), [])
        messages = console_output.getvalue()
        self.assertNotIn(self.configuration.jira_token, messages)
        return result, messages, session

    def test_command_line_selects_scheduler_and_optional_ticket_project(self) -> None:
        """Keep no-flag scheduling and support both configured and explicit listing projects."""
        self.assertEqual(jira_agent.JiraAgentCommandLine.parse([]), jira_agent.JiraAgentCommandLine())
        self.assertEqual(jira_agent.JiraAgentCommandLine.parse([jira_agent.C_FLAG_TICKETS]),
                         jira_agent.JiraAgentCommandLine(tickets=True))
        self.assertEqual(jira_agent.JiraAgentCommandLine.parse([jira_agent.C_FLAG_TICKETS, C_PROJECT_OVERRIDE]),
                         jira_agent.JiraAgentCommandLine(tickets=True, project=C_PROJECT_OVERRIDE))
        self.assertEqual(jira_agent.JiraAgentCommandLine.parse([jira_agent.C_FLAG_PROJECTS]),
                         jira_agent.JiraAgentCommandLine(projects=True))

    def test_conflicting_and_unknown_flags_stop_before_loading_settings(self) -> None:
        """Reject ambiguous commands before authentication or configuration access."""
        for arguments in ([jira_agent.C_FLAG_TICKETS, jira_agent.C_FLAG_PROJECTS], [C_FLAG_UNKNOWN]):
            with self.subTest(arguments=arguments):
                with patch.object(jira_agent, C_METHOD_DOTENV) as load_settings, redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_context:
                        jira_agent.main(arguments)
                    self.assertEqual(exit_context.exception.code, C_ARGUMENT_ERROR)
                    load_settings.assert_not_called()

    def test_help_needs_no_configuration_or_connection(self) -> None:
        """Allow discovering listing syntax without credentials or Jira connectivity."""
        console_output = io.StringIO()
        with patch.object(jira_agent, C_METHOD_DOTENV) as load_settings, redirect_stdout(console_output):
            with self.assertRaises(SystemExit) as exit_context:
                jira_agent.main([C_FLAG_HELP])
            self.assertEqual(exit_context.exception.code, jira_agent.C_ZERO)
            load_settings.assert_not_called()
        self.assertIn(jira_agent.C_FLAG_TICKETS, console_output.getvalue())
        self.assertIn(jira_agent.C_FLAG_PROJECTS, console_output.getvalue())

    def test_tickets_follow_token_pagination_without_worker_filters(self) -> None:
        """Collect every status and follow continuation tokens even for short pages."""
        client, session = self.create_client([
            {jira_agent.C_KEY_ISSUES: C_TICKET_ROWS[:C_PAGE_SECOND], jira_agent.C_KEY_NEXT_PAGE_TOKEN: C_TOKEN,
             jira_agent.C_KEY_IS_LAST: False},
            {jira_agent.C_KEY_ISSUES: C_TICKET_ROWS[C_PAGE_SECOND:], jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(client.list_project_tickets(), C_TICKET_ROWS)
        first_parameters = session.request.call_args_list[C_PAGE_FIRST].kwargs[C_PARAMETERS_KEY]
        last_parameters = session.request.call_args_list[C_PAGE_SECOND].kwargs[C_PARAMETERS_KEY]
        query = first_parameters[jira_agent.C_KEY_QUERY]
        self.assertIn(jira_agent.json.dumps(C_PROJECT_NAME), query)
        self.assertNotIn(C_STATUS_FILTER, query)
        self.assertNotIn(C_HISTORY_FILTER, query)
        self.assertNotIn(jira_agent.C_KEY_NEXT_PAGE_TOKEN, first_parameters)
        self.assertEqual(last_parameters[jira_agent.C_KEY_NEXT_PAGE_TOKEN], C_TOKEN)

    def test_projects_follow_actual_offset_instead_of_requested_page_size(self) -> None:
        """Handle Jira returning fewer projects per page than the requested maximum."""
        client, session = self.create_client([
            {jira_agent.C_KEY_VALUES: C_PROJECT_ROWS[:C_PAGE_SECOND], jira_agent.C_KEY_START_AT: C_PAGE_FIRST,
             jira_agent.C_KEY_IS_LAST: False},
            {jira_agent.C_KEY_VALUES: C_PROJECT_ROWS[C_PAGE_SECOND:], jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(client.list_projects(), C_PROJECT_ROWS)
        self.assertEqual(session.request.call_args.kwargs[C_PARAMETERS_KEY][jira_agent.C_KEY_START_AT],
                         C_PAGE_SECOND)

    def test_tickets_reject_missing_and_repeated_continuation_tokens(self) -> None:
        """Prevent partial-success reports and infinite loops when pagination is broken."""
        for pages in (
            [{jira_agent.C_KEY_ISSUES: [], jira_agent.C_KEY_IS_LAST: False}],
            [{jira_agent.C_KEY_ISSUES: [], jira_agent.C_KEY_NEXT_PAGE_TOKEN: C_TOKEN}] * C_ARGUMENT_ERROR,
        ):
            with self.subTest(pages=pages):
                client, session = self.create_client(pages)
                with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_LIST_PAGINATION):
                    client.list_project_tickets()

    def test_projects_reject_nonadvancing_pages(self) -> None:
        """An empty nonfinal project page must fail instead of silently truncating results."""
        client, session = self.create_client([{jira_agent.C_KEY_VALUES: [], jira_agent.C_KEY_IS_LAST: False}])
        with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_LIST_PAGINATION):
            client.list_projects()

    def test_malformed_pages_fail_instead_of_claiming_empty_results(self) -> None:
        """Reject unexpected API shapes for both listing endpoints."""
        for pages in ([{}], [{jira_agent.C_KEY_ISSUES: [C_FIRST_KEY]}]):
            with self.subTest(pages=pages):
                client, session = self.create_client(pages)
                with self.assertRaisesRegex(RuntimeError, jira_agent.C_ERROR_LIST_RESPONSE):
                    client.list_project_tickets()

    def test_tickets_command_authenticates_and_prints_all_statuses(self) -> None:
        """Run the listing entry point and display both open and completed tickets."""
        result, messages, session = self.run_listing([jira_agent.C_FLAG_TICKETS], [
            {jira_agent.C_KEY_ISSUES: C_TICKET_ROWS, jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(result, jira_agent.C_ZERO)
        self.assertIn(C_FIRST_KEY, messages)
        self.assertIn(C_STATUS_DONE, messages)
        self.assertIn(C_SECOND_SUMMARY, messages)
        self.assertTrue(session.request.call_args_list[C_PAGE_FIRST].args[C_PAGE_SECOND].endswith(
            jira_agent.C_CURRENT_USER_PATH,
        ))

    def test_projects_command_works_without_a_configured_project(self) -> None:
        """Discover available project keys before setting JIRA_PROJECT."""
        self.environment.pop(jira_agent.C_ENV_JIRA_PROJECT)
        result, messages, session = self.run_listing([jira_agent.C_FLAG_PROJECTS], [
            {jira_agent.C_KEY_VALUES: C_PROJECT_ROWS, jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(result, jira_agent.C_ZERO)
        self.assertIn(C_PROJECT_KEY, messages)
        self.assertIn(C_SECOND_PROJECT_NAME, messages)

    def test_explicit_ticket_project_overrides_environment_and_is_quoted(self) -> None:
        """Apply the optional project only to this listing and quote it safely in JQL."""
        result, messages, session = self.run_listing([jira_agent.C_FLAG_TICKETS, C_PROJECT_OVERRIDE], [
            {jira_agent.C_KEY_ISSUES: [], jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(result, jira_agent.C_ZERO)
        self.assertIn(jira_agent.json.dumps(C_PROJECT_OVERRIDE),
                      session.request.call_args.kwargs[C_PARAMETERS_KEY][jira_agent.C_KEY_QUERY])
        self.assertEqual(self.environment[jira_agent.C_ENV_JIRA_PROJECT], C_PROJECT_NAME)

    def test_empty_listing_and_later_page_failure_have_distinct_results(self) -> None:
        """Return success for empty results and failure when any later page cannot be fetched."""
        result, messages, session = self.run_listing([jira_agent.C_FLAG_PROJECTS], [
            {jira_agent.C_KEY_VALUES: [], jira_agent.C_KEY_IS_LAST: True},
        ])
        self.assertEqual(result, jira_agent.C_ZERO)
        self.assertIn(jira_agent.C_LOG_LIST_EMPTY, messages)
        result, messages, session = self.run_listing([jira_agent.C_FLAG_TICKETS], [
            {jira_agent.C_KEY_ISSUES: C_TICKET_ROWS, jira_agent.C_KEY_NEXT_PAGE_TOKEN: C_TOKEN},
            RuntimeError(C_ERROR),
        ])
        self.assertEqual(result, jira_agent.C_ONE)
        self.assertIn(C_ERROR, messages)
        self.assertNotIn(C_FIRST_SUMMARY, messages)
