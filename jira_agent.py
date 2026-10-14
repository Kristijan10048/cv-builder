#!/usr/bin/env python3
"""Poll Jira Cloud and publish coding-agent changes as GitHub pull requests.

Run one worker per project: Jira label updates are not an atomic lock.
Configuration is read when main() starts, so importing this module is safe.
Requires requests, Git, and the CLI configured through AGENT_CMD.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import quote

import requests

C_EMPTY_TEXT = ""
C_SLASH = "/"
C_HYPHEN = "-"
C_ZERO = 0
C_FIRST_CHARACTER = 0
C_LAST_CHARACTER = -1
C_QUOTE_LENGTH = 1
C_MIN_QUOTED_LENGTH = 2
C_QUOTE_CHARACTERS = "\"'"
C_WINDOWS_PLATFORM = "nt"
C_ENCODING = "utf-8"
C_ENCODING_ERRORS = "replace"
C_MAIN_MODULE = "__main__"
C_HTTP_TIMEOUT = 30
C_COMMAND_TIMEOUT = 300
C_DEFAULT_AGENT_TIMEOUT = 1800
C_DEFAULT_POLL_INTERVAL = 60
C_SEARCH_LIMIT = 5
C_SLUG_LIMIT = 40
C_OUTPUT_LIMIT = 1500
C_ERROR_LIMIT = 1800
C_ENV_JIRA_URL = "JIRA_URL"
C_ENV_JIRA_EMAIL = "JIRA_EMAIL"
C_ENV_JIRA_TOKEN = "JIRA_API_TOKEN"
C_ENV_JIRA_PROJECT = "JIRA_PROJECT"
C_ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
C_ENV_GITHUB_REPOSITORY = "GITHUB_REPO"
C_ENV_BASE_BRANCH = "BASE_BRANCH"
C_ENV_AGENT_COMMAND = "AGENT_CMD"
C_ENV_AGENT_TIMEOUT = "AGENT_TIMEOUT"
C_ENV_POLL_INTERVAL = "POLL_INTERVAL"
C_DEFAULT_BASE_BRANCH = "main"
C_PROMPT_PLACEHOLDER = "{prompt}"
C_DEFAULT_AGENT_COMMAND = "claude -p {prompt} --permission-mode acceptEdits --max-turns 30"
C_SLUG_PATTERN = r"[^a-z0-9]+"
C_REPOSITORY_PATTERN = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
C_ISSUE_KEY_PATTERN = r"[A-Za-z][A-Za-z0-9_]*-[0-9]+"
C_API_PATH = "/rest/api/2"
C_SEARCH_PATH = "/search/jql"
C_ISSUE_PATH = "/issue/{issue_key}"
C_COMMENT_PATH = "/issue/{issue_key}/comment"
C_BROWSE_URL = "{jira_url}/browse/{issue_key}"
C_REPOSITORY_URL = "https://github.com/{repository}.git"
C_PULL_REQUEST_URL = "https://api.github.com/repos/{repository}/pulls"
C_METHOD_GET = "GET"
C_METHOD_PUT = "PUT"
C_METHOD_POST = "POST"
C_KEY_ISSUES = "issues"
C_KEY_ISSUE_KEY = "key"
C_KEY_FIELDS = "fields"
C_KEY_SUMMARY = "summary"
C_KEY_DESCRIPTION = "description"
C_KEY_LABELS = "labels"
C_KEY_QUERY = "jql"
C_KEY_MAX_RESULTS = "maxResults"
C_KEY_UPDATE = "update"
C_KEY_REMOVE = "remove"
C_KEY_ADD = "add"
C_KEY_BODY = "body"
C_KEY_TITLE = "title"
C_KEY_HEAD = "head"
C_KEY_BASE = "base"
C_KEY_HTML_URL = "html_url"
C_HEADER_AUTHORIZATION = "Authorization"
C_HEADER_ACCEPT = "Accept"
C_GITHUB_ACCEPT = "application/vnd.github+json"
C_BEARER_TOKEN = "Bearer {token}"
C_LABEL_READY = "agent-ready"
C_LABEL_IN_PROGRESS = "agent-in-progress"
C_LABEL_REVIEW = "agent-review"
C_LABEL_FAILED = "agent-failed"
C_SEARCH_FIELDS = "summary,description"
C_LABEL_FIELDS = "labels"
C_JQL_TEMPLATE = (
    'project = {project} AND labels = "agent-ready" '
    'AND labels NOT IN ("agent-in-progress", "agent-review", "agent-failed") '
    "ORDER BY created ASC"
)
C_PROMPT_TEMPLATE = (
    "You are working on Jira ticket {issue_key}.\n\n"
    "Title: {summary}\n\nDescription:\n{description}\n\n"
    "Implement the change, add or update tests, and run the test suite. "
    "Do not touch CI config, secrets, or unrelated files. "
    "Follow the conventions in CLAUDE.md / AGENTS.md if present. "
    "Do not commit; leave changes in the working tree."
)
C_MISSING_DESCRIPTION = "(none)"
C_BRANCH_TEMPLATE = "{issue_key}-{slug}"
C_TITLE_TEMPLATE = "{issue_key}: {summary}"
C_PULL_REQUEST_BODY = (
    "Automated change for {ticket_url}.\n\n"
    "Agent output (tail):\n```\n{output}\n```"
)
C_REVIEW_COMMENT = "Agent opened a PR for review: {pull_request_url}"
C_FAILURE_COMMENT = (
    "Agent could not complete this ticket:\n{{noformat}}\n{error}\n{{noformat}}"
)
C_LOG_STARTED = "[{issue_key}] started"
C_LOG_PULL_REQUEST = "[{issue_key}] PR: {pull_request_url}"
C_LOG_FAILURE = "[{issue_key}] failed: {error}"
C_LOG_REPORT_FAILURE = "[{issue_key}] {operation} failed: {error}"
C_LOG_POLL_FAILURE = "Polling failed: {error}"
C_LOG_POLLING = "Polling Jira for agent-ready tickets..."
C_OPERATION_LABEL = "label update"
C_OPERATION_COMMENT = "comment"
C_ERROR_REQUIRED_SETTING = "Missing required environment setting: {setting}"
C_ERROR_POSITIVE_SETTING = "{setting} must be a positive integer."
C_ERROR_REPOSITORY = "GITHUB_REPO must use owner/repository format."
C_ERROR_PROMPT = "AGENT_CMD must contain a {prompt} placeholder."
C_ERROR_ISSUE_KEY = "Invalid Jira issue key."
C_ERROR_COMMAND = "Command failed with exit code {return_code}:\n{output}"
C_ERROR_NO_CHANGES = "Agent made no changes."
C_REDACTED = "[REDACTED]"
C_GIT_EXECUTABLE = "git"
C_GIT_CLONE_ARGUMENTS = ("clone", "--depth", "50", "--branch")
C_GIT_BRANCH_ARGUMENTS = ("checkout", "-b")
C_GIT_STATUS_ARGUMENTS = ("status", "--porcelain")
C_GIT_ADD_ARGUMENTS = ("add", "-A")
C_GIT_COMMIT_ARGUMENTS = (
    "-c", "user.name=agent-bot",
    "-c", "user.email=agent-bot@users.noreply.github.com", "commit", "-m",
)
C_GIT_PUSH_ARGUMENTS = ("push", "origin")
C_GIT_CONFIG_COUNT = "GIT_CONFIG_COUNT"
C_GIT_CONFIG_KEY_PREFIX = "GIT_CONFIG_KEY_"
C_GIT_CONFIG_VALUE_PREFIX = "GIT_CONFIG_VALUE_"
C_GIT_AUTH_CONFIG_KEY = "GIT_CONFIG_KEY_0"
C_GIT_AUTH_CONFIG_VALUE = "GIT_CONFIG_VALUE_0"
C_GIT_HELPER_CONFIG_KEY = "GIT_CONFIG_KEY_1"
C_GIT_HELPER_CONFIG_VALUE = "GIT_CONFIG_VALUE_1"
C_GIT_CONFIG_ENTRY_COUNT = "2"
C_GIT_AUTH_HEADER_KEY = "http.https://github.com/.extraheader"
C_GIT_AUTH_HEADER_VALUE = "AUTHORIZATION: basic {authorization}"
C_GIT_HELPER_KEY = "credential.helper"
C_GIT_TERMINAL_PROMPT = "GIT_TERMINAL_PROMPT"
C_GIT_DISABLE_PROMPT = "0"
C_GIT_CREDENTIAL_TEMPLATE = "x-access-token:{token}"


@dataclass(frozen=True)
class AgentConfiguration:
    """Keep validated configuration without exposing credentials in repr."""

    jira_url: str
    jira_email: str
    jira_token: str = field(repr=False)
    jira_project: str
    github_token: str = field(repr=False)
    github_repository: str
    base_branch: str = C_DEFAULT_BASE_BRANCH
    agent_command: str = C_DEFAULT_AGENT_COMMAND
    agent_timeout: int = C_DEFAULT_AGENT_TIMEOUT
    poll_interval: int = C_DEFAULT_POLL_INTERVAL

    @classmethod
    def from_environment(class_type, environment: Mapping[str, str]) -> AgentConfiguration:
        """Load required settings and validate configuration before polling."""
        required_settings = (
            C_ENV_JIRA_URL, C_ENV_JIRA_EMAIL, C_ENV_JIRA_TOKEN,
            C_ENV_JIRA_PROJECT, C_ENV_GITHUB_TOKEN, C_ENV_GITHUB_REPOSITORY,
        )
        for setting in required_settings:
            if not environment.get(setting, C_EMPTY_TEXT).strip():
                raise ValueError(C_ERROR_REQUIRED_SETTING.format(setting=setting))
        repository = environment[C_ENV_GITHUB_REPOSITORY].strip()
        if not re.fullmatch(C_REPOSITORY_PATTERN, repository):
            raise ValueError(C_ERROR_REPOSITORY)
        agent_command = environment.get(C_ENV_AGENT_COMMAND, C_DEFAULT_AGENT_COMMAND)
        if C_PROMPT_PLACEHOLDER not in agent_command:
            raise ValueError(C_ERROR_PROMPT)
        return class_type(
            jira_url=environment[C_ENV_JIRA_URL].rstrip(C_SLASH),
            jira_email=environment[C_ENV_JIRA_EMAIL],
            jira_token=environment[C_ENV_JIRA_TOKEN],
            jira_project=environment[C_ENV_JIRA_PROJECT],
            github_token=environment[C_ENV_GITHUB_TOKEN],
            github_repository=repository,
            base_branch=environment.get(C_ENV_BASE_BRANCH, C_DEFAULT_BASE_BRANCH),
            agent_command=agent_command,
            agent_timeout=class_type.read_positive_integer(
                environment, C_ENV_AGENT_TIMEOUT, C_DEFAULT_AGENT_TIMEOUT,
            ),
            poll_interval=class_type.read_positive_integer(
                environment, C_ENV_POLL_INTERVAL, C_DEFAULT_POLL_INTERVAL,
            ),
        )

    @staticmethod
    def read_positive_integer(
        environment: Mapping[str, str], setting: str, default_value: int,
    ) -> int:
        """Reject invalid or nonpositive durations with an actionable message."""
        try:
            duration = int(environment.get(setting, str(default_value)))
        except ValueError as exception:
            raise ValueError(C_ERROR_POSITIVE_SETTING.format(setting=setting)) from exception
        if duration <= C_ZERO:
            raise ValueError(C_ERROR_POSITIVE_SETTING.format(setting=setting))
        return duration

    def redact(self, text: str) -> str:
        """Remove raw and encoded credentials from logs and published output."""
        credentials = C_GIT_CREDENTIAL_TEMPLATE.format(token=self.github_token)
        encoded_credentials = base64.b64encode(credentials.encode(C_ENCODING)).decode(C_ENCODING)
        for secret in (
            encoded_credentials, quote(self.github_token, safe=C_EMPTY_TEXT),
            self.github_token, self.jira_token,
        ):
            if secret:
                text = text.replace(secret, C_REDACTED)
        return text


@dataclass(frozen=True)
class JiraIssue:
    """Represent Jira fields required for one coding task."""

    issue_key: str
    summary: str
    description: str | None

    @classmethod
    def from_response(class_type, response: dict) -> JiraIssue:
        """Extract ticket fields and validate the key used in Git commands."""
        issue_key = response[C_KEY_ISSUE_KEY]
        if not re.fullmatch(C_ISSUE_KEY_PATTERN, issue_key):
            raise ValueError(C_ERROR_ISSUE_KEY)
        issue_fields = response[C_KEY_FIELDS]
        return class_type(issue_key, issue_fields[C_KEY_SUMMARY], issue_fields.get(C_KEY_DESCRIPTION))

    def build_prompt(self) -> str:
        """Combine ticket text with instructions for the coding CLI."""
        return C_PROMPT_TEMPLATE.format(
            issue_key=self.issue_key, summary=self.summary,
            description=self.description or C_MISSING_DESCRIPTION,
        )

    def build_branch_name(self) -> str:
        """Create a Git-safe branch with no invalid trailing separator."""
        slug = re.sub(C_SLUG_PATTERN, C_HYPHEN, self.summary.lower())
        slug = slug.strip(C_HYPHEN)[:C_SLUG_LIMIT].rstrip(C_HYPHEN)
        if not slug:
            return self.issue_key
        return C_BRANCH_TEMPLATE.format(issue_key=self.issue_key, slug=slug)


class BaseHttpClient:
    """Share bounded requests, status checking, and empty-body handling."""

    def __init__(self, session: requests.Session | None = None) -> None:
        """Accept a reusable HTTP session that can be replaced in tests."""
        self.session = session if session is not None else requests.Session()

    def request(self, method: str, url: str, **arguments: object) -> dict:
        """Send a request and parse JSON only when a response body exists."""
        response = self.session.request(method, url, timeout=C_HTTP_TIMEOUT, **arguments)
        response.raise_for_status()
        return response.json() if response.content else {}


class JiraClient(BaseHttpClient):
    """Find Jira Cloud work and maintain ticket labels and comments."""

    def __init__(
        self, configuration: AgentConfiguration, session: requests.Session | None = None,
    ) -> None:
        """Configure basic authentication on a dedicated Jira session."""
        super().__init__(session)
        self.configuration = configuration
        self.session.auth = (configuration.jira_email, configuration.jira_token)

    def find_ready_issues(self) -> list[dict]:
        """Fetch a bounded batch that excludes other worker states."""
        # JSON quoting also escapes the backslashes and quotes required by JQL.
        project = json.dumps(self.configuration.jira_project, ensure_ascii=False)
        response = self.request(
            C_METHOD_GET, self.configuration.jira_url + C_API_PATH + C_SEARCH_PATH,
            params={
                C_KEY_QUERY: C_JQL_TEMPLATE.format(project=project),
                C_KEY_FIELDS: C_SEARCH_FIELDS, C_KEY_MAX_RESULTS: C_SEARCH_LIMIT,
            },
        )
        return response.get(C_KEY_ISSUES, [])

    def claim_issue(self, issue_key: str) -> bool:
        """Recheck live labels because enhanced search may return stale issues."""
        response = self.request(
            C_METHOD_GET,
            self.configuration.jira_url + C_API_PATH + C_ISSUE_PATH.format(issue_key=issue_key),
            params={C_KEY_FIELDS: C_LABEL_FIELDS},
        )
        labels = response[C_KEY_FIELDS].get(C_KEY_LABELS, [])
        active_labels = {C_LABEL_IN_PROGRESS, C_LABEL_REVIEW, C_LABEL_FAILED}
        if C_LABEL_READY not in labels or active_labels.intersection(labels):
            return False
        # This protects a single worker from stale search results, not concurrent claims.
        self.swap_label(issue_key, C_LABEL_READY, C_LABEL_IN_PROGRESS)
        return True

    def swap_label(self, issue_key: str, removed_label: str, added_label: str) -> None:
        """Replace a worker label while retaining unrelated labels."""
        self.request(
            C_METHOD_PUT,
            self.configuration.jira_url + C_API_PATH + C_ISSUE_PATH.format(issue_key=issue_key),
            json={C_KEY_UPDATE: {C_KEY_LABELS: [
                {C_KEY_REMOVE: removed_label}, {C_KEY_ADD: added_label},
            ]}},
        )

    def add_comment(self, issue_key: str, text: str) -> None:
        """Append a plain-text comment using the Jira v2 representation."""
        self.request(
            C_METHOD_POST,
            self.configuration.jira_url + C_API_PATH + C_COMMENT_PATH.format(issue_key=issue_key),
            json={C_KEY_BODY: text},
        )


class GitHubClient(BaseHttpClient):
    """Create GitHub pull requests using a dedicated authenticated session."""

    def __init__(
        self, configuration: AgentConfiguration, session: requests.Session | None = None,
    ) -> None:
        """Configure the GitHub REST authentication headers."""
        super().__init__(session)
        self.configuration = configuration
        self.session.headers.update({
            C_HEADER_AUTHORIZATION: C_BEARER_TOKEN.format(token=configuration.github_token),
            C_HEADER_ACCEPT: C_GITHUB_ACCEPT,
        })

    def open_pull_request(self, branch: str, title: str, body: str) -> str:
        """Publish a PR against the configured base branch and return its URL."""
        response = self.request(
            C_METHOD_POST,
            C_PULL_REQUEST_URL.format(repository=self.configuration.github_repository),
            json={
                C_KEY_TITLE: title, C_KEY_HEAD: branch,
                C_KEY_BASE: self.configuration.base_branch, C_KEY_BODY: body,
            },
        )
        return response[C_KEY_HTML_URL]


class CommandRunner:
    """Execute argument lists directly with bounded timeouts and useful diagnostics."""

    def run(
        self, arguments: list[str], directory: str | None = None,
        timeout: int = C_COMMAND_TIMEOUT, environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run without a shell and raise a useful error for unsuccessful commands."""
        result = subprocess.run(
            arguments, cwd=directory, capture_output=True, text=True, timeout=timeout,
            env=environment, encoding=C_ENCODING, errors=C_ENCODING_ERRORS,
        )
        if result.returncode != C_ZERO:
            output = result.stderr or result.stdout
            raise RuntimeError(C_ERROR_COMMAND.format(
                return_code=result.returncode, output=output,
            ))
        return result


