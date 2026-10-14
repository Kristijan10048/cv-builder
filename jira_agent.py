#!/usr/bin/env python3
"""Schedule Jira batches with APScheduler, implement locally, and persist CSV state."""

from __future__ import annotations

import csv
import errno
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

import requests
from apscheduler.schedulers.blocking import BlockingScheduler

C_EMPTY_TEXT = ""
C_SLASH = "/"
C_ZERO = 0
C_ONE = 1
C_LAST_CHARACTER = -1
C_MIN_QUOTED_LENGTH = 2
C_QUOTE_CHARACTERS = "\"'"
C_WINDOWS_PLATFORM = "nt"
C_ENCODING = "utf-8"
C_ENCODING_ERRORS = "replace"
C_MAIN_MODULE = "__main__"
C_HTTP_TIMEOUT = 30
C_COMMAND_TIMEOUT = 300
C_DEFAULT_AGENT_TIMEOUT = 1800
C_DEFAULT_POLL_INTERVAL = 600
C_DEFAULT_JIRA_STATUS = "Waiting for AI Developer"
C_SEARCH_LIMIT = 5
C_ERROR_LIMIT = 1800
C_ENV_JIRA_URL = "JIRA_URL"
C_ENV_JIRA_EMAIL = "JIRA_EMAIL"
C_ENV_JIRA_TOKEN = "JIRA_API_TOKEN"
C_ENV_JIRA_PROJECT = "JIRA_PROJECT"
C_ENV_JIRA_STATUS = "JIRA_STATUS"
C_ENV_POLL_INTERVAL = "POLL_INTERVAL"
C_ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
C_ENV_AGENT_COMMAND = "AGENT_CMD"
C_ENV_AGENT_TIMEOUT = "AGENT_TIMEOUT"
C_ENV_REPOSITORY_DIRECTORY = "JIRA_AGENT_REPOSITORY"
C_ENV_TICKET_CSV_PATH = "JIRA_AGENT_CSV_PATH"
C_DEFAULT_TICKET_CSV_PATH = "jira_agent_tickets.csv"
C_CSV_IMPLEMENTED_TICKET = "implemented_ticket"
C_CSV_CURRENT_TICKET = "currently_implementing_ticket"
C_CSV_COLUMNS = (C_CSV_IMPLEMENTED_TICKET, C_CSV_CURRENT_TICKET)
C_FILE_READ_MODE = "r"
C_FILE_WRITE_MODE = "w"
C_LOCK_FILE_MODE = "r+b"
C_LOCK_CREATE_MODE = "xb"
C_LOCK_FILE_NAME = ".jira_agent.lock"
C_LOCK_BYTE = b"0"
C_CSV_TEMP_SUFFIX = ".tmp"
C_PROMPT_PLACEHOLDER = "{prompt}"
C_DEFAULT_AGENT_COMMAND = "codex --ask-for-approval never exec --sandbox workspace-write {prompt}"
C_ISSUE_KEY_PATTERN = r"[A-Za-z][A-Za-z0-9_]*-[0-9]+"
C_API_PATH = "/rest/api/2"
C_SEARCH_PATH = "/search/jql"
C_METHOD_GET = "GET"
C_KEY_ISSUES = "issues"
C_KEY_ISSUE_KEY = "key"
C_KEY_FIELDS = "fields"
C_KEY_SUMMARY = "summary"
C_KEY_DESCRIPTION = "description"
C_KEY_QUERY = "jql"
C_KEY_MAX_RESULTS = "maxResults"
C_SEARCH_FIELDS = "summary,description"
C_JQL_TEMPLATE = (
    "project = {project} AND status = {status} "
    "ORDER BY created ASC"
)
C_JQL_EXCLUSION = "AND key NOT IN ({keys}) "
C_JQL_KEY_SEPARATOR = ", "
C_JQL_ORDER = "ORDER BY created ASC"
C_SUCCESS_MARKER_TEMPLATE = "JIRA_AGENT_IMPLEMENTED:{issue_key}"
C_PROMPT_TEMPLATE = (
    "You are working on Jira ticket {issue_key}.\n\n"
    "Title: {summary}\n\nDescription:\n{description}\n\n"
    "Implement the change and run appropriate tests. "
    "Follow CLAUDE.md / AGENTS.md if present. Preserve existing unrelated changes. "
    "Do not touch CI config, secrets, the ticket CSV, or the worker lock file. "
    "Do not commit, push, create a PR, or send messages; leave changes locally. "
    "Only after implementation is complete and validation passes, end your final "
    "response with this exact line: {success_marker}\n"
    "If blocked or validation fails, explain the problem and omit that line."
)
C_MISSING_DESCRIPTION = "(none)"
C_LOG_STARTED = "[{issue_key}] started"
C_LOG_IMPLEMENTED = "[{issue_key}] implemented"
C_LOG_SKIPPED = "[{issue_key}] already implemented; skipped"
C_LOG_FAILURE = "[{issue_key}] failed: {error}"
C_LOG_REPORT_FAILURE = "[{issue_key}] CSV update failed: {error}"
C_LOG_BATCH = "Fetching one batch of Jira tickets..."
C_LOG_BATCH_FAILURE = "Jira batch failed: {error}"
C_LOG_LOCKED = "Another Jira agent run is active; skipping this invocation."
C_LOG_SCHEDULER_STARTED = "Scheduling Jira status '{status}' every {seconds} seconds; first batch starts now."
C_LOG_SCHEDULER_STOPPED = "Jira scheduler stopped."
C_LOG_SCHEDULED_FAILURE = "Scheduled Jira batch failed; retrying at the next interval."
C_SCHEDULER_JOB_ID = "jira-implementation-batch"
C_SCHEDULER_TRIGGER = "interval"
C_SCHEDULER_TIMEZONE = "UTC"
C_ERROR_REQUIRED_SETTING = "Missing required environment setting: {setting}"
C_ERROR_POSITIVE_SETTING = "{setting} must be a positive integer."
C_ERROR_PROMPT = "AGENT_CMD must contain a {prompt} placeholder."
C_ERROR_ISSUE_KEY = "Invalid Jira issue key."
C_ERROR_REPOSITORY = "JIRA_AGENT_REPOSITORY must be an existing directory."
C_ERROR_COMMAND = "Command failed with exit code {return_code}:\n{output}"
C_ERROR_NO_CHANGES = "Agent made no new changes."
C_ERROR_INCOMPLETE = "Agent did not confirm implementation and successful validation."
C_ERROR_CSV_COLUMNS = "Ticket CSV must have columns: implemented_ticket, currently_implementing_ticket."
C_REDACTED = "[REDACTED]"
C_GIT_EXECUTABLE = "git"
C_GIT_DIFF_ARGUMENTS = ("diff", "--binary", "HEAD", "--")
C_CURRENT_DIRECTORY = "."
C_GIT_UNTRACKED_ARGUMENTS = ("ls-files", "--others", "--exclude-standard", "-z", "--", ".")
C_NULL_SEPARATOR = "\0"
C_GIT_CONFIG_COUNT = "GIT_CONFIG_COUNT"
C_GIT_CONFIG_KEY_PREFIX = "GIT_CONFIG_KEY_"
C_GIT_CONFIG_VALUE_PREFIX = "GIT_CONFIG_VALUE_"


