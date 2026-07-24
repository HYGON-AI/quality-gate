# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Parse external scanner output without exposing secret material."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import finding
from .secret_placeholders import deterministic_placeholder_reason


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("invalid scanner JSON {}: {}".format(path.name, error))


def _relative(path: str) -> str:
    value = str(path).replace("\\", "/")
    for prefix in ("/repo/", "/src/"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def parse_gitleaks(
    path: Path,
    *,
    source_repo: Optional[Path] = None,
    target_commit: str = "",
    placeholder_config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    document = _load_json(path)
    if not isinstance(document, list):
        raise ValueError("gitleaks report root must be a list")
    findings = []
    summary = {
        "raw_findings": 0,
        "ignored_placeholders": 0,
        "ignored_safe_markers": 0,
        "reported_findings": 0,
    }
    for item in document:
        if not isinstance(item, dict):
            continue
        summary["raw_findings"] += 1
        if source_repo is not None:
            ignored_reason = deterministic_placeholder_reason(
                item,
                source_repo=source_repo,
                target_commit=target_commit,
                config=placeholder_config or {},
            )
            if ignored_reason:
                if ignored_reason == "safe-marker":
                    summary["ignored_safe_markers"] += 1
                else:
                    summary["ignored_placeholders"] += 1
                continue
        rule = str(item.get("RuleID") or item.get("Description") or "unknown")
        file_path = _relative(str(item.get("File") or "Git history"))
        commit = str(item.get("Commit") or "") or None
        line = item.get("StartLine")
        fingerprint = str(item.get("Fingerprint") or "") or None
        evidence = "规则 {} 命中；密钥内容已脱敏".format(rule)
        if commit:
            evidence += "；Commit {}".format(commit[:12])
        findings.append(
            finding(
                "SECRET.GITLEAKS.{}".format(rule.upper().replace("_", "-")),
                "gitleaks",
                file_path,
                "Git 当前树或历史中疑似包含密钥",
                evidence,
                "立即吊销并轮换凭据，清理待发布 Git 历史；不得只删除当前文件。",
                level="blocker",
                line=int(line) if isinstance(line, int) else None,
                commit=commit,
                fingerprint=fingerprint,
                confidence="high",
                reachability="not-applicable",
            )
        )
    summary["reported_findings"] = len(findings)
    return findings, summary


def parse_trivy(
    path: Path, policy: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    document = _load_json(path)
    if not isinstance(document, dict) or not isinstance(document.get("Results", []), list):
        raise ValueError("trivy report has no Results list")
    policy = policy or {}
    block_fixable = {
        str(value).upper()
        for value in policy.get("block_fixable_severities", ["CRITICAL", "HIGH"])
    }
    review_fixable = {
        str(value).upper()
        for value in policy.get("review_fixable_severities", [])
    }
    review_unfixed = {
        str(value).upper()
        for value in policy.get("review_unfixed_severities", ["CRITICAL", "HIGH"])
    }
    findings = []
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    for result in document.get("Results", []):
        target = _relative(str(result.get("Target") or "Dependency manifest"))
        for item in result.get("Vulnerabilities") or []:
            severity = str(item.get("Severity") or "UNKNOWN").upper()
            summary[severity if severity in summary else "UNKNOWN"] += 1
            if severity not in {"CRITICAL", "HIGH"}:
                continue
            vulnerability = str(item.get("VulnerabilityID") or "unknown")
            package = str(item.get("PkgName") or "unknown")
            installed = str(item.get("InstalledVersion") or "unknown")
            fixed = str(item.get("FixedVersion") or "").strip()
            if fixed and severity in block_fixable:
                level = "blocker"
            elif fixed and severity in review_fixable:
                level = "review"
            elif not fixed and severity in review_unfixed:
                level = "review"
            else:
                level = "advisory"
            evidence = "{} {}，当前版本 {}".format(vulnerability, package, installed)
            if fixed:
                evidence += "，修复版本 {}".format(fixed)
                remediation = (
                    "先核对受影响功能、运行时可达性和语言工具链兼容性；兼容时升级 {} 至 {} "
                    "或更高安全版本，不兼容时登记缓解措施和限期例外。"
                ).format(package, fixed)
            else:
                evidence += "，扫描数据库未提供修复版本"
                remediation = "核对影响面、上游处置计划和缓解措施；无法修复时申请限期例外。"
            findings.append(
                finding(
                    "SCA.TRIVY.{}".format(vulnerability.upper()),
                    "trivy",
                    target,
                    "依赖存在 {} 漏洞".format(severity),
                    evidence,
                    remediation,
                    level=level,
                    fingerprint="trivy:{}:{}:{}".format(vulnerability, package, target),
                    confidence="high",
                    reachability="unknown",
                    metadata={
                        "severity": severity,
                        "package": package,
                        "installed_version": installed,
                        "fixed_version": fixed,
                        "fix_available": bool(fixed),
                    },
                )
            )
    return findings, summary


def parse_semgrep(
    path: Path, policy: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    document = _load_json(path)
    if not isinstance(document, dict) or not isinstance(document.get("results", []), list):
        raise ValueError("semgrep report has no results list")
    policy = policy or {}
    block_rule_ids = {
        str(value) for value in policy.get("block_rule_ids", [])
    }
    advisory_rule_ids = {
        str(value) for value in policy.get("advisory_rule_ids", [])
    }
    block_severities = {
        str(value).upper() for value in policy.get("block_severities", ["ERROR"])
    }
    review_severities = {
        str(value).upper()
        for value in policy.get("review_severities", ["WARNING"])
    }
    findings = []
    coverage_errors = []
    for error in document.get("errors") or []:
        if not isinstance(error, dict):
            continue
        message = str(error.get("message") or error.get("type") or "Semgrep error")
        path_value = _relative(str(error.get("path") or ""))
        if path_value:
            coverage_errors.append("{}: {}".format(path_value, message))
            findings.append(
                finding(
                    "SAST.SEMGREP.COVERAGE",
                    "semgrep",
                    path_value,
                    "Semgrep 无法完整解析该文件",
                    message,
                    "确认语言版本或生成语法；必要时补充兼容规则，不能将未解析视为通过。",
                    level="review",
                )
            )
        else:
            coverage_errors.append(message)
    for item in document["results"]:
        extra = item.get("extra") or {}
        severity = str(extra.get("severity") or "WARNING").upper()
        rule = str(item.get("check_id") or "unknown")
        metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
        confidence = str(metadata.get("confidence") or "unknown").lower()
        reachability = str(metadata.get("reachability") or "unknown").lower()
        if rule in block_rule_ids:
            level = "blocker"
        elif rule in advisory_rule_ids:
            level = "advisory"
        elif severity in block_severities:
            level = "blocker"
        elif severity in review_severities:
            level = "review"
        else:
            level = "advisory"
        file_path = _relative(str(item.get("path") or "Unknown file"))
        start = item.get("start") or {}
        line = start.get("line")
        message = str(extra.get("message") or "命中本地 SAST 规则")
        findings.append(
            finding(
                "SAST.SEMGREP.{}".format(rule.upper()),
                "semgrep",
                file_path,
                "静态分析发现潜在安全问题",
                "{}：{}".format(rule, message),
                "按规则说明消除危险数据流；如无法确认可利用性，提交安全核对结论。",
                level=level,
                line=int(line) if isinstance(line, int) else None,
                fingerprint=str(extra.get("fingerprint") or "") or None,
                confidence=confidence,
                reachability=reachability,
                metadata={"severity": severity, "rule_id": rule},
            )
        )
    return findings, coverage_errors


def parse_ruff(
    path: Path, policy: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    document = _load_json(path)
    if not isinstance(document, list):
        raise ValueError("ruff report root must be a list")
    policy = policy or {}
    blocker_patterns = [
        re.compile(str(value), re.IGNORECASE)
        for value in policy.get("block_code_patterns", [r"^E9", r"^F63", r"^F7", r"^F82"])
    ]
    review_patterns = [
        re.compile(str(value), re.IGNORECASE)
        for value in policy.get("review_code_patterns", [])
    ]
    default_level = str(policy.get("default_level", "review"))
    findings = []
    for item in document:
        code = str(item.get("code") or "unknown")
        location = item.get("location") or {}
        file_path = _relative(str(item.get("filename") or "Unknown file"))
        if any(expression.search(code) for expression in blocker_patterns):
            level = "blocker"
        elif any(expression.search(code) for expression in review_patterns):
            level = "review"
        else:
            level = default_level
        findings.append(
            finding(
                "QUALITY.RUFF.{}".format(code.upper()),
                "ruff",
                file_path,
                "Python 高置信正确性问题",
                "{}：{}".format(code, str(item.get("message") or "Ruff finding")),
                "修复语法、未定义名称或无效控制流问题；本基线不因格式风格阻断。",
                level=level,
                line=int(location.get("row")) if isinstance(location.get("row"), int) else None,
                confidence="high" if level == "blocker" else "medium",
                reachability="unknown",
                metadata={"code": code},
            )
        )
    return findings


def parse_quality_tools(path: Path) -> List[Dict[str, Any]]:
    document = _load_json(path)
    if not isinstance(document, dict) or not isinstance(document.get("findings", []), list):
        raise ValueError("quality-tools report has no findings list")
    errors = document.get("operational_errors") or []
    if errors:
        raise ValueError("quality-tools coverage failed: {}".format("; ".join(map(str, errors))))
    normalized = []
    grouped = {}
    for item in document["findings"]:
        tool = str(item.get("tool") or "quality-tools")
        if tool not in {"yamllint", "lizard", "actionlint", "shellcheck"}:
            normalized.append(item)
            continue
        item = dict(item)
        original_code = str(item.get("code") or "FINDING")
        if tool == "actionlint":
            if original_code.lower() == "runner-label":
                item["severity"] = "warning"
        key = (
            tool,
            str(item.get("path") or "Unknown file"),
            str(item.get("code") or "FINDING"),
            str(item.get("severity") or "warning").lower(),
        )
        bucket = grouped.setdefault(
            key,
            {
                "item": dict(item),
                "count": 0,
                "lines": [],
                "messages": [],
            },
        )
        bucket["count"] += 1
        if isinstance(item.get("line"), int):
            bucket["lines"].append(item["line"])
        message = str(item.get("message") or "").strip()
        if message and message not in bucket["messages"]:
            bucket["messages"].append(message)
    for bucket in grouped.values():
        item = bucket["item"]
        details = ["同文件同规则共 {} 处".format(bucket["count"])]
        lines = sorted(set(bucket["lines"]))[:8]
        messages = sorted(set(bucket["messages"]))[:3]
        if lines:
            details.append("示例行 {}".format("、".join(map(str, lines))))
        if messages:
            details.append("；".join(messages))
        item["message"] = "；".join(details)
        normalized.append(item)

    findings = []
    for item in normalized:
        tool = str(item.get("tool") or "quality-tools")
        severity = str(item.get("severity") or "warning").lower()
        level = "blocker" if severity == "error" else "review" if severity == "warning" else "advisory"
        if tool == "lizard":
            level = "advisory"
        findings.append(
            finding(
                "QUALITY.{}.{}".format(
                    tool.upper().replace("-", "_"),
                    str(item.get("code") or "FINDING").upper().replace("-", "_"),
                ),
                tool,
                _relative(str(item.get("path") or "Unknown file")),
                str(item.get("title") or "质量检查发现问题"),
                str(item.get("message") or ""),
                str(item.get("remediation") or "按工具提示修改并重新扫描。"),
                level=level,
                line=int(item["line"]) if isinstance(item.get("line"), int) else None,
            )
        )
    return findings
