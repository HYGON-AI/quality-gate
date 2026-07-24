# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Stable finding and scanner-result models."""

import hashlib
from typing import Any, Dict, Optional


ATTENTION_LEVELS = {"blocker", "review"}


def finding(
    rule_id: str,
    scanner: str,
    path: str,
    title: str,
    evidence: str,
    remediation: str,
    *,
    level: str,
    line: Optional[int] = None,
    commit: Optional[str] = None,
    fingerprint: Optional[str] = None,
    origin: str = "unknown",
    confidence: str = "unknown",
    reachability: str = "unknown",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if level not in {"blocker", "review", "advisory"}:
        raise ValueError("invalid finding level: {}".format(level))
    stable = "\0".join(
        [rule_id, scanner, path, str(line or ""), str(commit or ""), evidence]
    )
    return {
        "rule_id": rule_id,
        "scanner": scanner,
        "path": path,
        "title": title,
        "evidence": evidence,
        "remediation": remediation,
        "level": level,
        "line": line,
        "commit": commit,
        "fingerprint": fingerprint
        or hashlib.sha256(stable.encode("utf-8", errors="replace")).hexdigest(),
        "exception": None,
        "origin": origin,
        "origin_evidence": "",
        "confidence": confidence,
        "reachability": reachability,
        "metadata": dict(metadata or {}),
    }


def scanner_status(
    scanner: str,
    state: str,
    *,
    detail: str = "",
    version: str = "",
    image: str = "",
    finding_count: int = 0,
) -> Dict[str, Any]:
    if state not in {"passed", "findings", "disabled", "failed"}:
        raise ValueError("invalid scanner state: {}".format(state))
    return {
        "scanner": scanner,
        "state": state,
        "detail": detail,
        "version": version,
        "image": image,
        "finding_count": finding_count,
    }
