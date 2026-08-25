#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Run the deterministic incremental HYGON pull-request gate."""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hygon_quality_security.models import scanner_status

from .git_scope import PRGitError, collect_scope
from .local_executor import LocalDockerExecutor, LocalExecutionError
from .sensitive_diff_check import scan_sensitive_diff
from .native_checks import (
    scan_compliance,
    scan_git_and_encoding,
    scan_identity,
    scan_syntax_and_workflows,
)
from .policy import load_policy
from .render_summary import render_summary


NATIVE_CHECKS = {
    "identity": scan_identity,
    "git-encoding": scan_git_and_encoding,
    "syntax-workflow": scan_syntax_and_workflows,
    "compliance": scan_compliance,
    "sensitive-diff": scan_sensitive_diff,
}
EXTERNAL_CHECKS = ("gitleaks", "semgrep", "ruff", "quality-tools")
ALL_CHECKS = tuple(NATIVE_CHECKS) + EXTERNAL_CHECKS

CHECK_DISPLAY_NAMES = {
    "sensitive-diff": ("Sensitive Diff Text", "Sensitive Diff Text"),
    "identity": ("Commit Identity", "提交身份"),
    "git-encoding": ("File Integrity", "文件完整性"),
    "syntax-workflow": ("Workflow Integrity", "工作流完整性"),
    "compliance": ("License Compliance", "许可证合规"),
    "gitleaks": ("Secret Detection", "密钥泄露检测"),
    "semgrep": ("Code Security", "代码安全"),
    "ruff": ("Code Quality", "代码质量"),
    "quality-tools": ("Code Quality", "代码质量"),
}

CHECK_GROUP_DISPLAY_NAMES = {
    ("identity", "compliance", "sensitive-diff"): (
        "Identity, license & wording",
        "治理与许可证合规",
    ),
    ("git-encoding", "syntax-workflow", "ruff", "quality-tools"): (
        "Repository & code quality",
        "仓库完整性与代码质量",
    ),
    ("gitleaks", "semgrep"): (
        "Secrets & SAST",
        "安全检查",
    ),
}