class JiraAgentWorker:
    """Coordinate ticket claims, isolated coding work, and independent reporting."""

    def __init__(
        self, configuration: AgentConfiguration, jira_client: JiraClient,
        github_client: GitHubClient, command_runner: CommandRunner,
    ) -> None:
        """Accept collaborators explicitly for offline workflow tests."""
        self.configuration = configuration
        self.jira_client = jira_client
        self.github_client = github_client
        self.command_runner = command_runner

    def build_agent_arguments(self, prompt: str, windows: bool | None = None) -> list[str]:
        """Parse the template before inserting arbitrary ticket text as an argument."""
        if windows is None:
            windows = os.name == C_WINDOWS_PLATFORM
        arguments = shlex.split(self.configuration.agent_command, posix=not windows)
        if windows:
            # Non-POSIX parsing preserves Windows path backslashes and surrounding quotes.
            arguments = [
                argument[C_QUOTE_LENGTH:-C_QUOTE_LENGTH]
                if len(argument) >= C_MIN_QUOTED_LENGTH
                and argument[C_FIRST_CHARACTER] in C_QUOTE_CHARACTERS
                and argument[C_LAST_CHARACTER] == argument[C_FIRST_CHARACTER]
                else argument
                for argument in arguments
            ]
        return [argument.replace(C_PROMPT_PLACEHOLDER, prompt) for argument in arguments]

    def build_process_environment(self, authenticate_git: bool = False) -> dict[str, str]:
        """Keep credentials out of clone URLs and the coding process environment."""
        environment = dict(os.environ)
        for setting in tuple(environment):
            if setting in {C_ENV_GITHUB_TOKEN, C_ENV_JIRA_TOKEN, C_GIT_CONFIG_COUNT}:
                environment.pop(setting, None)
            elif setting.startswith((C_GIT_CONFIG_KEY_PREFIX, C_GIT_CONFIG_VALUE_PREFIX)):
                environment.pop(setting, None)
        if authenticate_git:
            credentials = C_GIT_CREDENTIAL_TEMPLATE.format(token=self.configuration.github_token)
            authorization = base64.b64encode(credentials.encode(C_ENCODING)).decode(C_ENCODING)
            environment.update({
                C_GIT_CONFIG_COUNT: C_GIT_CONFIG_ENTRY_COUNT,
                C_GIT_AUTH_CONFIG_KEY: C_GIT_AUTH_HEADER_KEY,
                C_GIT_AUTH_CONFIG_VALUE: C_GIT_AUTH_HEADER_VALUE.format(authorization=authorization),
                C_GIT_HELPER_CONFIG_KEY: C_GIT_HELPER_KEY,
                C_GIT_HELPER_CONFIG_VALUE: C_EMPTY_TEXT,
                C_GIT_TERMINAL_PROMPT: C_GIT_DISABLE_PROMPT,
            })
        return environment

    def create_pull_request(self, issue: JiraIssue) -> str:
        """Clone, run the coding CLI, commit its changes, push, and create a PR."""
        branch = issue.build_branch_name()
        title = C_TITLE_TEMPLATE.format(issue_key=issue.issue_key, summary=issue.summary)
        git_environment = self.build_process_environment(authenticate_git=True)
        agent_environment = self.build_process_environment()
        with tempfile.TemporaryDirectory() as repository_directory:
            repository_url = C_REPOSITORY_URL.format(repository=self.configuration.github_repository)
            self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_CLONE_ARGUMENTS, self.configuration.base_branch,
                 repository_url, repository_directory], environment=git_environment,
            )
            self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_BRANCH_ARGUMENTS, branch], directory=repository_directory,
            )
            result = self.command_runner.run(
                self.build_agent_arguments(issue.build_prompt()), directory=repository_directory,
                timeout=self.configuration.agent_timeout, environment=agent_environment,
            )
            status = self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_STATUS_ARGUMENTS], directory=repository_directory,
            )
            if not status.stdout.strip():
                raise RuntimeError(C_ERROR_NO_CHANGES)
            self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_ADD_ARGUMENTS], directory=repository_directory,
            )
            self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_COMMIT_ARGUMENTS, title], directory=repository_directory,
            )
            self.command_runner.run(
                [C_GIT_EXECUTABLE, *C_GIT_PUSH_ARGUMENTS, branch],
                directory=repository_directory, environment=git_environment,
            )
            ticket_url = C_BROWSE_URL.format(
                jira_url=self.configuration.jira_url, issue_key=issue.issue_key,
            )
            # Redact before truncation to avoid publishing a partial credential.
            output = self.configuration.redact(result.stdout)[-C_OUTPUT_LIMIT:]
            body = C_PULL_REQUEST_BODY.format(ticket_url=ticket_url, output=output)
        return self.github_client.open_pull_request(branch, title, body)

    def report_result(self, issue_key: str, label: str, comment: str) -> None:
        """Attempt label updates and comments independently when either API call fails."""
        try:
            self.jira_client.swap_label(issue_key, C_LABEL_IN_PROGRESS, label)
        except Exception as exception:
            self.log(C_LOG_REPORT_FAILURE.format(
                issue_key=issue_key, operation=C_OPERATION_LABEL, error=exception,
            ))
        try:
            self.jira_client.add_comment(issue_key, comment)
        except Exception as exception:
            self.log(C_LOG_REPORT_FAILURE.format(
                issue_key=issue_key, operation=C_OPERATION_COMMENT, error=exception,
            ))

    def process_issue(self, issue: JiraIssue) -> None:
        """Isolate ticket failures and preserve success after a PR has been created."""
        try:
            if not self.jira_client.claim_issue(issue.issue_key):
                return
        except Exception as exception:
            self.log(C_LOG_FAILURE.format(issue_key=issue.issue_key, error=exception))
            return
        self.log(C_LOG_STARTED.format(issue_key=issue.issue_key))
        try:
            pull_request_url = self.create_pull_request(issue)
        except Exception as exception:
            error = self.configuration.redact(str(exception))[:C_ERROR_LIMIT]
            self.report_result(
                issue.issue_key, C_LABEL_FAILED, C_FAILURE_COMMENT.format(error=error),
            )
            self.log(C_LOG_FAILURE.format(issue_key=issue.issue_key, error=error))
            return
        # Jira reporting failures must not change a successfully opened PR to agent-failed.
        self.log(C_LOG_PULL_REQUEST.format(issue_key=issue.issue_key, pull_request_url=pull_request_url))
        self.report_result(
            issue.issue_key, C_LABEL_REVIEW,
            C_REVIEW_COMMENT.format(pull_request_url=pull_request_url),
        )

    def log(self, message: str) -> None:
        """Print operational messages after removing configured credentials."""
        print(self.configuration.redact(message))

    def poll_forever(self) -> None:
        """Process sequentially while isolating network failures and malformed tickets."""
        self.log(C_LOG_POLLING)
        while True:
            try:
                responses = self.jira_client.find_ready_issues()
                for response in responses:
                    try:
                        self.process_issue(JiraIssue.from_response(response))
                    except Exception as exception:
                        self.log(C_LOG_POLL_FAILURE.format(error=exception))
            except Exception as exception:
                self.log(C_LOG_POLL_FAILURE.format(error=exception))
            time.sleep(self.configuration.poll_interval)


def main() -> None:
    """Load configuration and start the single-instance Jira coding worker."""
    configuration = AgentConfiguration.from_environment(os.environ)
    worker = JiraAgentWorker(
        configuration, JiraClient(configuration), GitHubClient(configuration), CommandRunner(),
    )
    worker.poll_forever()


if __name__ == C_MAIN_MODULE:
    main()
