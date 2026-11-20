"""Collector tests use a disposable Git repository and synthetic data only."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "privacy_collect", Path(__file__).resolve().parents[1] / "scripts/privacy_collect.py"
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test Author")
        self.git("config", "user.email", "author@example.invalid")
        self.git("commit", "--allow-empty", "-qm", "initial")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL).decode()

    def commit(self, message="change"):
        self.git("add", "--all")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def collect(self):
        return collector.collect(self.repo, self.base, self.git("rev-parse", "HEAD").strip(), {"branch": "test"})

    def assertBlocked(self, code):
        with self.assertRaises(collector.PrivacyCollectionError) as error:
            self.collect()
        self.assertEqual(error.exception.code, code)
        self.assertEqual(str(error.exception), code)

    def test_every_version_including_added_then_deleted(self):
        file = self.repo / ".hidden"
        file.write_text("synthetic first version\n", encoding="utf-8")
        self.commit("synthetic message one")
        file.write_text("synthetic second version\n", encoding="utf-8")
        self.commit("synthetic message two")
        file.unlink()
        self.commit("synthetic message three")
        items = self.collect()
        files = [json.loads(item["text"]) for item in items if item["kind"] == "file"]
        self.assertEqual({item["content"] for item in files}, {
            "synthetic first version\n", "synthetic second version\n"
        })
        content = "\n".join(item["text"] for item in items)
        self.assertIn('"status": "D"', content)
        self.assertIn("synthetic message one", content)
        self.assertIn("synthetic message three", content)
        self.assertNotIn("author@example.invalid", content)
        self.assertEqual([item["id"] for item in items], [f"item-{n:04d}" for n in range(1, len(items) + 1)])

    def test_rename_audits_new_path_and_unchanged_content(self):
        (self.repo / "old.txt").write_text("unchanged", encoding="utf-8")
        self.base = self.commit()
        (self.repo / "old.txt").rename(self.repo / "new.txt")
        self.commit()
        items = self.collect()
        self.assertEqual(sum(item["kind"] == "file" for item in items), 1)
        texts = "\n".join(item["text"] for item in items)
        self.assertIn("old.txt", texts)
        self.assertIn("new.txt", texts)

    def test_hostile_path_is_data_not_shell(self):
        name = "$(touch DID_NOT_RUN)\n--option.txt"
        (self.repo / name).write_text("ordinary text", encoding="utf-8")
        self.commit()
        items = self.collect()
        file = next(json.loads(item["text"]) for item in items if item["kind"] == "file")
        self.assertEqual(file["path"], name)
        self.assertFalse((self.repo / "DID_NOT_RUN").exists())

    def test_same_blob_multiple_paths_preserves_all_paths(self):
        (self.repo / "one.txt").write_text("same text", encoding="utf-8")
        (self.repo / "two.txt").write_text("same text", encoding="utf-8")
        self.commit()
        items = self.collect()
        self.assertEqual(sum(item["kind"] == "file" for item in items), 1)
        metadata = "\n".join(item["text"] for item in items if item["kind"] == "metadata")
        self.assertIn("one.txt", metadata)
        self.assertIn("two.txt", metadata)

    def test_binary_blocked(self):
        (self.repo / "file.bin").write_bytes(b"content\0not text")
        self.commit()
        self.assertBlocked("unsupported_binary")

    def test_invalid_encoding_blocked(self):
        (self.repo / "file.txt").write_bytes(b"\xff\xfe")
        self.commit()
        self.assertBlocked("unsupported_encoding")

    def test_pdf_even_when_ascii_or_renamed_is_blocked(self):
        (self.repo / "file.txt").write_bytes(b"%PDF-1.7\nsynthetic container")
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_svg_is_not_mistaken_for_visually_audited_text(self):
        (self.repo / "drawing.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_renamed_svg_with_long_xml_preamble_is_blocked(self):
        (self.repo / "drawing.txt").write_text(
            '<?xml version="1.0"?>\n<!--' + "x" * 2100 + '-->\n<svg/>'
        )
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_renamed_postscript_is_blocked(self):
        (self.repo / "drawing.txt").write_text("%!PS-Adobe-3.0\nshowpage\n")
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_renamed_namespaced_svg_is_blocked(self):
        (self.repo / "drawing.txt").write_text(
            '<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:text>synthetic</s:text></s:svg>'
        )
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_svg_literal_in_source_is_still_text(self):
        (self.repo / "example.py").write_text('example = "<svg/>"\n')
        self.commit()
        self.assertEqual(sum(item["kind"] == "file" for item in self.collect()), 1)

    def test_symlink_is_not_followed(self):
        (self.repo / "link").symlink_to("/etc/passwd")
        self.commit()
        self.assertBlocked("unsupported_file_mode")

    def test_gitlink_is_not_treated_as_blob(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",submodule")
        self.git("commit", "-qm", "synthetic gitlink")
        self.assertBlocked("unsupported_file_mode")

    def test_lfs_pointer_is_not_treated_as_contents(self):
        (self.repo / "large.txt").write_text("version https://git-lfs.github.com/spec/v1\noid sha256:synthetic\nsize 10\n")
        self.commit()
        self.assertBlocked("unfetched_lfs_object")

    def test_size_limit_does_not_return_partial_success(self):
        (self.repo / "large.txt").write_text("x" * (collector.MAX_BLOB_BYTES + 1))
        self.commit()
        self.assertBlocked("blob_size_limit")

    def test_commit_limit(self):
        (self.repo / "file.txt").write_text("value")
        self.commit()
        with patch.object(collector, "MAX_COMMITS", 0):
            self.assertBlocked("commit_limit")

    def test_blob_limit(self):
        (self.repo / "file.txt").write_text("value")
        self.commit()
        with patch.object(collector, "MAX_BLOBS", 0):
            self.assertBlocked("blob_limit")

    def test_path_limit(self):
        (self.repo / "file.txt").write_text("value")
        self.commit()
        with patch.object(collector, "MAX_PATHS", 0):
            self.assertBlocked("path_limit")

    def test_metadata_limit(self):
        with patch.object(collector, "MAX_METADATA_BYTES", 2):
            self.assertBlocked("metadata_limit")

    def test_shallow_history_is_never_reported_complete(self):
        (self.repo / ".git" / "shallow").write_text(self.base + "\n")
        self.assertBlocked("incomplete_history")

    def test_proposed_executable_file_is_only_read(self):
        (self.repo / "run.sh").write_text("#!/bin/sh\ntouch DID_NOT_RUN\n")
        (self.repo / "run.sh").chmod(0o755)
        self.commit()
        self.assertEqual(sum(item["kind"] == "file" for item in self.collect()), 1)
        self.assertFalse((self.repo / "DID_NOT_RUN").exists())

    def test_deleted_existing_binary_only_changes_path(self):
        file = self.repo / "old.pdf"
        file.write_bytes(b"%PDF-1.7\n\0synthetic")
        self.base = self.commit()
        file.unlink()
        self.commit()
        items = self.collect()
        self.assertFalse(any(item["kind"] == "file" for item in items))
        self.assertIn("old.pdf", "\n".join(item["text"] for item in items))

    def test_total_limit(self):
        (self.repo / "file.txt").write_text("value")
        self.commit()
        with patch.object(collector, "MAX_TOTAL_BYTES", 5):
            self.assertBlocked("total_limit")

    def test_metadata_only_when_base_equals_head(self):
        items = collector.collect(self.repo, self.base, self.base, {"title": "synthetic title"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "metadata")
        self.assertIn("synthetic title", items[0]["text"])

    def test_invalid_revision_fails_without_echoing_input(self):
        with self.assertRaises(collector.PrivacyCollectionError) as error:
            collector.collect(self.repo, "bad-sensitive-value", self.base, {})
        self.assertEqual(str(error.exception), "invalid_revision")

    def test_merge_parent_changes_remain_in_scope(self):
        self.git("checkout", "-qb", "side")
        (self.repo / "side.txt").write_text("side contents")
        self.commit("side message")
        self.git("checkout", "-qb", "target", self.base)
        (self.repo / "target.txt").write_text("target contents")
        self.commit("target message")
        self.git("merge", "--no-ff", "-qm", "merge branches", "side")
        items = self.collect()
        files = [json.loads(item["text"])["content"] for item in items if item["kind"] == "file"]
        self.assertEqual(set(files), {"side contents", "target contents"})

    def test_merging_current_base_does_not_reaudit_unchanged_svg(self):
        original_base = self.base
        self.git("checkout", "-qb", "base-line")
        (self.repo / "approved.svg").write_text("<svg/>")
        self.base = self.commit("base adds previously approved diagram")
        self.git("checkout", "-qb", "topic", original_base)
        (self.repo / "note.txt").write_text("topic changes only this text")
        self.commit("topic note")
        self.git("merge", "--no-ff", "-qm", "update topic from base", "base-line")
        items = self.collect()
        files = [json.loads(item["text"]) for item in items if item["kind"] == "file"]
        self.assertEqual([item["path"] for item in files], ["note.txt"])
        metadata = "\n".join(item["text"] for item in items if item["kind"] == "metadata")
        self.assertIn("approved.svg", metadata)

    def test_existing_svg_at_new_path_is_not_exempt(self):
        file = self.repo / "approved.svg"
        file.write_text("<svg/>")
        self.base = self.commit()
        (self.repo / "new.svg").write_bytes(file.read_bytes())
        self.commit()
        self.assertBlocked("unsupported_format")

    def test_modified_then_restored_base_content_still_audits_intermediate(self):
        file = self.repo / "note.txt"
        file.write_text("base contents")
        self.base = self.commit()
        file.write_text("synthetic intermediate information")
        self.commit()
        file.write_text("base contents")
        self.commit()
        items = self.collect()
        files = [json.loads(item["text"])["content"] for item in items if item["kind"] == "file"]
        self.assertEqual(files, ["synthetic intermediate information"])

    def test_base_svg_with_changed_mode_is_not_exempt(self):
        file = self.repo / "approved.svg"
        file.write_text("<svg/>")
        self.base = self.commit()
        file.chmod(0o755)
        self.commit()
        self.assertBlocked("unsupported_format")


if __name__ == "__main__":
    unittest.main()