@dataclass(frozen=True)
class AgentConfiguration:
    """Keep Jira credentials and local implementation settings."""

    jira_url: str
    jira_email: str
    jira_token: str = field(repr=False)
    jira_project: str
    repository_directory: str
    agent_command: str = C_DEFAULT_AGENT_COMMAND
    agent_timeout: int = C_DEFAULT_AGENT_TIMEOUT
    ticket_csv_path: str = C_DEFAULT_TICKET_CSV_PATH
    jira_status: str = C_DEFAULT_JIRA_STATUS
    poll_interval: int = C_DEFAULT_POLL_INTERVAL

    @classmethod
    def from_environment(class_type, environment: Mapping[str, str]) -> AgentConfiguration:
        """Validate Jira selection, agent settings, and the recurring batch interval."""
        for setting in (C_ENV_JIRA_URL, C_ENV_JIRA_EMAIL, C_ENV_JIRA_TOKEN, C_ENV_JIRA_PROJECT):
            if not environment.get(setting, C_EMPTY_TEXT).strip():
                raise ValueError(C_ERROR_REQUIRED_SETTING.format(setting=setting))
        repository_directory = Path(environment.get(
            C_ENV_REPOSITORY_DIRECTORY, str(Path(__file__).resolve().parent),
        )).resolve()
        if not repository_directory.is_dir():
            raise ValueError(C_ERROR_REPOSITORY)
        agent_command = environment.get(C_ENV_AGENT_COMMAND, C_DEFAULT_AGENT_COMMAND)
        if C_PROMPT_PLACEHOLDER not in agent_command:
            raise ValueError(C_ERROR_PROMPT)
        jira_status = environment.get(C_ENV_JIRA_STATUS, C_DEFAULT_JIRA_STATUS).strip()
        if not jira_status:
            raise ValueError(C_ERROR_REQUIRED_SETTING.format(setting=C_ENV_JIRA_STATUS))
        report_path = Path(environment.get(C_ENV_TICKET_CSV_PATH, C_DEFAULT_TICKET_CSV_PATH))
        if not report_path.is_absolute():
            report_path = repository_directory / report_path
        return class_type(
            jira_url=environment[C_ENV_JIRA_URL].rstrip(C_SLASH),
            jira_email=environment[C_ENV_JIRA_EMAIL],
            jira_token=environment[C_ENV_JIRA_TOKEN],
            jira_project=environment[C_ENV_JIRA_PROJECT],
            repository_directory=str(repository_directory),
            agent_command=agent_command,
            agent_timeout=class_type.read_positive_integer(
                environment, C_ENV_AGENT_TIMEOUT, C_DEFAULT_AGENT_TIMEOUT,
            ),
            ticket_csv_path=str(report_path.resolve()),
            jira_status=jira_status,
            poll_interval=class_type.read_positive_integer(
                environment, C_ENV_POLL_INTERVAL, C_DEFAULT_POLL_INTERVAL,
            ),
        )

    @staticmethod
    def read_positive_integer(
        environment: Mapping[str, str], setting: str, default_value: int,
    ) -> int:
        """Reject invalid or nonpositive timeouts and polling intervals."""
        try:
            duration = int(environment.get(setting, str(default_value)))
        except ValueError as exception:
            raise ValueError(C_ERROR_POSITIVE_SETTING.format(setting=setting)) from exception
        if duration <= C_ZERO:
            raise ValueError(C_ERROR_POSITIVE_SETTING.format(setting=setting))
        return duration

    def redact(self, text: str) -> str:
        """Remove the Jira token and its URL-encoded representation from diagnostics."""
        for secret in (quote(self.jira_token, safe=C_EMPTY_TEXT), self.jira_token):
            if secret:
                text = text.replace(secret, C_REDACTED)
        return text


