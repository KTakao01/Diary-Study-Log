import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import privacy_ci as ci

BASE = "a" * 40
HEAD = "b" * 40
NEW = "c" * 40
REPOSITORY = "example/diary"
ENV = {"GITHUB_REF": "refs/heads/main", "GITHUB_ACTOR": "example"}


def pr(head=HEAD, title="Reading notes", base=BASE, target="main"):
    return {"number": 12, "state": "open", "title": title, "body": "A summary.",
            "head": {"sha": head, "ref": "topic"},
            "base": {"sha": base, "ref": target,
                     "repo": {"full_name": REPOSITORY}}}


def event(action="completed"):
    return {"action": action, "workflow_run": {"id": 5, "head_sha": HEAD}}


class FakeAPI:
    repository = REPOSITORY
    owner = "example"

    def __init__(self):
        self.statuses = []
        self.pulls = [pr()]
        self.base = BASE
        self.branch_head = HEAD
        self.source = {"name": "Privacy audit request", "path": ci.REQUEST_PATH,
                       "event": "push", "repository": {"full_name": REPOSITORY},
                       "head_sha": HEAD, "head_branch": "topic",
                       "actor": {"login": "example"}, "status": "completed"}

    def request(self, path, data=None):
        if path == "/actions/runs/5":
            return self.source
        if path == "/branches/main":
            return {"commit": {"sha": self.base}}
        if path == "/branches/topic":
            return {"commit": {"sha": self.branch_head}}
        if path == "/pulls/12":
            return self.pulls[0]
        raise AssertionError("Unexpected endpoint")

    def pages(self, path):
        if path == f"/commits/{HEAD}/pulls":
            return self.pulls
        raise AssertionError("Unexpected endpoint")

    def status(self, head, state):
        self.statuses.append((head, state))


class PrivacyCITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        directory = self.repo / ".agents/skills/audit-log-privacy"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("Trusted audit rules")
        (self.repo / "AGENTS.md").write_text("Trusted project rules")
        self.api = FakeAPI()
        self.seen = []
        self.collected = []

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, repo, base, head, metadata):
        self.collected.append((base, head, metadata))
        return [{"id": "item-0001", "kind": "metadata", "sha": None,
                 "text": "Safe learning content"}]

    def audit(self, items, policy):
        self.seen.append((items, policy))

    def run_audit(self, audit=None, ev=None, name="workflow_run", env=None):
        def fake_git(repo, *args):
            return BASE if args == ("rev-parse", "HEAD") else "false"
        with patch.object(ci, "git", side_effect=fake_git):
            return ci.run(self.api, name, ev or event(), env or ENV, self.repo,
                          self.collect, audit or self.audit)

    def test_success_covers_metadata_and_trusted_policy(self):
        self.assertEqual(self.run_audit(), "success")
        self.assertEqual(self.api.statuses[-1], (HEAD, "success"))
        self.assertIn("Trusted project rules", self.seen[0][1])
        self.assertEqual(self.collected[0][2]["pull_requests"][0]["title"], "Reading notes")

    def test_requested_marks_pending_without_model_usage(self):
        self.assertEqual(self.run_audit(ev=event("requested")), "pending")
        self.assertEqual(self.api.statuses[-1], (HEAD, "pending"))
        self.assertEqual(self.seen, [])

    def test_changed_title_during_audit_does_not_pass(self):
        def edit(items, policy):
            self.api.pulls = [pr(title="Edited during audit")]
        with self.assertRaisesRegex(ci.CIError, "pull_request_changed"):
            self.run_audit(audit=edit)
        self.assertEqual(self.api.statuses[-1], (HEAD, "failure"))

    def test_changed_head_during_audit_does_not_pass(self):
        def push(items, policy):
            self.api.pulls = [pr(head=NEW)]
        with self.assertRaisesRegex(ci.CIError, "pull_request_changed"):
            self.run_audit(audit=push)
        self.assertNotIn((HEAD, "success"), self.api.statuses)

    def test_base_update_during_audit_does_not_pass(self):
        def merge(items, policy):
            self.api.base = NEW
        with self.assertRaisesRegex(ci.CIError, "base_changed"):
            self.run_audit(audit=merge)

    def test_retargeting_during_audit_does_not_pass(self):
        def retarget(items, policy):
            self.api.pulls = [pr(target="other")]
        with self.assertRaisesRegex(ci.CIError, "unsupported_pull_request"):
            self.run_audit(audit=retarget)
        self.assertEqual(self.api.statuses[-1], (HEAD, "failure"))

    def test_api_or_auditor_failure_never_success(self):
        def error(items, policy):
            raise TimeoutError("Do not print this sensitive string")
        with self.assertRaises(TimeoutError):
            self.run_audit(audit=error)
        self.assertEqual(self.api.statuses[-1], (HEAD, "failure"))
        self.assertNotIn((HEAD, "success"), self.api.statuses)

    def test_push_without_pr_is_audited(self):
        self.api.pulls = []
        self.assertEqual(self.run_audit(), "success")
        self.assertEqual(self.collected[0][2]["pull_requests"], [])

    def test_push_advanced_without_pr_does_not_pass(self):
        self.api.pulls = []
        def pushed(items, policy):
            self.api.branch_head = NEW
        with self.assertRaisesRegex(ci.CIError, "branch_changed"):
            self.run_audit(audit=pushed)

    def test_another_actor_cannot_spend_model_credits(self):
        self.api.source["actor"]["login"] = "external"
        with self.assertRaisesRegex(ci.CIError, "untrusted_actor"):
            self.run_audit()
        self.assertEqual(self.api.statuses[-1], (HEAD, "pending"))
        self.assertEqual(self.seen, [])

    def test_untrusted_dispatch_branch_is_rejected(self):
        with self.assertRaisesRegex(ci.CIError, "untrusted_workflow_ref"):
            self.run_audit(env={**ENV, "GITHUB_REF": "refs/heads/topic"})

    def test_wrong_named_workflow_is_rejected(self):
        self.api.source["path"] = ".github/workflows/other.yml"
        with self.assertRaisesRegex(ci.CIError, "unsupported_source_run"):
            self.run_audit()
        self.assertEqual(self.seen, [])

    def test_wrong_source_event_is_rejected(self):
        self.api.source["event"] = "workflow_dispatch"
        with self.assertRaisesRegex(ci.CIError, "unsupported_source_run"):
            self.run_audit()

    def test_invalid_revision_is_rejected_before_git(self):
        self.api.source["head_sha"] = "--upload-pack=malicious"
        with self.assertRaisesRegex(ci.CIError, "invalid_revision"):
            self.run_audit()
        self.assertEqual(self.collected, [])

    def test_dispatch_can_recheck_exact_pr_head(self):
        self.assertEqual(self.run_audit(name="workflow_dispatch",
                                       ev={"inputs": {"pull_request_number": "12"}}),
                         "success")

    def test_paginated_results_not_silently_truncated(self):
        api = ci.GitHub(REPOSITORY, "placeholder", 123)
        with patch.object(api, "request", return_value=[{}] * 100):
            with self.assertRaisesRegex(ci.CIError, "github_pagination_limit"):
                api.pages("/pulls")

    def test_bad_shapes_fail_closed(self):
        for malformed in ({}, {"number": 12}, {"number": False}):
            with self.subTest(malformed=malformed), self.assertRaises(ci.CIError):
                ci.pull_snapshot(malformed, REPOSITORY)

    def test_status_uses_exact_head_and_fixed_description(self):
        api = ci.GitHub(REPOSITORY, "placeholder", 123)
        with patch.object(api, "request") as request:
            api.status(HEAD, "success")
            path, data = request.call_args.args
            self.assertEqual(path, f"/statuses/{HEAD}")
            self.assertEqual(data["context"], "privacy-audit")
            self.assertNotIn("Reading notes", data["description"])

    def test_error_report_preserves_known_uppercase_codes(self):
        error = ci.CIError("MISSING_API_KEY")
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            ci.report_error(error)
        self.assertIn("MISSING_API_KEY", stream.getvalue())

    def test_error_report_never_echoes_arbitrary_text(self):
        error = ci.CIError("privateperson")
        error.findings = [{"id": "privateperson", "sha": HEAD,
                           "reason": "contact", "lines": [1]}]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            ci.report_error(error)
        self.assertNotIn("privateperson", stream.getvalue())
        self.assertIn("audit_error", stream.getvalue())

    def test_error_report_uses_only_neutral_validated_fields(self):
        error = ci.CIError("CONTENT_REVIEW_REQUIRED")
        error.findings = [{"id": "item-0001", "sha": HEAD,
                           "reason": "contact", "lines": [1, 2]},
                          {"id": "item-0002", "sha": HEAD,
                           "reason": "contact", "lines": [True]}]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            ci.report_error(error)
        self.assertIn("item-0001", stream.getvalue())
        self.assertNotIn("item-0002", stream.getvalue())

    def test_redirects_are_rejected(self):
        with self.assertRaisesRegex(ci.CIError, "github_redirect_blocked"):
            ci.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid")

    def test_stale_trusted_policy_does_not_audit_new_base(self):
        self.api.base = NEW
        with self.assertRaisesRegex(ci.CIError, "policy_changed"):
            self.run_audit()
        self.assertEqual(self.collected, [])
        self.assertEqual(self.seen, [])
        self.assertEqual(self.api.statuses[-1], (HEAD, "failure"))

    def test_shallow_history_fails_without_auditing(self):
        def fake_git(repo, *args):
            return BASE if args == ("rev-parse", "HEAD") else "true"
        with patch.object(ci, "git", side_effect=fake_git):
            with self.assertRaisesRegex(ci.CIError, "shallow_history"):
                ci.run(self.api, "workflow_run", event(), ENV, self.repo,
                       self.collect, self.audit)
        self.assertEqual(self.seen, [])
        self.assertEqual(self.api.statuses[-1], (HEAD, "failure"))


if __name__ == "__main__":
    unittest.main()
