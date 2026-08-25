# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Run pinned scanners locally on the self-hosted quality runner."""

import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from hygon_quality_security.models import scanner_status
from hygon_quality_security.scanner_parsers import (
    parse_gitleaks,
    parse_quality_tools,
    parse_ruff,
    parse_semgrep,
)

from .git_scope import git


class LocalExecutionError(RuntimeError):
    pass


SOURCE_EXTENSIONS = {
    ".bzl", ".c", ".cc", ".cmake", ".cpp", ".cu", ".cuh", ".cxx", ".go",
    ".h", ".hh", ".hip", ".hpp", ".hxx", ".java", ".js", ".jsx", ".kt",
    ".m", ".metal", ".mm", ".py", ".pyi", ".rs", ".sh", ".ts", ".tsx",
}


def _run(command: Sequence[str], *, allowed: Tuple[int, ...] = (0,), timeout: int = 1800) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if completed.returncode not in allowed:
        raise LocalExecutionError(
            "{} failed ({}): {}".format(
                command[0],
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace").strip()[:1000],
            )
        )
    return completed


def _write_paths(path: Path, values: Iterable[str]) -> None:
    path.write_text("\n".join(sorted(set(values))) + "\n", encoding="utf-8")


def _filter_changed_lines(
    findings: List[Dict[str, Any]], changed_lines: Dict[str, set]
) -> List[Dict[str, Any]]:
    filtered = []
    for item in findings:
        path = str(item.get("path") or "").replace("\\", "/")
        if path not in changed_lines:
            continue
        line = item.get("line")
        if isinstance(line, int) and changed_lines[path] and line not in changed_lines[path]:
            continue
        filtered.append(item)
    return filtered