@dataclass(frozen=True)
class JiraIssue:
    """Represent Jira fields needed to implement a local coding task."""

    issue_key: str
    summary: str
    description: str | None

    @classmethod
    def from_response(class_type, response: dict) -> JiraIssue:
        """Extract ticket fields and validate the key used in completion markers."""
        issue_key = response[C_KEY_ISSUE_KEY]
        if not re.fullmatch(C_ISSUE_KEY_PATTERN, issue_key):
            raise ValueError(C_ERROR_ISSUE_KEY)
        issue_fields = response[C_KEY_FIELDS]
        return class_type(issue_key, issue_fields[C_KEY_SUMMARY], issue_fields.get(C_KEY_DESCRIPTION))

    def build_prompt(self) -> str:
        """Combine ticket details with implementation and completion instructions."""
        return C_PROMPT_TEMPLATE.format(
            issue_key=self.issue_key, summary=self.summary,
            description=self.description or C_MISSING_DESCRIPTION,
            success_marker=C_SUCCESS_MARKER_TEMPLATE.format(issue_key=self.issue_key),
        )


class BaseHttpClient:
    """Share bounded requests and HTTP status checking."""

    def __init__(self, session: requests.Session | None = None) -> None:
        """Accept a reusable session for offline tests."""
        self.session = session if session is not None else requests.Session()

    def request(self, method: str, url: str, **arguments: object) -> dict:
        """Send a bounded request and decode nonempty JSON responses."""
        response = self.session.request(method, url, timeout=C_HTTP_TIMEOUT, **arguments)
        response.raise_for_status()
        return response.json() if response.content else {}


