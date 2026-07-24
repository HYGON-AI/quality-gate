#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Run deterministic quality tools and emit one normalized JSON document."""

import argparse
import csv
import io
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def run(command: Sequence[str], *, cwd: Path, allowed=(0,)) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode not in allowed:
        raise RuntimeError(
            "{} failed ({}): {}".format(
                command[0],
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace").strip(),
            )
        )
    return completed


def tracked_files(repo: Path) -> List[str]:
    output = run(["git", "ls-files", "-z"], cwd=repo).stdout
    result = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", errors="replace")
        full = repo / path
        if full.is_file() and not full.is_symlink():
            result.append(path)
    return result


def batches(values: List[str], size: int = 150) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def shell_paths(repo: Path, paths: List[str]) -> List[str]:
    result = []
    for path in paths:
        if Path(path).suffix.lower() in {".sh", ".bash", ".ksh"}:
            result.append(path)
            continue
        try:
            first = (repo / path).open("rb").readline(256)
        except OSError:
            continue
        if re.match(br"^#!.*\b(?:ba|da|k|z)?sh\b", first):
            result.append(path)
    return result


def scan_shellcheck(repo: Path, paths: List[str]) -> List[Dict[str, Any]]:
    findings = []
    for batch in batches(shell_paths(repo, paths), 100):
        if not batch:
            continue
        completed = run(["shellcheck", "--format=json1", *batch], cwd=repo, allowed=(0, 1))
        if not completed.stdout.strip():
            continue
        document = json.loads(completed.stdout.decode("utf-8"))
        comments = document.get("comments", []) if isinstance(document, dict) else document
        for item in comments:
            level = str(item.get("level") or "warning").lower()
            severity = "error" if level == "error" else "warning" if level == "warning" else "info"
            findings.append(
                {
                    "tool": "shellcheck",
                    "code": "SC{}".format(item.get("code", "")),
                    "severity": severity,
                    "path": str(item.get("file") or ""),
                    "line": item.get("line"),
                    "title": "Shell 脚本存在{}问题".format("错误" if severity == "error" else "风险"),
                    "message": str(item.get("message") or ""),
                    "remediation": "按 ShellCheck 规则修复并保持脚本行为不变。",
                }
            )
    return findings


def scan_actionlint(repo: Path, paths: List[str]) -> List[Dict[str, Any]]:
    workflow_root = repo / ".github" / "workflows"
    if not workflow_root.is_dir():
        return []
    requested = set(paths)
    workflow_paths = sorted(
        str(path.relative_to(repo))
        for path in workflow_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".yaml", ".yml"}
        and str(path.relative_to(repo)) in requested
    )
    output_lines = []
    for workflow_path in workflow_paths:
        completed = run(
            [
                "actionlint",
                "-shellcheck=",
                "-format",
                "{{json .}}",
                workflow_path,
            ],
            cwd=repo,
            allowed=(0, 1),
        )
        output_lines.extend(
            completed.stdout.decode("utf-8", errors="replace").splitlines()
        )
    findings = []
    for raw in output_lines:
        raw = raw.strip()
        if not raw:
            continue
        decoded = json.loads(raw)
        items = decoded if isinstance(decoded, list) else [decoded]
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "workflow")
            message = str(item.get("message") or "")
            severity = "error"
            if kind == "runner-label":
                severity = "warning"
            if kind == "shellcheck":
                match = re.search(r"SC\d+:(error|warning|info|style):", message)
                shell_level = match.group(1) if match else "warning"
                severity = (
                    "error"
                    if shell_level == "error"
                    else "warning"
                    if shell_level == "warning"
                    else "info"
                )
            findings.append(
                {
                    "tool": "actionlint",
                    "code": kind,
                    "severity": severity,
                    "path": str(item.get("filepath") or ""),
                    "line": item.get("line"),
                    "title": "GitHub Actions 工作流存在{}".format(
                        "错误" if severity == "error" else "风险"
                    ),
                    "message": message,
                    "remediation": "修复 Workflow 语法、表达式、Job/Step 引用或内嵌 Shell 问题。",
                }
            )
    return findings


YAMLLINT_RE = re.compile(
    r"^(.*?):(\d+):(\d+): \[(warning|error)\] (.*?) \(([^)]+)\)$"
)


