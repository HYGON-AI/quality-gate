# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Render concise GitHub Job Summary output for the PR gate."""

from pathlib import Path
from typing import Any, Dict, List


SCANNER_DISPLAY_NAMES = {
    "sensitive-diff": "Sensitive Diff Text",
    "identity": "Built-in / 内置检查",
    "native-git": "Built-in / 内置检查",
    "native-syntax": "Built-in / 内置检查",
    "compliance": "Built-in / 内置检查",
    "gitleaks": "Gitleaks",
    "semgrep": "Semgrep",
    "ruff": "Ruff",
    "quality-tools": "Quality Tools / 质量工具",
    "trivy": "Trivy",
    "external-scanners": "External Scanners / 外部扫描器",
    "pr-gate-orchestrator": "Gate Orchestrator / 门禁调度器",
}


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_summary(data: Dict[str, Any], output: Path) -> None:
    findings = data.get("findings", [])
    blockers = [item for item in findings if item.get("level") == "blocker"]
    advisories = [item for item in findings if item.get("level") != "blocker"]
    status_icon = {
        "passed": "Passed / 通过",
        "findings": "Findings / 有发现",
        "failed": "Failed / 执行失败",
        "disabled": "Skipped / 未执行",
    }
    display_name = _escape(data.get("display_name") or "Unknown Check")
    display_name_zh = _escape(data.get("display_name_zh") or "未知检查")
    lines: List[str] = [
        "# Quality Gate · PR 增量门禁",
        "",
        "- Repository / 仓库：`{}`".format(_escape(data["repository"])),
        "- Check / 检查项：`{}`（{}）".format(display_name, display_name_zh),
        "- Comparison / 比较范围：`{}..{}`".format(
            data["scope"]["merge_base"][:12], data["scope"]["head"][:12]
        ),
        "- Changed Files / 变更文件：{}".format(len(data["scope"]["changes"])),
        "- Commits / 引入提交：{}".format(len(data["scope"]["commits"])),
        "- Blockers / 阻断问题：{}".format(len(blockers)),
        "- Advisories / 提示问题：{}".format(len(advisories)),
        "",
        "## Results / 检查结果",
        "",
        "| Scanner / 扫描器 | Status / 状态 | Findings / 发现数 | Details / 说明 |",
        "| --- | --- | ---: | --- |",
    ]
    for item in data.get("statuses", []):
        scanner = str(item.get("scanner") or "")
        lines.append(
            "| {} | {} | {} | {} |".format(
                _escape(SCANNER_DISPLAY_NAMES.get(scanner, "Scanner / 扫描器")),
                status_icon.get(item.get("state"), _escape(item.get("state"))),
                int(item.get("finding_count") or 0),
                _escape(item.get("detail") or ""),
            )
        )
    if blockers:
        lines.extend(["", "## Required Changes / 必须修改", ""])
        for item in blockers:
            location = "`{}`".format(_escape(item.get("path") or ""))
            if item.get("line"):
                location += " 第 {} 行".format(item["line"])
            lines.append("### {}".format(location))
            lines.append("")
            lines.append("- **Issue / 问题**：{}".format(_escape(item["title"])))
            lines.append("- **Reason / 原因**：{}".format(_escape(item.get("evidence") or "")))
            lines.append(
                "- **Remediation / 修改要求**：{}".format(
                    _escape(item.get("remediation") or "")
                )
            )
            lines.append("")
    if advisories:
        lines.extend(["", "## Advisories / 提示项（不阻断）", ""])
        for item in advisories[:100]:
            lines.append(
                "- `{}`：{}；{}".format(
                    _escape(item.get("path") or ""),
                    _escape(item.get("title") or ""),
                    _escape(item.get("remediation") or ""),
                )
            )
        if len(advisories) > 100:
            lines.append("- 其余 {} 个提示已省略。".format(len(advisories) - 100))
    if data.get("operational_error"):
        lines.extend(
            [
                "",
                "## Invalid Scan / 扫描无效",
                "",
                "- {}".format(_escape(data["operational_error"])),
                "- 扫描器执行失败不得解释为通过。",
            ]
        )
    lines.extend(
        [
            "",
            "## Decision / 判定",
            "",
            "**{}**".format(
                "⚠️ Invalid Scan / 扫描无效"
                if data.get("operational_error")
                else "❌ Blocked / 本检查阻断"
                if blockers
                else "✅ Passed / 本检查通过"
            ),
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