class JiraClient(BaseHttpClient):
    """Read ready Jira tickets without updating Jira labels or comments."""

    def __init__(
        self, configuration: AgentConfiguration, session: requests.Session | None = None,
    ) -> None:
        """Configure Jira authentication on a dedicated session."""
        super().__init__(session)
        self.configuration = configuration
        self.session.auth = (configuration.jira_email, configuration.jira_token)

    def find_ready_issues(self, implemented_tickets: list[str] | None = None) -> list[dict]:
        """Fetch one batch, excluding completed keys before applying the result limit."""
        project = json.dumps(self.configuration.jira_project, ensure_ascii=False)
        status = json.dumps(self.configuration.jira_status, ensure_ascii=False)
        query = C_JQL_TEMPLATE.format(project=project, status=status)
        if implemented_tickets:
            # Exclude history before maxResults so completed tickets do not starve later work.
            exclusion = C_JQL_EXCLUSION.format(keys=C_JQL_KEY_SEPARATOR.join(
                json.dumps(issue_key) for issue_key in implemented_tickets
            ))
            query = query.replace(C_JQL_ORDER, exclusion + C_JQL_ORDER)
        response = self.request(
            C_METHOD_GET, self.configuration.jira_url + C_API_PATH + C_SEARCH_PATH,
            params={
                C_KEY_QUERY: query, C_KEY_FIELDS: C_SEARCH_FIELDS, C_KEY_MAX_RESULTS: C_SEARCH_LIMIT,
            },
        )
        return response.get(C_KEY_ISSUES, [])


