# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Conservatively identify deterministic secret placeholders without exposing values."""

import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional


COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,40}")
AUTH_VALUE_RE = re.compile(
    r"authorization\s*:\s*(?:(?:bearer|basic|token)\s+)?([^\s\"'\\]+)",
    re.IGNORECASE,
)
ASSIGNED_VALUE_RE = re.compile(
    r"[\"']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password)"
    r"[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
ASSIGNMENT_NAME_RE = re.compile(
    r"[\"']?([A-Za-z_][A-Za-z0-9_-]*)[\"']?\s*[:=]",
)
TEMPLATE_VALUE_RE = re.compile(
    r"(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|"
    r"\{\{\s*[A-Za-z_][A-Za-z0-9_.-]*\s*\}\}|"
    r"<[A-Za-z_][A-Za-z0-9_.-]*>|"
    r"%[A-Za-z_][A-Za-z0-9_]*%)"
)
PEM_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"[\s\r\n]+[A-Za-z0-9+/=\s]{32,}"
    r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.MULTILINE,
)


def _source_line(repo: Path, commit: str, path: str, line_number: int) -> Optional[str]:
    if not COMMIT_RE.fullmatch(commit) or line_number <= 0:
        return None
    normalized = str(path).replace("\\", "/").lstrip("/")
    if not normalized or normalized == "Git history":
        return None
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", "{}:{}".format(commit, normalized)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    lines = completed.stdout.decode("utf-8", errors="replace").splitlines()
    if line_number > len(lines):
        return None
    return lines[line_number - 1]


def _source_text(repo: Path, commit: str, path: str) -> Optional[str]:
    if not COMMIT_RE.fullmatch(commit):
        return None
    normalized = str(path).replace("\\", "/").lstrip("/")
    if not normalized or normalized == "Git history":
        return None
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", "{}:{}".format(commit, normalized)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


def _candidate(line: str) -> Optional[str]:
    for expression in (AUTH_VALUE_RE, ASSIGNED_VALUE_RE):
        match = expression.search(line)
        if match:
            return match.group(1).strip()
    return None


def _example_context(path: str, config: Dict[str, Any]) -> bool:
    normalized = PurePosixPath(str(path).replace("\\", "/"))
    extensions = {
        str(value).lower()
        for value in config.get("documentation_extensions", [])
        if str(value).strip()
    }
    if normalized.suffix.lower() in extensions:
        return True
    segments = {part.lower() for part in normalized.parts}
    markers = {
        str(value).lower()
        for value in config.get("example_path_segments", [])
        if str(value).strip()
    }
    return bool(segments.intersection(markers))


def deterministic_placeholder_reason(
    item: Dict[str, Any],
    *,
    source_repo: Path,
    target_commit: str,
    config: Dict[str, Any],
) -> Optional[str]:
    """Return a reason only when source evidence proves a non-secret fixture."""

    if not config.get("enabled", False):
        return None
    commit = str(item.get("Commit") or target_commit or "")
    path = str(item.get("File") or "")
    line_number = item.get("StartLine")
    if not isinstance(line_number, int):
        return None
    line = _source_line(source_repo, commit, path, line_number)
    if line is None:
        return None

    rule = str(item.get("RuleID") or "").lower()
    non_secret_rule_ids = {
        str(value).lower()
        for value in config.get("non_secret_assignment_rule_ids", [])
        if str(value).strip()
    }
    non_secret_names = {
        str(value).lower()
        for value in config.get("non_secret_assignment_names", [])
        if str(value).strip()
    }
    assignment = ASSIGNMENT_NAME_RE.search(line)
    if (
        rule in non_secret_rule_ids
        and assignment is not None
        and assignment.group(1).lower() in non_secret_names
    ):
        return "non-secret-assignment"

    marker_rule_ids = {
        str(value).lower()
        for value in config.get("safe_marker_rule_ids", [])
        if str(value).strip()
    }
    if rule in marker_rule_ids and _example_context(path, config):
        for expression in config.get("safe_marker_line_patterns", []):
            try:
                matched = re.search(str(expression), line)
            except re.error:
                return None
            if not matched:
                continue
            source = _source_text(source_repo, commit, path)
            if source is not None and not PEM_BLOCK_RE.search(source):
                return "safe-marker"

    candidate = _candidate(line)
    if not candidate:
        return None

    # Template references do not contain credential material and are safe in any path.
    if TEMPLATE_VALUE_RE.fullmatch(candidate):
        return "template-reference"

    # Human-readable literals are ignored only in documentation/example contexts.
    if not _example_context(path, config):
        return None
    for value in config.get("literal_patterns", []):
        try:
            if re.fullmatch(str(value), candidate):
                return "placeholder-literal"
        except re.error:
            # Policy validation reports malformed patterns; never skip on parser failure.
            return None
    return None


def is_deterministic_placeholder(
    item: Dict[str, Any],
    *,
    source_repo: Path,
    target_commit: str,
    config: Dict[str, Any],
) -> bool:
    """Compatibility wrapper for callers that need only a boolean result."""

    return (
        deterministic_placeholder_reason(
            item,
            source_repo=source_repo,
            target_commit=target_commit,
            config=config,
        )
        is not None
    )
