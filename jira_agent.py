#!/usr/bin/env python3
"""
Minimal Jira -> coding agent -> GitHub PR worker.

Designed for a home lab behind NAT: it only makes OUTBOUND requests
(polling Jira), so no port forwarding, tunnel, or public webhook is needed.

Flow per ticket:
  1. Find Jira issues labelled `agent-ready`
  2. Swap label to `agent-in-progress`
  3. Clone repo, create branch PROJ-123-...
  4. Run the coding agent headlessly with the ticket text
  5. Commit, push, open a PR
  6. Comment on the Jira ticket with the PR link, label `agent-review`
  On failure: comment, label `agent-failed`

Requires: pip install requests
"""

import os
import re
import shlex
import subprocess
import tempfile
import time

import requests

# ---- Config (environment variables) ---------------------------------------
JIRA_URL = os.environ["JIRA_URL"].rstrip("/")      # https://yourco.atlassian.net
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT = os.environ["JIRA_PROJECT"]          # e.g. PROJ

GH_TOKEN = os.environ["GITHUB_TOKEN"]              # fine-grained PAT: contents + pull requests
GH_REPO = os.environ["GITHUB_REPO"]                # owner/name
BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")

# Check the exact flags for your agent/CLI version. This example uses Claude Code in print mode.
AGENT_CMD = os.environ.get(
    "AGENT_CMD", "claude -p {prompt} --permission-mode acceptEdits --max-turns 30"
)
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "1800"))  # seconds
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

JIRA_AUTH = (JIRA_EMAIL, JIRA_TOKEN)
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
}


# ---- Jira helpers ----------------------------------------------------------
def jira(method, path, **kwargs):
    r = requests.request(method, f"{JIRA_URL}/rest/api/2{path}", auth=JIRA_AUTH, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def find_ready_issues():
    jql = f'project = {JIRA_PROJECT} AND labels = "agent-ready" ORDER BY created ASC'
    data = jira("GET", "/search/jql", params={"jql": jql, "fields": "summary,description", "maxResults": 5})
    return data.get("issues", [])


def swap_label(key, remove, add):
    jira("PUT", f"/issue/{key}", json={"update": {"labels": [{"remove": remove}, {"add": add}]}})


def comment(key, text):
    jira("POST", f"/issue/{key}/comment", json={"body": text})


# ---- Git / GitHub helpers --------------------------------------------------
def run(cmd, cwd=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def open_pr(branch, title, body):
    r = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/pulls",
        headers=GH_HEADERS,
        json={"title": title, "head": branch, "base": BASE_BRANCH, "body": body},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["html_url"]


# ---- Main work -------------------------------------------------------------
def build_prompt(key, summary, description):
    return (
        f"You are working on Jira ticket {key}.\n\n"
        f"Title: {summary}\n\nDescription:\n{description or '(none)'}\n\n"
        "Implement the change, add or update tests, and run the test suite. "
        "Do not touch CI config, secrets, or unrelated files. "
        "Follow the conventions in CLAUDE.md / AGENTS.md if present. "
        "Do not commit; leave changes in the working tree."
    )


def process_issue(issue):
    key = issue["key"]
    summary = issue["fields"]["summary"]
    description = issue["fields"].get("description")
    branch = f"{key}-{slugify(summary)}"

    swap_label(key, "agent-ready", "agent-in-progress")
    print(f"[{key}] started")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            repo_url = f"https://x-access-token:{GH_TOKEN}@github.com/{GH_REPO}.git"
            run(["git", "clone", "--depth", "50", "--branch", BASE_BRANCH, repo_url, tmp])
            run(["git", "checkout", "-b", branch], cwd=tmp)

            prompt = build_prompt(key, summary, description)
            cmd = AGENT_CMD.format(prompt=shlex.quote(prompt))
            result = subprocess.run(
                shlex.split(cmd), cwd=tmp, capture_output=True, text=True, timeout=AGENT_TIMEOUT
            )
            if result.returncode != 0:
                raise RuntimeError(f"Agent exited with {result.returncode}:\n{result.stderr[-1500:]}")

            if not run(["git", "status", "--porcelain"], cwd=tmp).stdout.strip():
                raise RuntimeError("Agent made no changes.")

            run(["git", "add", "-A"], cwd=tmp)
            run(["git", "-c", "user.name=agent-bot", "-c", "user.email=agent-bot@users.noreply.github.com",
                 "commit", "-m", f"{key}: {summary}"], cwd=tmp)
            run(["git", "push", "origin", branch], cwd=tmp)

            pr_url = open_pr(
                branch,
                f"{key}: {summary}",
                f"Automated change for {JIRA_URL}/browse/{key}.\n\nAgent output (tail):\n```\n{result.stdout[-1500:]}\n```",
            )

        comment(key, f"Agent opened a PR for review: {pr_url}")
        swap_label(key, "agent-in-progress", "agent-review")
        print(f"[{key}] PR: {pr_url}")

    except Exception as exc:  # noqa: BLE001 - report any failure back to the ticket
        comment(key, f"Agent could not complete this ticket:\n{{noformat}}\n{str(exc)[:1800]}\n{{noformat}}")
        swap_label(key, "agent-in-progress", "agent-failed")
        print(f"[{key}] failed: {exc}")


def main():
    print("Polling Jira for agent-ready tickets...")
    while True:
        try:
            for issue in find_ready_issues():
                process_issue(issue)  # sequential on purpose: one at a time
        except requests.RequestException as exc:
            print(f"Jira/GitHub request failed: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
