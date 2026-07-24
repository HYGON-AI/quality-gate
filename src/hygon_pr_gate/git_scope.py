# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Read-only Git inventory for one pull-request range."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


COMMIT_RE = re.compile(r"[0-9a-f]{40}")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class PRGitError(RuntimeError):
    pass


def git(repo: Path, *args: str, allowed: Tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode not in allowed:
        raise PRGitError(
            "git {} failed ({}): {}".format(
                args[0] if args else "command",
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace").strip(),
            )
        )
    return completed


def resolve_commit(repo: Path, value: str, label: str) -> str:
    if not COMMIT_RE.fullmatch(value.lower()):
        raise PRGitError("{} must be a full 40-character commit SHA".format(label))
    resolved = git(repo, "rev-parse", "--verify", "{}^{{commit}}".format(value)).stdout
    commit = resolved.decode("ascii").strip().lower()
    if commit != value.lower():
        raise PRGitError("{} resolved to an unexpected commit".format(label))
    return commit


def _decode_path(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def changed_files(repo: Path, start: str, head: str) -> List[Dict[str, Any]]:
    raw = git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames=100%",
        "--find-copies=100%",
        start,
        head,
        "--",
    ).stdout
    fields = raw.split(b"\0")
    changes: List[Dict[str, Any]] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        kind = status[:1]
        if kind in {"R", "C"}:
            if index + 1 >= len(fields):
                raise PRGitError("truncated rename/copy diff record")
            old_path = _decode_path(fields[index])
            path = _decode_path(fields[index + 1])
            index += 2
        else:
            if index >= len(fields):
                raise PRGitError("truncated diff record")
            old_path = None
            path = _decode_path(fields[index])
            index += 1
        changes.append(
            {
                "kind": kind,
                "status": status,
                "path": path,
                "old_path": old_path,
            }
        )
    return changes


def changed_lines(repo: Path, start: str, head: str, paths: Iterable[str]) -> Dict[str, Set[int]]:
    result: Dict[str, Set[int]] = {}
    for path in paths:
        output = git(
            repo,
            "diff",
            "--unified=0",
            "--no-ext-diff",
            start,
            head,
            "--",
            path,
        ).stdout.decode("utf-8", errors="replace")
        lines: Set[int] = set()
        for raw in output.splitlines():
            match = HUNK_RE.match(raw)
            if not match:
                continue
            first = int(match.group(1))
            count = int(match.group(2) or "1")
            if count:
                lines.update(range(first, first + count))
        result[path] = lines
    return result


def commit_metadata(repo: Path, start: str, head: str) -> List[Dict[str, str]]:
    separator = "\x1f"
    terminator = "\x1e"
    format_string = separator.join(["%H", "%an", "%ae", "%cn", "%ce", "%s", "%b"]) + terminator
    raw = git(
        repo,
        "log",
        "--reverse",
        "{}..{}".format(start, head),
        "--format={}".format(format_string),
    ).stdout.decode("utf-8", errors="replace")
    commits = []
    keys = (
        "commit",
        "author_name",
        "author_email",
        "committer_name",
        "committer_email",
        "subject",
        "body",
    )
    for record in raw.split(terminator):
        record = record.strip("\n")
        if not record:
            continue
        values = record.split(separator, 6)
        if len(values) == len(keys):
            commits.append(dict(zip(keys, values)))
    return commits


def mode(repo: Path, commit: str, path: str) -> Optional[str]:
    output = git(repo, "ls-tree", "-z", commit, "--", path).stdout
    if not output:
        return None
    metadata = output.split(b"\t", 1)[0].decode("ascii", errors="replace")
    return metadata.split()[0] if metadata else None


def blob_size(repo: Path, commit: str, path: str) -> Optional[int]:
    completed = git(repo, "cat-file", "-s", "{}:{}".format(commit, path), allowed=(0, 128))
    if completed.returncode:
        return None
    return int(completed.stdout.decode("ascii").strip())


def read_blob(repo: Path, commit: str, path: str, max_bytes: Optional[int] = None) -> Optional[bytes]:
    size = blob_size(repo, commit, path)
    if size is None or (max_bytes is not None and size > max_bytes):
        return None
    return git(repo, "show", "{}:{}".format(commit, path)).stdout


def collect_scope(repo: Path, base: str, head: str) -> Dict[str, Any]:
    if not (repo / ".git").exists():
        raise PRGitError("target path is not a non-bare Git working tree")
    base_commit = resolve_commit(repo, base, "base")
    head_commit = resolve_commit(repo, head, "head")
    merge_base = git(repo, "merge-base", base_commit, head_commit).stdout.decode("ascii").strip()
    if not COMMIT_RE.fullmatch(merge_base):
        raise PRGitError("unable to resolve pull-request merge base")
    changes = changed_files(repo, merge_base, head_commit)
    target_paths = [item["path"] for item in changes if item["kind"] != "D"]
    return {
        "base": base_commit,
        "head": head_commit,
        "merge_base": merge_base,
        "changes": changes,
        "changed_lines": changed_lines(repo, merge_base, head_commit, target_paths),
        "commits": commit_metadata(repo, base_commit, head_commit),
    }
