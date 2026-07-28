# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Block sensitive platform terms introduced by a pull-request diff."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Sequence, Tuple

from hygon_quality_security.models import finding, scanner_status

from .git_scope import read_blob


MAX_SNIPPET_LENGTH = 180


def _expression(terms: Sequence[str], case_sensitive: bool) -> Pattern[str]:
    if not terms:
        raise ValueError("sensitive_diff.terms must be a non-empty list")
    normalized: List[str] = []
    for term in terms:
        value = str(term)
        if not value:
            raise ValueError("sensitive_diff terms must be non-empty strings")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("sensitive_diff terms must be unique")
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(
        "|".join(
            re.escape(value)
            for value in sorted(normalized, key=len, reverse=True)
        ),
        flags,
    )


def _text(data: Optional[bytes]) -> Optional[str]:
    if data is None or b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _snippet(value: str) -> str:
    result = " ".join(value.split())
    if len(result) > MAX_SNIPPET_LENGTH:
        result = result[: MAX_SNIPPET_LENGTH - 3] + "..."
    return result


def scan_sensitive_diff(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile_checks = policy.get("profile", {}).get("checks", {})
    if profile_checks.get("hcu_runtime_wording") is not True:
        return [], scanner_status(
            "sensitive-diff",
            "disabled",
            detail="Sensitive platform wording check is disabled for this repository.",
        )

    config = policy.get("sensitive_diff") or {}
    if config.get("enabled") is not True:
        raise ValueError("sensitive_diff policy must be enabled")
    expression = _expression(
        config.get("terms") or [],
        bool(config.get("case_sensitive", False)),
    )
    maximum = int(policy["git"]["max_text_scan_bytes"])
    findings: List[Dict[str, Any]] = []

    for change in scope["changes"]:
        if change["kind"] == "D":
            continue
        path = change["path"]
        for match in expression.finditer(path):
            findings.append(
                finding(
                    "SENSITIVE_DIFF.PATH",
                    "sensitive-diff",
                    path,
                    "Changed file path contains a sensitive platform term",
                    "Destination path contains {!r}.".format(match.group(0)),
                    "Rename the destination path and update its references.",
                    level="blocker",
                    line=1,
                )
            )

        text = _text(read_blob(repo, scope["head"], path, maximum))
        if text is None:
            continue
        added_lines = scope["changed_lines"].get(path, set())
        for number, line in enumerate(text.splitlines(), 1):
            if change["kind"] not in {"A", "C"} and number not in added_lines:
                continue
            for match in expression.finditer(line):
                findings.append(
                    finding(
                        "SENSITIVE_DIFF.ADDED_CONTENT",
                        "sensitive-diff",
                        path,
                        "Added content contains a sensitive platform term",
                        "Line {} contains {!r}: {}".format(
                            number,
                            match.group(0),
                            _snippet(line),
                        ),
                        "Update the added text to use approved HCU platform wording.",
                        level="blocker",
                        line=number,
                    )
                )

    return findings, scanner_status(
        "sensitive-diff",
        "findings" if findings else "passed",
        detail=(
            "Destination paths and added lines only; unchanged content, "
            "removed lines, and deleted paths are ignored."
        ),
        finding_count=len(findings),
    )
