"""Read proposed Git data without checking out or executing proposed files.

The scope is metadata supplied by the caller, commit messages in base..head,
changed paths, and every new/modified blob version in that range. Existing
versions identical to the current base at the same path and mode are not
re-audited, including files inherited by merging base into a topic branch.
Author/committer identities, signatures, other refs, and remote link targets are
outside this incremental scope. Returned text is private audit input: callers
must never print it to a public CI log.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

MAX_COMMITS = 50
MAX_BLOBS = 100
MAX_BLOB_BYTES = 50_000
MAX_METADATA_BYTES = 50_000
MAX_TOTAL_BYTES = 500_000
MAX_PATHS = 500
SHA = re.compile(r"[0-9a-f]{40}\Z")
# These formats need a dedicated visual/container audit. Failing is intentional:
# decoding a PDF or SVG as UTF-8 does not audit its rendered contents.
UNSUPPORTED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".tif", ".tiff", ".heic", ".avif", ".pdf", ".ps", ".eps",
    ".zip", ".gz", ".tar", ".7z", ".rar", ".bz2", ".xz",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
    ".mp3", ".mp4", ".mov", ".wav", ".ogg", ".woff", ".woff2",
}


class PrivacyCollectionError(Exception):
    """A fixed, non-sensitive error code; never include underlying Git output."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _git(repo: Path, *args: str) -> bytes:
    # No shell, filters, textconv, pager, hooks, credential helpers, or user Git
    # config are needed. Sanitizing the environment also prevents GIT_TRACE from
    # sending commands or data to a caller-selected public log.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/nonexistent",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    try:
        proc = subprocess.run(
            ["git", "--no-pager", "-c", "core.hooksPath=/dev/null", "-C",
             str(repo), *args],
            capture_output=True, check=False, timeout=30, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PrivacyCollectionError("git_read_failed") from None
    if proc.returncode:
        raise PrivacyCollectionError("git_read_failed")
    return proc.stdout


def _decode(data: bytes) -> str:
    if b"\0" in data:
        raise PrivacyCollectionError("unsupported_binary")
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise PrivacyCollectionError("unsupported_encoding") from None


def _is_container(data: bytes) -> bool:
    # SVG may have an arbitrarily long legal XML preamble. Scan the complete
    # bounded blob, but only a document root: a code example containing an SVG
    # string is ordinary text, not itself a rendered SVG image.
    prefix = data.lstrip().lower()
    return (
        data.startswith((b"%PDF-", b"%!PS", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a",
                         b"PK\x03\x04", b"\xff\xd8\xff", b"\x1f\x8b"))
        or re.match(br"(?:(?:<\?xml[\s\S]*?\?>|<!--[\s\S]*?-->)\s*)*<(?:[a-z_][\w.-]*:)?svg(?:\s|/?>)", prefix) is not None
        or (prefix.startswith(b"<") and b"http://www.w3.org/2000/svg" in prefix)
    )


def collect(repo: Path, base: str, head: str, metadata: dict) -> list[dict]:
    """Return complete bounded audit items or raise, never a partial success."""
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise PrivacyCollectionError("invalid_revision")
    repo = Path(repo)
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise PrivacyCollectionError("incomplete_history")
    for revision in (base, head):
        if _git(repo, "cat-file", "-t", revision).strip() != b"commit":
            raise PrivacyCollectionError("invalid_revision")
    try:
        metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        metadata_size = len(metadata_text.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError):
        raise PrivacyCollectionError("invalid_metadata") from None
    if not isinstance(metadata, dict) or metadata_size > MAX_METADATA_BYTES:
        raise PrivacyCollectionError("metadata_limit")

    commits = _git(repo, "rev-list", "--reverse", "--topo-order", head, "--not", base).splitlines()
    if len(commits) > MAX_COMMITS:
        raise PrivacyCollectionError("commit_limit")
    # Merging an updated base into a topic produces parent-relative additions
    # that are already part of the current base. Exempt only an exact
    # (path, content, mode) match. A copied/renamed file, changed mode, or any
    # intermediate content version still needs its own audit.
    base_versions: set[tuple[bytes, str, str]] = set()
    tree = _git(repo, "ls-tree", "-r", "-z", "--full-tree", base)
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        try:
            header, path = entry.split(b"\t", 1)
            mode, object_type, sha = header.decode("ascii").split()
            if not SHA.fullmatch(sha) or object_type not in {"blob", "commit"}:
                raise ValueError
        except (UnicodeError, ValueError):
            raise PrivacyCollectionError("invalid_git_data") from None
        base_versions.add((path, sha, mode))
    items: list[dict] = []
    total_bytes = 0

    def add(kind: str, text: str, sha: str | None = None) -> None:
        nonlocal total_bytes
        try:
            size = len(text.encode("utf-8"))
        except UnicodeError:
            raise PrivacyCollectionError("unsupported_encoding") from None
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise PrivacyCollectionError("total_limit")
        items.append({"id": f"item-{len(items) + 1:04d}", "kind": kind, "sha": sha, "text": text})

    add("metadata", metadata_text)
    # The same blob can appear under multiple names. Audit content once while
    # retaining every path in a separate metadata item, including deleted paths.
    blobs: dict[str, str] = {}
    changes: set[tuple[str, str, str, str]] = set()

    def read_changes(old: str | None, new: str) -> None:
        args = ["diff-tree", "--no-commit-id", "--no-abbrev", "--no-renames",
                "--no-ext-diff", "--raw", "-r", "-z"]
        args.extend([old, new] if old else ["--root", new])
        fields = _git(repo, *args).split(b"\0")
        if fields[-1] != b"":
            raise PrivacyCollectionError("invalid_git_data")
        fields.pop()
        if len(fields) % 2:
            raise PrivacyCollectionError("invalid_git_data")
        for offset in range(0, len(fields), 2):
            try:
                header = fields[offset].decode("ascii").split()
                if len(header) != 5 or not header[0].startswith(":"):
                    raise ValueError
                mode, sha, status = header[1], header[3], header[4]
                if not SHA.fullmatch(sha) or status not in {"A", "M", "D", "T"}:
                    raise ValueError
            except (UnicodeError, ValueError):
                raise PrivacyCollectionError("invalid_git_data") from None
            path = _decode(fields[offset + 1])
            changes.add((new, status, path, sha))
            if len(changes) > MAX_PATHS:
                raise PrivacyCollectionError("path_limit")
            if status == "D":
                continue
            if (fields[offset + 1], sha, mode) in base_versions:
                continue
            if mode not in {"100644", "100755"}:
                raise PrivacyCollectionError("unsupported_file_mode")
            if Path(path).suffix.lower() in UNSUPPORTED_SUFFIXES:
                raise PrivacyCollectionError("unsupported_format")
            if sha not in blobs:
                if len(blobs) >= MAX_BLOBS:
                    raise PrivacyCollectionError("blob_limit")
                blobs[sha] = path

    for raw_commit in commits:
        try:
            commit = raw_commit.decode("ascii")
        except UnicodeError:
            raise PrivacyCollectionError("invalid_git_data") from None
        if not SHA.fullmatch(commit):
            raise PrivacyCollectionError("invalid_git_data")
        data = _git(repo, "cat-file", "commit", commit)
        try:
            header, message = data.split(b"\n\n", 1)
        except ValueError:
            raise PrivacyCollectionError("invalid_git_data") from None
        if len(message) > MAX_METADATA_BYTES:
            raise PrivacyCollectionError("metadata_limit")
        add("metadata", json.dumps({"commit": commit, "message": _decode(message)}, ensure_ascii=False))
        parents = [line[7:].decode("ascii") for line in header.splitlines() if line.startswith(b"parent ")]
        if not all(SHA.fullmatch(parent) for parent in parents):
            raise PrivacyCollectionError("invalid_git_data")
        for parent in parents or [None]:
            read_changes(parent, commit)
    if base != head:
        read_changes(base, head)

    if changes:
        add("metadata", json.dumps({"changes": [
            {"commit": commit, "status": status, "path": path, "blob": sha}
            for commit, status, path, sha in sorted(changes)
        ]}, ensure_ascii=False))
    for sha, path in blobs.items():
        size = _git(repo, "cat-file", "-s", sha).strip()
        if not size.isdigit() or int(size) > MAX_BLOB_BYTES:
            raise PrivacyCollectionError("blob_size_limit")
        data = _git(repo, "cat-file", "blob", sha)
        if len(data) != int(size):
            raise PrivacyCollectionError("invalid_git_data")
        if _is_container(data):
            raise PrivacyCollectionError("unsupported_format")
        text = _decode(data)
        if text.startswith("version https://git-lfs.github.com/spec/"):
            raise PrivacyCollectionError("unfetched_lfs_object")
        add("file", json.dumps({"path": path, "content": text}, ensure_ascii=False), sha)
    return items