class LocalDockerExecutor:
    def __init__(self, policy: Dict[str, Any], policy_root: Path):
        self.policy = policy
        self.policy_root = policy_root
        self.quality = policy["quality_security"]
        self.images = self.quality["images"]
        scanner_policy = policy["external_scanners"]
        self.timeout = int(scanner_policy.get("timeout_seconds", 1800))
        self.docker_cpus = str(scanner_policy.get("docker_cpus", 16))
        self.docker_memory = str(scanner_policy.get("docker_memory", "32g"))
        self.uid = os.getuid()
        self.gid = os.getgid()

    def _verify_image(self, name: str) -> None:
        image = str(self.images[name])
        _run(["docker", "image", "inspect", image], timeout=60)

    def _docker(
        self,
        image_name: str,
        repo: Path,
        reports: Path,
        arguments: Sequence[str],
        *,
        mounts: Sequence[Tuple[Path, str, str]] = (),
        environment: Sequence[Tuple[str, str]] = (),
        allowed: Tuple[int, ...] = (0,),
    ) -> subprocess.CompletedProcess:
        self._verify_image(image_name)
        command = [
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--cpus", self.docker_cpus, "--memory", self.docker_memory,
            "--user", "{}:{}".format(self.uid, self.gid),
            "-e", "HOME=/tmp",
            "-v", "{}:/repo:ro".format(repo.resolve()),
            "-v", "{}:/reports:rw".format(reports.resolve()),
            "-w", "/repo",
        ]
        for host, container, access in mounts:
            command.extend(["-v", "{}:{}:{}".format(host.resolve(), container, access)])
        for key, value in environment:
            command.extend(["-e", "{}={}".format(key, value)])
        command.extend([str(self.images[image_name]), *map(str, arguments)])
        return _run(command, allowed=allowed, timeout=self.timeout)

    @staticmethod
    def _status(name: str, findings: List[Dict[str, Any]], image: str, detail: str = "") -> Dict[str, Any]:
        return scanner_status(
            name,
            "findings" if findings else "passed",
            image=image,
            detail=detail,
            finding_count=len(findings),
        )

    def _gitleaks(
        self, repo: Path, scope: Dict[str, Any], reports: Path
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        report = reports / "gitleaks.json"
        self._docker(
            "gitleaks",
            repo,
            reports,
            [
                "detect", "--source", "/repo", "--redact", "--report-format", "json",
                "--report-path", "/reports/gitleaks.json", "--log-opts",
                "{}..{}".format(scope["base"], scope["head"]),
            ],
            allowed=(0, 1),
        )
        if not report.exists():
            report.write_text("[]", encoding="utf-8")
        findings, summary = parse_gitleaks(
            report,
            source_repo=repo,
            target_commit=scope["head"],
            placeholder_config=self.quality["scanners"]["gitleaks"].get("placeholder_filter", {}),
        )
        detail = (
            "扫描 PR 新增 Commit，已忽略 {} 个确定性占位符和 {} 个安全标记断言"
        ).format(
            summary.get("ignored_placeholders", 0),
            summary.get("ignored_safe_markers", 0),
        )
        return findings, self._status("gitleaks", findings, str(self.images["gitleaks"]), detail)

    def _semgrep(
        self, repo: Path, scope: Dict[str, Any], reports: Path, paths: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        targets = [path for path in paths if PurePosixPath(path).suffix.lower() in SOURCE_EXTENSIONS]
        if not targets:
            return [], scanner_status("semgrep", "passed", detail="PR 没有适用的变更源码")
        report = reports / "semgrep.json"
        rules = self.policy_root / "semgrep"
        self._docker(
            "semgrep",
            repo,
            reports,
            [
                "semgrep", "scan", "--config", "/rules/hygon-security-v1.yml",
                "--metrics", "off", "--json", "--output", "/reports/semgrep.json",
                "--error", *["/repo/{}".format(path) for path in targets],
            ],
            mounts=[(rules, "/rules", "ro")],
            environment=[("SEMGREP_SEND_METRICS", "off")],
            allowed=(0, 1),
        )
        findings, coverage = parse_semgrep(
            report, self.quality["scanners"]["semgrep"]
        )
        findings = _filter_changed_lines(findings, scope["changed_lines"])
        advisory_rules = {
            str(value).upper()
            for value in self.policy.get("advisory", {}).get("semgrep_rule_ids", [])
        }
        for item in findings:
            normalized_rule = str(item.get("rule_id") or "").replace("SAST.SEMGREP.", "")
            if normalized_rule.upper() in advisory_rules:
                item["level"] = "advisory"
        return findings, self._status(
            "semgrep", findings, str(self.images["semgrep"]),
            "本地规则、无网络；覆盖异常 {} 个".format(len(coverage)),
        )

    def _ruff(
        self, repo: Path, scope: Dict[str, Any], reports: Path, paths: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        targets = [path for path in paths if PurePosixPath(path).suffix.lower() in {".py", ".pyi"}]
        if not targets:
            return [], scanner_status("ruff", "passed", detail="PR 没有 Python 变更")
        report = reports / "ruff.json"
        self._docker(
            "ruff",
            repo,
            reports,
            [
                "check", "--select", "E9,F63,F7,F82", "--output-format", "json",
                "--output-file", "/reports/ruff.json", *["/repo/{}".format(path) for path in targets],
            ],
            environment=[("RUFF_CACHE_DIR", "/reports/ruff-cache")],
            allowed=(0, 1),
        )
        findings = _filter_changed_lines(
            parse_ruff(report, self.quality["scanners"]["ruff"]),
            scope["changed_lines"],
        )
        return findings, self._status("ruff", findings, str(self.images["ruff"]), "仅 E9,F63,F7,F82")

    def _quality_tools(
        self, repo: Path, scope: Dict[str, Any], reports: Path, paths: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not paths:
            return [], scanner_status("quality-tools", "passed", detail="PR 没有变更文件")
        report = reports / "quality-tools.json"
        path_file = reports / "changed-paths.txt"
        _write_paths(path_file, paths)
        driver = Path(__file__).resolve().parents[1] / "hygon_quality_security" / "quality_driver.py"
        self._docker(
            "quality_tools",
            repo,
            reports,
            [
                "python3", "/driver/quality_driver.py", "--repo", "/repo",
                "--output", "/reports/quality-tools.json", "--paths-file", "/reports/changed-paths.txt",
            ],
            mounts=[(driver, "/driver/quality_driver.py", "ro")],
            allowed=(0, 1),
        )
        findings = parse_quality_tools(report)
        findings = _filter_changed_lines(findings, scope["changed_lines"])
        for item in findings:
            if item["level"] == "review":
                item["level"] = "advisory"
        return findings, self._status("quality-tools", findings, str(self.images["quality_tools"]), "ShellCheck/actionlint/yamllint/Lizard")

    def scan(
        self,
        repo: Path,
        scope: Dict[str, Any],
        scanner_names: Sequence[str] = ("gitleaks", "semgrep", "ruff", "quality-tools"),
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        paths = [item["path"] for item in scope["changes"] if item["kind"] != "D"]
        findings: List[Dict[str, Any]] = []
        statuses: List[Dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="hygon-pr-gate-") as directory:
            reports = Path(directory)
            scanners = {
                "gitleaks": lambda: self._gitleaks(repo, scope, reports),
                "semgrep": lambda: self._semgrep(repo, scope, reports, paths),
                "ruff": lambda: self._ruff(repo, scope, reports, paths),
                "quality-tools": lambda: self._quality_tools(repo, scope, reports, paths),
            }
            unknown = sorted(set(scanner_names) - set(scanners))
            if unknown:
                raise LocalExecutionError(
                    "unknown external scanner(s): {}".format(", ".join(unknown))
                )
            for name in scanner_names:
                scanner = scanners[name]
                current, status = scanner()
                findings.extend(current)
                statuses.append(status)
        return findings, statuses