def scan_yamllint(repo: Path, paths: List[str]) -> List[Dict[str, Any]]:
    yaml_paths = [path for path in paths if Path(path).suffix.lower() in {".yaml", ".yml"}]
    config = "{extends: default, rules: {document-start: disable, truthy: disable, line-length: {max: 120, level: warning}}}"
    findings = []
    for batch in batches(yaml_paths, 100):
        completed = run(
            ["yamllint", "-f", "parsable", "-d", config, *batch],
            cwd=repo,
            allowed=(0, 1),
        )
        for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
            match = YAMLLINT_RE.match(line)
            if not match:
                continue
            path, row, _column, severity, message, rule = match.groups()
            is_hard = rule in {"syntax", "key-duplicates"}
            findings.append(
                {
                    "tool": "yamllint",
                    "code": rule,
                    "severity": "error" if is_hard else "info",
                    "path": path,
                    "line": int(row),
                    "title": "YAML {}问题".format("语法" if is_hard else "规范"),
                    "message": message,
                    "remediation": (
                        "修复 YAML 语法或重复键。"
                        if is_hard
                        else "建议按仓库 YAML 规范统一格式；第一版不阻断。"
                    ),
                }
            )
    return findings


def scan_lizard(repo: Path, paths: List[str]) -> List[Dict[str, Any]]:
    extensions = {".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cu", ".cuh", ".js", ".ts", ".java", ".go", ".rs"}
    source_paths = [path for path in paths if Path(path).suffix.lower() in extensions]
    findings = []
    for batch in batches(source_paths, 120):
        completed = run(["lizard", "--csv", *batch], cwd=repo, allowed=(0,))
        content = completed.stdout.decode("utf-8", errors="replace")
        if not content.strip():
            continue
        fieldnames = [
            "NLOC",
            "CCN",
            "token",
            "PARAM",
            "length",
            "location",
            "file",
            "function",
            "long_name",
            "start",
            "end",
        ]
        for row in csv.DictReader(io.StringIO(content), fieldnames=fieldnames):
            try:
                ccn = int(row.get("CCN") or 0)
                nloc = int(row.get("NLOC") or 0)
                params = int(row.get("PARAM") or 0)
                start = int(row.get("start") or 0)
            except ValueError:
                continue
            reasons = []
            if ccn > 15:
                reasons.append("圈复杂度 {} > 15".format(ccn))
            if nloc > 100:
                reasons.append("函数有效代码行 {} > 100".format(nloc))
            if params > 8:
                reasons.append("参数数量 {} > 8".format(params))
            if not reasons:
                continue
            findings.append(
                {
                    "tool": "lizard",
                    "code": "complexity",
                    "severity": "info",
                    "path": str(row.get("file") or ""),
                    "line": start or None,
                    "title": "函数复杂度较高",
                    "message": "{}；函数 {}".format(
                        "，".join(reasons), str(row.get("function") or "unknown")
                    ),
                    "remediation": "建议拆分函数、降低分支复杂度；第一版不阻断。",
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paths-file", type=Path)
    args = parser.parse_args()
    tracked = set(tracked_files(args.repo))
    if args.paths_file:
        requested = []
        for raw in args.paths_file.read_text(encoding="utf-8").splitlines():
            path = raw.strip().replace("\\", "/")
            if not path or path.startswith("/") or ".." in Path(path).parts:
                raise ValueError("invalid path in --paths-file")
            if path in tracked:
                requested.append(path)
        paths = sorted(set(requested))
    else:
        paths = sorted(tracked)
    findings = []
    errors = []
    scanners = (
        ("shellcheck", lambda: scan_shellcheck(args.repo, paths)),
        ("actionlint", lambda: scan_actionlint(args.repo, paths)),
        ("yamllint", lambda: scan_yamllint(args.repo, paths)),
        ("lizard", lambda: scan_lizard(args.repo, paths)),
    )
    for name, scanner in scanners:
        try:
            findings.extend(scanner())
        except Exception as error:  # record tool coverage failure in output
            errors.append("{}: {}".format(name, error))
    args.output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tracked_files": len(paths),
                "findings": findings,
                "operational_errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
