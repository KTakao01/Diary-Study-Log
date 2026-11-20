import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import privacy_audit as audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.items = [{"id": "item-0001", "kind": "file", "sha": "a" * 40,
                       "text": "A generic technical example.\nSecond line."}]
        self.result = {"verdict": "pass", "results": [
            {"id": "item-0001", "verdict": "pass", "reason": "none", "lines": []}]}

    def response(self, result=None):
        return {"status": "completed", "output": [{"type": "message", "role": "assistant",
                "status": "completed", "content": [{"type": "output_text",
                "text": json.dumps(result or self.result)}]}]}

    def error(self, expected, function, *args):
        with self.assertRaises(audit.PrivacyAuditError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, expected)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"})
    def test_success_requires_actual_model_and_trusted_policy(self):
        with patch.object(audit, "request_model", return_value=self.response()) as request:
            audit.audit_items(self.items, "trusted audit instructions")
        payload, _ = request.call_args.args
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"], [])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertIn("trusted audit instructions", payload["instructions"])
        self.assertNotIn(self.items[0]["text"], payload["instructions"])
        self.assertIn(self.items[0]["text"].splitlines()[0], payload["input"][0]["content"])

    @patch.dict(os.environ, {}, clear=True)
    def test_no_key_fails_without_network(self):
        with patch.object(audit, "request_model") as request:
            self.error("MISSING_API_KEY", audit.audit_items, self.items, "policy")
            request.assert_not_called()

    def test_no_empty_audit_or_duplicate_ids(self):
        self.error("INVALID_ITEMS", audit.audit_items, [], "policy")
        self.error("INVALID_ITEMS", audit.audit_items, self.items * 2, "policy")

    def test_limit_does_not_silently_truncate(self):
        self.items[0]["text"] = "あ" * audit.MAX_INPUT_BYTES
        self.error("INPUT_TOO_LARGE", audit.audit_items, self.items, "policy")

    def test_credential_tripwire_never_sends_secret(self):
        self.items[0]["text"] = "gh" + "p_" + "Z" * 36
        with patch.object(audit, "request_model") as request:
            self.error("SECRET_PATTERN", audit.audit_items, self.items, "policy")
            request.assert_not_called()

    def test_reject_missing_extra_and_duplicate_results(self):
        for rows in ([], self.result["results"] * 2):
            value = {"verdict": "pass", "results": rows}
            self.error("COVERAGE_MISMATCH", audit.validate_result, value, self.items)
        value = copy.deepcopy(self.result)
        value["results"][0]["id"] = "item-9999"
        self.error("COVERAGE_MISMATCH", audit.validate_result, value, self.items)

    def test_fail_and_uncertainty_block_merge(self):
        for verdict in ("fail", "needs_review"):
            value = copy.deepcopy(self.result)
            value["verdict"] = verdict
            value["results"][0].update(verdict=verdict, reason="contact", lines=[2])
            self.error("CONTENT_REVIEW_REQUIRED", audit.validate_result, value, self.items)

    def test_overall_pass_cannot_override_failed_item(self):
        value = copy.deepcopy(self.result)
        value["results"][0].update(verdict="fail", reason="credential")
        self.error("INCONSISTENT_VERDICT", audit.validate_result, value, self.items)

    def test_cannot_smuggle_free_text_or_workflow_commands(self):
        value = copy.deepcopy(self.result)
        value["results"][0]["reason"] = "::warning::private data"
        self.error("INVALID_RESPONSE", audit.validate_result, value, self.items)
        value = copy.deepcopy(self.result)
        value["explanation"] = "private data"
        self.error("INVALID_RESPONSE", audit.validate_result, value, self.items)
        for line in (True, 0, 3, "::error::"):
            value = copy.deepcopy(self.result)
            value["results"][0]["lines"] = [line]
            self.error("INVALID_RESPONSE", audit.validate_result, value, self.items)

    def test_incomplete_error_refusal_and_tool_call(self):
        for state in ("incomplete", "failed", "queued"):
            self.error("MODEL_INCOMPLETE", audit.parse_response,
                       {"status": state}, self.items)
        value = self.response()
        value["error"] = {"message": "private data"}
        self.error("MODEL_INCOMPLETE", audit.parse_response, value, self.items)
        value = self.response()
        value["output"][0]["content"] = [{"type": "refusal", "refusal": "private data"}]
        self.error("MODEL_REFUSAL_OR_INVALID", audit.parse_response, value, self.items)
        value = self.response()
        value["output"].append({"type": "function_call"})
        self.error("INVALID_RESPONSE", audit.parse_response, value, self.items)

    def test_duplicate_json_keys_and_multiple_messages_rejected(self):
        self.error("INVALID_RESPONSE", audit.strict_json, '{"verdict":"fail","verdict":"pass"}')
        value = self.response()
        value["output"] *= 2
        self.error("INVALID_RESPONSE", audit.parse_response, value, self.items)

    def test_http_errors_do_not_expose_server_body(self):
        for status, expected in ((401, "API_AUTH"), (429, "API_RATE_LIMIT"), (500, "API_ERROR")):
            error = urllib.error.HTTPError(audit.ENDPOINT, status, "private data", {}, io.BytesIO(b"private data"))
            with patch("urllib.request.OpenerDirector.open", side_effect=error):
                self.error(expected, audit.request_model, {}, "test-only")

    def test_redirect_cannot_send_key_elsewhere(self):
        self.error("API_REDIRECT_BLOCKED", audit.NoRedirect().redirect_request,
                   None, None, 302, "", {}, "https://example.invalid")

    def test_valid_reasoning_plus_message(self):
        value = self.response()
        value["output"].insert(0, {"type": "reasoning", "summary": []})
        audit.parse_response(value, self.items)


if __name__ == "__main__":
    unittest.main()
