#!/usr/bin/env python3
"""Trusted CI orchestration. Never execute code from the audited revision."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONTEXT = "privacy-audit"
REQUEST_PATH = ".github/workflows/privacy-audit-request.yml"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MAX_PAGES = 10
SAFE_CODES = {
    "invalid_revision", "invalid_number", "github_configuration", "github_request",
    "github_response_limit", "github_unavailable", "github_response_shape",
    "github_pagination_limit", "invalid_status", "unsupported_pull_request",
    "untrusted_workflow_ref", "untrusted_actor", "unsupported_event",
    "changed_source_run", "unsupported_source_run", "invalid_branch",
    "source_run_incomplete", "git_unavailable", "pull_request_changed",
    "shallow_history", "base_changed", "policy_changed", "branch_changed", "event_limit",
    "github_redirect_blocked", "audit_error", "git_read_failed",
    "unsupported_binary", "unsupported_encoding", "incomplete_history",
    "invalid_metadata", "metadata_limit", "commit_limit", "total_limit",
    "invalid_git_data", "path_limit", "unsupported_file_mode",
    "unsupported_format", "blob_limit", "blob_size_limit", "unfetched_lfs_object",
    "INVALID_RESPONSE", "COVERAGE_MISMATCH", "INCONSISTENT_VERDICT",
    "CONTENT_REVIEW_REQUIRED", "MODEL_INCOMPLETE", "MODEL_REFUSAL_OR_INVALID",
    "API_REDIRECT_BLOCKED", "RESPONSE_TOO_LARGE", "API_RATE_LIMIT", "API_AUTH",
    "API_ERROR", "API_UNAVAILABLE", "INVALID_ITEMS", "MISSING_POLICY",
    "INPUT_TOO_LARGE", "SECRET_PATTERN", "MISSING_API_KEY",
}
SAFE_REASONS = {
    "credential", "identity", "contact", "sensitive_personal", "internal_business",
    "reidentification", "unreviewed", "instruction_attack",
}


class CIError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def sha(value):
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise CIError("invalid_revision")
    return value


def positive_number(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,9}", str(value)):
        raise CIError("invalid_number")
    return int(value)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CIError("github_redirect_blocked")


class GitHub:
    def __init__(self, repository, token, run_id):
        if not REPO_PATTERN.fullmatch(repository) or not token:
            raise CIError("github_configuration")
        self.repository = repository
        self.owner = repository.split("/", 1)[0]
        self.token = token
        self.run_id = positive_number(run_id)

    def request(self, path, data=None):
        if not path.startswith("/") or ".." in path or "#" in path:
            raise CIError("github_request")
        url = f"https://api.github.com/repos/{self.repository}{path}"
        request = urllib.request.Request(
            url,
            data=None if data is None else json.dumps(data).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise CIError("github_response_limit")
                return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            # Never echo HTTP bodies, URLs, credentials or repository contents.
            raise CIError("github_unavailable") from None

    def pages(self, path):
        result = []
        separator = "&" if "?" in path else "?"
        for page in range(1, MAX_PAGES + 1):
            items = self.request(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(items, list):
                raise CIError("github_response_shape")
            result.extend(items)
            if len(items) < 100:
                return result
        raise CIError("github_pagination_limit")

    def status(self, head, state):
        descriptions = {
            "pending": "Privacy audit has not completed.",
            "success": "All items in the audited scope passed.",
            "failure": "Privacy audit blocked; see redacted workflow result.",
        }
        if state not in descriptions:
            raise CIError("invalid_status")
        self.request(f"/statuses/{sha(head)}", {
            "state": state, "context": CONTEXT,
            "description": descriptions[state],
            "target_url": f"https://github.com/{self.repository}/actions/runs/{self.run_id}",
        })


def pull_snapshot(pr, repository):
    """Only data relevant to this audit; no authors or GitHub user metadata."""
    try:
        number = positive_number(pr["number"])
        head = sha(pr["head"]["sha"])
        base = sha(pr["base"]["sha"])
        branch = pr["head"]["ref"]
        title = pr["title"]
        body = pr["body"] or ""
        if (pr["state"] != "open" or pr["base"]["ref"] != "main"
                or pr["base"]["repo"]["full_name"] != repository):
            raise CIError("unsupported_pull_request")
        if not all(isinstance(x, str) for x in (branch, title, body)):
            raise CIError("github_response_shape")
        return {"number": number, "head": head, "base": base,
                "branch": branch, "title": title, "body": body}
    except (KeyError, TypeError):
        raise CIError("github_response_shape") from None


def associated_pulls(api, head):
    snapshots = []
    for pr in api.pages(f"/commits/{sha(head)}/pulls"):
        try:
            if pr["state"] != "open" or pr["head"]["sha"] != head:
                continue
            # A PR targeting another branch cannot receive a passing audit.
            snapshots.append(pull_snapshot(pr, api.repository))
        except (KeyError, TypeError):
            raise CIError("github_response_shape") from None
    return sorted(snapshots, key=lambda item: item["number"])


def target(api, event_name, event, env):
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise CIError("untrusted_workflow_ref")
    if event_name == "workflow_dispatch":
        if env.get("GITHUB_ACTOR", "").lower() != api.owner.lower():
            raise CIError("untrusted_actor")
        number = positive_number(event.get("inputs", {}).get("pull_request_number"))
        snapshot = pull_snapshot(api.request(f"/pulls/{number}"), api.repository)
        return snapshot["head"], snapshot["branch"], False
    if event_name != "workflow_run":
        raise CIError("unsupported_event")
    try:
        supplied = event["workflow_run"]
        run = api.request(f"/actions/runs/{positive_number(supplied['id'])}")
        head = sha(run["head_sha"])
        if head != sha(supplied["head_sha"]):
            raise CIError("changed_source_run")
        if (run["name"] != "Privacy audit request"
                or run["path"] != REQUEST_PATH
                or run["event"] not in {"push", "pull_request"}
                or run["repository"]["full_name"] != api.repository):
            raise CIError("unsupported_source_run")
        branch = run["head_branch"]
        if not isinstance(branch, str) or not branch:
            raise CIError("invalid_branch")
        # Set a blocking state before checking who can incur model usage.
        api.status(head, "pending")
        if run["actor"]["login"].lower() != api.owner.lower():
            raise CIError("untrusted_actor")
        requested = event.get("action") == "requested"
        if not requested and (event.get("action") != "completed"
                              or run["status"] != "completed"):
            raise CIError("source_run_incomplete")
        return head, branch, requested
    except (KeyError, TypeError, AttributeError):
        raise CIError("github_response_shape") from None


def git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=120, check=True)
        return result.stdout.decode("ascii").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise CIError("git_unavailable") from None


def run(api, event_name, event, env, repo, collect_fn, audit_fn):
    head = None
    try:
        head, branch, requested = target(api, event_name, event, env)
        api.status(head, "pending")
        if requested:
            return "pending"
        base = sha(api.request("/branches/main")["commit"]["sha"])
        # A queued run may have checked out an older trusted default-branch SHA.
        # Do not audit a new base with stale code or policy; rerun from current main.
        if sha(git(repo, "rev-parse", "HEAD")) != base:
            raise CIError("policy_changed")
        pulls = associated_pulls(api, head)
        if event_name == "workflow_dispatch" and not pulls:
            raise CIError("pull_request_changed")
        # No credential helpers, PR checkout, submodules, hooks, or git filters.
        remote = f"https://github.com/{api.repository}.git"
        git(repo, "-c", "credential.helper=", "fetch", "--no-tags", remote, base, head)
        if git(repo, "rev-parse", "--is-shallow-repository") != "false":
            raise CIError("shallow_history")
        metadata = {"branch": branch, "pull_requests": pulls}
        items = collect_fn(repo, base, head, metadata)
        trusted = repo / ".agents/skills/audit-log-privacy/SKILL.md"
        policy = trusted.read_text(encoding="utf-8")
        # The trusted top-level policy is included, not any PR-supplied AGENTS.
        policy += "\n\n" + (repo / "AGENTS.md").read_text(encoding="utf-8")
        audit_fn(items, policy)
        # Do not overwrite a newer revision or edited PR's result with old success.
        if sha(api.request("/branches/main")["commit"]["sha"]) != base:
            raise CIError("base_changed")
        if associated_pulls(api, head) != pulls:
            raise CIError("pull_request_changed")
        if not pulls:
            encoded = urllib.parse.quote(branch, safe="")
            current = api.request(f"/branches/{encoded}")
            if sha(current["commit"]["sha"]) != head:
                raise CIError("branch_changed")
        api.status(head, "success")
        return "success"
    except Exception:
        if head is not None:
            try:
                api.status(head, "failure")
            except Exception:
                pass  # The earlier pending status remains blocking.
        raise


def report_error(error):
    """Publish only known codes and validated neutral locations, never free text."""
    code = getattr(error, "code", "audit_error")
    if not isinstance(code, str) or code not in SAFE_CODES:
        code = "audit_error"
    print("Privacy audit: BLOCKED (" + code + ")")
    findings = getattr(error, "findings", [])
    if not isinstance(findings, list) or len(findings) > 300:
        return
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"id", "sha", "reason", "lines"}:
            continue
        item_id, blob, reason, lines = (finding["id"], finding["sha"],
                                        finding["reason"], finding["lines"])
        if (not isinstance(item_id, str) or not re.fullmatch(r"item-\d{4}", item_id)
                or (blob is not None and (not isinstance(blob, str) or not SHA_PATTERN.fullmatch(blob)))
                or not isinstance(reason, str) or reason not in SAFE_REASONS
                or not isinstance(lines, list) or len(lines) > 20
                or any(type(line) is not int or not 1 <= line <= 1_000_000 for line in lines)):
            continue
        print(json.dumps({"id": item_id, "sha": blob, "reason": reason, "lines": lines}))


def main():
    try:
        # Imports are delayed so standalone target selection can be unit tested.
        from privacy_collect import collect
        from privacy_audit import audit_items
        env = os.environ
        api = GitHub(env.get("GITHUB_REPOSITORY", ""), env.get("GITHUB_TOKEN", ""),
                     env.get("GITHUB_RUN_ID", ""))
        event_path = Path(env["GITHUB_EVENT_PATH"])
        if event_path.stat().st_size > 2_000_000:
            raise CIError("event_limit")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        result = run(api, env.get("GITHUB_EVENT_NAME"), event, env,
                     Path(__file__).resolve().parents[1], collect, audit_items)
        print("Privacy audit: " + result.upper())
        return 0
    except Exception as error:
        report_error(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