class CommandRunner:
    """Execute argument lists directly with bounded timeouts and diagnostics."""

    def run(
        self, arguments: list[str], directory: str | None = None,
        timeout: int = C_COMMAND_TIMEOUT, environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run without a shell and reject unsuccessful processes."""
        result = subprocess.run(
            arguments, cwd=directory, capture_output=True, text=True, timeout=timeout,
            env=environment, encoding=C_ENCODING, errors=C_ENCODING_ERRORS,
        )
        if result.returncode != C_ZERO:
            raise RuntimeError(C_ERROR_COMMAND.format(
                return_code=result.returncode, output=result.stderr or result.stdout,
            ))
        return result


class TicketCsvReport:
    """Persist completed ticket keys and the single worker's current ticket."""

    def __init__(self, file_path: str) -> None:
        """Restore completed history while discarding a previous run's active state."""
        self.file_path = Path(file_path).resolve()
        self.implemented_tickets: list[str] = []
        self.current_ticket = C_EMPTY_TEXT
        if self.file_path.exists():
            with self.file_path.open(C_FILE_READ_MODE, encoding=C_ENCODING, newline=C_EMPTY_TEXT) as report_file:
                reader = csv.DictReader(report_file)
                if reader.fieldnames != list(C_CSV_COLUMNS):
                    raise ValueError(C_ERROR_CSV_COLUMNS)
                for row in reader:
                    issue_key = row.get(C_CSV_IMPLEMENTED_TICKET, C_EMPTY_TEXT)
                    if issue_key and issue_key not in self.implemented_tickets:
                        self.implemented_tickets.append(issue_key)

    def record_started(self, issue_key: str) -> None:
        """Publish the ticket before starting implementation."""
        self.current_ticket = issue_key
        self.write()

    def record_finished(self, issue_key: str, implemented: bool) -> None:
        """Clear active work and retain successful tickets without duplicates."""
        self.current_ticket = C_EMPTY_TEXT
        if implemented and issue_key not in self.implemented_tickets:
            self.implemented_tickets.append(issue_key)
        self.write()

    def write(self) -> None:
        """Atomically replace the CSV so readers never see partial reports."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            # Windows requires closing the temporary file before replacement.
            with tempfile.NamedTemporaryFile(
                mode=C_FILE_WRITE_MODE, encoding=C_ENCODING, newline=C_EMPTY_TEXT,
                dir=self.file_path.parent, suffix=C_CSV_TEMP_SUFFIX, delete=False,
            ) as report_file:
                temporary_path = Path(report_file.name)
                writer = csv.DictWriter(report_file, fieldnames=C_CSV_COLUMNS)
                writer.writeheader()
                for issue_key in self.implemented_tickets:
                    writer.writerow({C_CSV_IMPLEMENTED_TICKET: issue_key})
                if self.current_ticket:
                    writer.writerow({C_CSV_CURRENT_TICKET: self.current_ticket})
            os.replace(temporary_path, self.file_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class RepositoryRunLock:
    """Hold an OS lock for the batch, released even if the process crashes."""

    def __init__(self, repository_directory: str) -> None:
        """Create a one-byte lock file once, without overwriting an active lock."""
        lock_path = Path(repository_directory) / C_LOCK_FILE_NAME
        try:
            with lock_path.open(C_LOCK_CREATE_MODE) as new_lock_file:
                new_lock_file.write(C_LOCK_BYTE)
        except FileExistsError:
            pass
        self.lock_file = lock_path.open(C_LOCK_FILE_MODE)

    def __enter__(self) -> RepositoryRunLock:
        """Acquire a nonblocking lock before reading or clearing the CSV."""
        try:
            if os.name == C_WINDOWS_PLATFORM:
                import msvcrt

                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, C_ONE)
            else:
                import fcntl

                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exception:
            self.lock_file.close()
            if exception.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise BlockingIOError from exception
            raise
        return self

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        """Release the OS lock by closing its file descriptor."""
        self.lock_file.close()


class JiraAgentWorker:
    """Implement a finite batch in the configured local repository."""

    def __init__(
        self, configuration: AgentConfiguration, jira_client: JiraClient,
        command_runner: CommandRunner, ticket_report: TicketCsvReport | None = None,
    ) -> None:
        """Accept collaborators explicitly for offline workflow tests."""
        self.configuration = configuration
        self.jira_client = jira_client
        self.command_runner = command_runner
        self.ticket_report = (
            ticket_report if ticket_report is not None
            else TicketCsvReport(configuration.ticket_csv_path)
        )

    def build_agent_arguments(self, prompt: str, windows: bool | None = None) -> list[str]:
        """Parse the command before inserting arbitrary ticket text as one argument."""
        if windows is None:
            windows = os.name == C_WINDOWS_PLATFORM
        arguments = shlex.split(self.configuration.agent_command, posix=not windows)
        if windows:
            arguments = [
                argument[C_ONE:-C_ONE]
                if len(argument) >= C_MIN_QUOTED_LENGTH
                and argument[C_ZERO] in C_QUOTE_CHARACTERS
                and argument[C_LAST_CHARACTER] == argument[C_ZERO]
                else argument for argument in arguments
            ]
        return [argument.replace(C_PROMPT_PLACEHOLDER, prompt) for argument in arguments]

    def build_process_environment(self) -> dict[str, str]:
        """Exclude Jira credentials and inherited Git authentication from the coding CLI."""
        environment = dict(os.environ)
        for setting in tuple(environment):
            if setting in {C_ENV_JIRA_TOKEN, C_ENV_JIRA_EMAIL, C_ENV_GITHUB_TOKEN, C_GIT_CONFIG_COUNT}:
                environment.pop(setting, None)
            elif setting.startswith((C_GIT_CONFIG_KEY_PREFIX, C_GIT_CONFIG_VALUE_PREFIX)):
                environment.pop(setting, None)
        return environment

    def workspace_fingerprint(self) -> bytes:
        """Detect new edits, including untracked files and preexisting dirty work."""
        directory = self.configuration.repository_directory
        changes = self.command_runner.run(
            [C_GIT_EXECUTABLE, *C_GIT_DIFF_ARGUMENTS, C_CURRENT_DIRECTORY], directory=directory,
        )
        untracked = self.command_runner.run([C_GIT_EXECUTABLE, *C_GIT_UNTRACKED_ARGUMENTS], directory=directory)
        fingerprint = hashlib.sha256(changes.stdout.encode(C_ENCODING))
        excluded_paths = {self.ticket_report.file_path, (Path(directory) / C_LOCK_FILE_NAME).resolve()}
        for relative_path in sorted(untracked.stdout.split(C_NULL_SEPARATOR)):
            if relative_path:
                file_path = Path(directory) / relative_path
                if file_path.resolve() not in excluded_paths and file_path.is_file():
                    fingerprint.update(relative_path.encode(C_ENCODING))
                    fingerprint.update(file_path.read_bytes())
        return fingerprint.digest()

    def implement_issue(self, issue: JiraIssue) -> None:
        """Require successful CLI execution, new edits, and a validated completion marker."""
        before_implementation = self.workspace_fingerprint()
        result = self.command_runner.run(
            self.build_agent_arguments(issue.build_prompt()), directory=self.configuration.repository_directory,
            timeout=self.configuration.agent_timeout, environment=self.build_process_environment(),
        )
        success_marker = C_SUCCESS_MARKER_TEMPLATE.format(issue_key=issue.issue_key)
        output_lines = result.stdout.rstrip().splitlines()
        if not output_lines or output_lines[C_LAST_CHARACTER] != success_marker:
            raise RuntimeError(C_ERROR_INCOMPLETE)
        if self.workspace_fingerprint() == before_implementation:
            raise RuntimeError(C_ERROR_NO_CHANGES)

    def process_issue(self, issue: JiraIssue) -> bool:
        """Track current work and write successful implementation to the CSV."""
        if issue.issue_key in self.ticket_report.implemented_tickets:
            self.log(C_LOG_SKIPPED.format(issue_key=issue.issue_key))
            return True
        self.log(C_LOG_STARTED.format(issue_key=issue.issue_key))
        try:
            self.ticket_report.record_started(issue.issue_key)
            self.implement_issue(issue)
        except Exception as exception:
            self.finish_ticket_report(issue.issue_key, implemented=False)
            self.log(C_LOG_FAILURE.format(
                issue_key=issue.issue_key, error=self.configuration.redact(str(exception))[:C_ERROR_LIMIT],
            ))
            return False
        recorded = self.finish_ticket_report(issue.issue_key, implemented=True)
        self.log(C_LOG_IMPLEMENTED.format(issue_key=issue.issue_key))
        return recorded

    def finish_ticket_report(self, issue_key: str, implemented: bool) -> bool:
        """Log CSV failures and expose them as a failed scheduled invocation."""
        try:
            self.ticket_report.record_finished(issue_key, implemented)
        except Exception as exception:
            self.log(C_LOG_REPORT_FAILURE.format(issue_key=issue_key, error=exception))
            return False
        return True

    def log(self, message: str) -> None:
        """Print credential-redacted operational messages immediately."""
        print(self.configuration.redact(message), flush=True)

    def run_once(self) -> int:
        """Fetch one batch, process sequentially, and return a scheduler-friendly code."""
        self.ticket_report.write()
        self.log(C_LOG_BATCH)
        failures = C_ZERO
        try:
            responses = self.jira_client.find_ready_issues(self.ticket_report.implemented_tickets)
            for response in responses:
                try:
                    if not self.process_issue(JiraIssue.from_response(response)):
                        failures += C_ONE
                except Exception as exception:
                    failures += C_ONE
                    self.log(C_LOG_BATCH_FAILURE.format(error=exception))
        except Exception as exception:
            self.log(C_LOG_BATCH_FAILURE.format(error=exception))
            return C_ONE
        return C_ONE if failures else C_ZERO


class JiraAgentScheduler:
    """Run recurring batches without overlapping implementations or a polling loop."""

    def __init__(
        self, configuration: AgentConfiguration, scheduler: BlockingScheduler | None = None,
    ) -> None:
        """Accept a scheduler that can be replaced in offline lifecycle tests."""
        self.configuration = configuration
        self.scheduler = (
            scheduler if scheduler is not None
            else BlockingScheduler(timezone=C_SCHEDULER_TIMEZONE)
        )

    def run_batch(self) -> int:
        """Reload CSV history under the repository lock for each scheduled batch."""
        try:
            with RepositoryRunLock(self.configuration.repository_directory):
                # Recreate the report after acquiring the lock so another run's
                # completed history is retained and its active row is never cleared.
                worker = JiraAgentWorker(
                    self.configuration, JiraClient(self.configuration), CommandRunner(),
                )
                result = worker.run_once()
                if result != C_ZERO:
                    print(C_LOG_SCHEDULED_FAILURE, flush=True)
                return result
        except BlockingIOError:
            print(C_LOG_LOCKED, flush=True)
            return C_ZERO
        except Exception as exception:
            print(self.configuration.redact(C_LOG_BATCH_FAILURE.format(error=exception)), flush=True)
            return C_ONE

    def start(self) -> None:
        """Start immediately, repeat at the configured interval, and stop gracefully."""
        self.scheduler.add_job(
            self.run_batch, trigger=C_SCHEDULER_TRIGGER,
            seconds=self.configuration.poll_interval, id=C_SCHEDULER_JOB_ID,
            next_run_time=datetime.now(timezone.utc), replace_existing=True,
            max_instances=C_ONE, coalesce=True,
            misfire_grace_time=self.configuration.poll_interval,
        )
        print(self.configuration.redact(C_LOG_SCHEDULER_STARTED.format(
            status=self.configuration.jira_status, seconds=self.configuration.poll_interval,
        )), flush=True)
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            # Let an active implementation finish its CSV update before exiting.
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            print(C_LOG_SCHEDULER_STOPPED, flush=True)


def main() -> int:
    """Load configuration and keep APScheduler running until interrupted."""
    configuration = AgentConfiguration.from_environment(os.environ)
    JiraAgentScheduler(configuration).start()
    return C_ZERO


if __name__ == C_MAIN_MODULE:
    sys.exit(main())