def _workflow_command_escape(value: Any, *, property_value: bool = False) -> str:
    escaped = (
        str(value)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def _github_annotation(item: Dict[str, Any]) -> str:
    command = "error" if item.get("level") == "blocker" else "warning"
    properties = []
    path = str(item.get("path") or "").strip()
    if path and path != "Git history":
        properties.append(
            "file={}".format(_workflow_command_escape(path, property_value=True))
        )
    line = item.get("line")
    if isinstance(line, int) and line > 0:
        properties.append("line={}".format(line))
    title = str(item.get("rule_id") or item.get("title") or "Quality Gate")
    properties.append("title={}".format(_workflow_command_escape(title, property_value=True)))
    message = "{}；{}".format(
        str(item.get("title") or "Quality Gate finding"),
        str(item.get("remediation") or "请查看 Job Summary。"),
    )
    return "::{} {}::{}".format(
        command,
        ",".join(properties),
        _workflow_command_escape(message),
    )


def _emit_github_annotations(data: Dict[str, Any], maximum: int = 50) -> None:
    findings = list(data.get("findings", []))
    findings.sort(key=lambda item: item.get("level") != "blocker")
    for item in findings[:maximum]:
        print(_github_annotation(item))
    if len(findings) > maximum:
        print(
            "::notice title=Quality Gate::{} findings omitted; see Job Summary".format(
                len(findings) - maximum
            )
        )
    if data.get("operational_error"):
        print(
            "::error title=Quality Gate invalid scan::{}".format(
                _workflow_command_escape(data["operational_error"])
            )
        )


def _selected_checks(value: str) -> List[str]:
    requested = [item.strip() for item in str(value or "all").split(",") if item.strip()]
    if not requested or requested == ["all"]:
        return list(ALL_CHECKS)
    unknown = sorted(set(requested) - set(ALL_CHECKS))
    if unknown:
        raise ValueError("unknown PR check(s): {}".format(", ".join(unknown)))
    return [name for name in ALL_CHECKS if name in requested]


def _check_display_name(selected: List[str]) -> Tuple[str, str]:
    if selected == list(ALL_CHECKS):
        return "All Checks", "全部检查"
    grouped = CHECK_GROUP_DISPLAY_NAMES.get(tuple(selected))
    if grouped is not None:
        return grouped
    labels: List[Tuple[str, str]] = []
    for name in selected:
        label = CHECK_DISPLAY_NAMES[name]
        if label not in labels:
            labels.append(label)
    if len(labels) != 1:
        raise ValueError("selected PR checks do not form one display group")
    return labels[0]


def run_gate(args: argparse.Namespace) -> Tuple[Path, int]:
    repo = args.repo.resolve()
    policy_root = args.policy_root.resolve()
    summary = args.summary.resolve()
    data: Dict[str, Any] = {
        "repository": args.repository,
        "scope": {
            "base": args.base,
            "head": args.head,
            "merge_base": args.base,
            "changes": [],
            "commits": [],
        },
        "findings": [],
        "statuses": [],
        "checks": [],
        "display_name": "Unknown Check",
        "display_name_zh": "未知检查",
        "operational_error": None,
    }
    try:
        selected = _selected_checks(getattr(args, "checks", "all"))
        data["checks"] = selected
        display_name, display_name_zh = _check_display_name(selected)
        requested_display_name = str(getattr(args, "display_name", "") or "").strip()
        if requested_display_name and requested_display_name != display_name:
            raise ValueError(
                "PR check display name mismatch: expected {}, got {}".format(
                    display_name, requested_display_name
                )
            )
        data["display_name"] = display_name
        data["display_name_zh"] = display_name_zh
        policy = load_policy(policy_root, args.repository)
        scope = collect_scope(repo, args.base.lower(), args.head.lower())
        data["scope"] = scope
        for name in selected:
            scanner = NATIVE_CHECKS.get(name)
            if scanner is None:
                continue
            current, status = scanner(repo, scope, policy)
            data["findings"].extend(current)
            data["statuses"].append(status)
        external = [name for name in selected if name in EXTERNAL_CHECKS]
        if external and args.native_only:
            data["statuses"].append(
                scanner_status(
                    "external-scanners",
                    "disabled",
                    detail="仅供中央仓库自测试使用；未执行 {}".format(
                        ", ".join(external)
                    ),
                )
            )
        elif external and policy.get("external_scanners", {}).get("enabled", False):
            executor = LocalDockerExecutor(policy, policy_root)
            external_findings, external_statuses = executor.scan(
                repo, scope, scanner_names=external
            )
            data["findings"].extend(external_findings)
            data["statuses"].extend(external_statuses)
        elif external:
            raise ValueError("central PR policy may not disable external scanners")
    except Exception as error:
        data["operational_error"] = "{}: {}".format(type(error).__name__, str(error))
        data["statuses"].append(
            scanner_status("pr-gate-orchestrator", "failed", detail=str(error)[:800])
        )
    render_summary(data, summary)
    if getattr(args, "github_annotations", False):
        _emit_github_annotations(data)
    if data["operational_error"]:
        return summary, 1
    if any(item.get("level") == "blocker" for item in data["findings"]):
        return summary, 2
    return summary, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hygon-compliance pr-gate")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--policy-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--checks",
        default="all",
        help="comma-separated check names: {}".format(",".join(ALL_CHECKS)),
    )
    parser.add_argument(
        "--display-name",
        default="",
        help="validated human-readable name for the selected check group",
    )
    parser.add_argument(
        "--github-annotations",
        action="store_true",
        help="emit escaped GitHub workflow annotations for findings",
    )
    parser.add_argument("--native-only", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    summary, exit_code = run_gate(args)
    print("SUMMARY={}".format(summary))
    print(
        "RESULT={}".format(
            "invalid" if exit_code == 1 else "blocked" if exit_code == 2 else "passed"
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
