# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""High-confidence native PR checks that never execute target repository code."""

import ast
import fnmatch
import posixpath
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml

from hygon_quality_security.models import finding, scanner_status

from .git_scope import blob_size, mode, read_blob


HYGON_COPYRIGHT = "Copyright (c) 2026 Hygon Information Technology Co., Ltd."
COPYRIGHT_RE = re.compile(r"copyright", re.IGNORECASE)
SPDX_RE = re.compile(
    r"^\s*(?:#|//+|/\*+|\*+|;|--)\s*"
    r"SPDX-License-Identifier:\s*([^\r\n*]+?)\s*(?:\*/)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
USES_RE = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*['\"]?([^\s'\"]+)", re.IGNORECASE)
PINNED_USES_RE = re.compile(r"^[^@\s]+@[0-9a-fA-F]{40}$")
TEXT_EXTENSIONS = {
    ".bzl", ".c", ".cc", ".cmake", ".cpp", ".cu", ".cuh", ".cxx",
    ".go", ".h", ".hh", ".hip", ".hpp", ".hxx", ".ini", ".java",
    ".js", ".json", ".jsx", ".kt", ".m", ".md", ".metal", ".mm",
    ".ps1", ".py", ".pyi", ".rs", ".sh", ".toml", ".ts", ".tsx",
    ".txt", ".xml", ".yaml", ".yml",
}
TEXT_NAMES = {"CMakeLists.txt", "Dockerfile", "Makefile", "BUILD", "WORKSPACE"}


def matches(path: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        value = str(pattern)
        if fnmatch.fnmatch(path, value):
            return True
        if value.startswith("**/") and fnmatch.fnmatch(path, value[3:]):
            return True
    return False


def is_source(path: str, policy: Dict[str, Any]) -> bool:
    source = policy["open_source"]["source_files"]
    return PurePosixPath(path).suffix.lower() in set(source.get("extensions", [])) or PurePosixPath(path).name in set(source.get("names", []))


def _text(path: str, data: Optional[bytes]) -> Optional[str]:
    if data is None or b"\0" in data[:8192]:
        return None
    if PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS and PurePosixPath(path).name not in TEXT_NAMES:
        return None
    return data.decode("utf-8")


def _header(text: str, line_count: int) -> str:
    return "\n".join(text.splitlines()[:line_count])


def _line_for_index(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _status(name: str, detail: str, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    return scanner_status(
        name,
        "findings" if findings else "passed",
        detail=detail,
        finding_count=len(findings),
    )


def scan_identity(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    brand = policy["brand_identity"]
    flags = 0 if brand.get("case_sensitive", False) else re.IGNORECASE
    raw_patterns = [str(value) for value in brand.get("forbidden_patterns", [])]
    if raw_patterns:
        expression = re.compile(
            "|".join("(?:{})".format(value) for value in raw_patterns),
            flags,
        )
    else:
        expression = re.compile(
            "|".join(
                re.escape(str(term))
                for term in brand.get("forbidden_terms", [])
            ),
            flags,
        )
    findings: List[Dict[str, Any]] = []
    max_bytes = int(policy["git"]["max_text_scan_bytes"])
    for change in scope["changes"]:
        path = change["path"]
        match = expression.search(path)
        if match:
            findings.append(
                finding(
                    "IDENTITY.FORBIDDEN_PATH",
                    "identity",
                    path,
                    "PR 文件路径包含禁止的品牌身份",
                    "路径命中大小写不敏感的禁止词 {}".format(match.group(0)),
                    "重命名文件并更新所有引用；hygon 标识允许保留。",
                    level="blocker",
                )
            )
        if change["kind"] == "D":
            continue
        data = read_blob(repo, scope["head"], path, max_bytes)
        if data is None or b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if change["kind"] not in {"A", "C"} and number not in scope["changed_lines"].get(path, set()):
                continue
            matched = expression.search(line)
            if not matched:
                continue
            findings.append(
                finding(
                    "IDENTITY.FORBIDDEN_CONTENT",
                    "identity",
                    path,
                    "PR 新版本文件包含禁止的品牌身份",
                    "第 {} 行命中大小写不敏感的禁止词 {}".format(number, matched.group(0)),
                    "删除或替换禁止身份；hygon 及 HYGON 邮箱允许保留。",
                    level="blocker",
                    line=number,
                )
            )
    commit_fields = {
        "author_name": "作者姓名",
        "author_email": "作者邮箱",
        "committer_name": "提交者姓名",
        "committer_email": "提交者邮箱",
        "subject": "Commit 标题",
        "body": "Commit 正文",
    }
    for commit in scope["commits"]:
        for key, title in commit_fields.items():
            matched = expression.search(str(commit.get(key) or ""))
            if not matched:
                continue
            findings.append(
                finding(
                    "IDENTITY.FORBIDDEN_COMMIT_{}".format(key.upper()),
                    "identity",
                    "Git commit {}".format(commit["commit"][:12]),
                    "{}包含禁止的品牌身份".format(title),
                    "命中大小写不敏感的禁止词 {}".format(matched.group(0)),
                    "在合并前重写该 Commit，并复查作者、提交者、邮箱和消息。",
                    level="blocker",
                    commit=commit["commit"],
                )
            )
    return findings, _status("identity", "变更路径、文件内容和 PR 引入的全部 Commit 元数据", findings)


def scan_git_and_encoding(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    maximum = int(policy["git"]["max_text_scan_bytes"])
    review_size = int(policy["git"]["large_file_review_bytes"])
    block_size = int(policy["git"]["large_file_block_bytes"])
    for change in scope["changes"]:
        path = change["path"]
        for character in path:
            if unicodedata.category(character) == "Cc":
                findings.append(
                    finding(
                        "GIT.PATH_CONTROL_CHARACTER",
                        "native-git",
                        path,
                        "PR 文件路径包含控制字符",
                        "文件名无法安全展示或跨平台检出",
                        "重命名文件并更新引用。",
                        level="blocker",
                    )
                )
                break
        if change["kind"] == "D":
            continue
        current_mode = mode(repo, scope["head"], path)
        if current_mode == "120000":
            raw = read_blob(repo, scope["head"], path, 8192) or b""
            target = raw.decode("utf-8", errors="replace")
            normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
            if posixpath.isabs(target) or normalized == ".." or normalized.startswith("../"):
                findings.append(
                    finding(
                        "GIT.SYMLINK_ESCAPE",
                        "native-git",
                        path,
                        "PR 引入了逃逸仓库的符号链接",
                        "符号链接目标为 {}".format(target[:200]),
                        "改为仓库内相对路径，或删除该符号链接。",
                        level="blocker",
                    )
                )
            continue
        size = blob_size(repo, scope["head"], path) or 0
        old_path = change.get("old_path") or path
        base_size = blob_size(repo, scope["merge_base"], old_path) or 0
        newly_over_block_limit = change["kind"] in {"A", "C"} or base_size <= block_size
        if size > block_size and newly_over_block_limit:
            findings.append(
                finding(
                    "GIT.LARGE_FILE_BLOCK",
                    "native-git",
                    path,
                    "PR 新版本包含超大 Git Blob",
                    "文件大小 {:.1f} MiB，超过 {:.1f} MiB 阻断阈值".format(size / 1048576, block_size / 1048576),
                    "移出仓库或使用 Git LFS；不能只调整 Workflow 阈值。",
                    level="blocker",
                )
            )
        elif size > review_size:
            findings.append(
                finding(
                    "GIT.LARGE_FILE_REVIEW",
                    "native-git",
                    path,
                    "PR 新版本包含较大文件",
                    "文件大小 {:.1f} MiB".format(size / 1048576),
                    "核对是否应使用 Git LFS；第一版仅提示。",
                    level="advisory",
                )
            )
        data = read_blob(repo, scope["head"], path, maximum)
        if data is None or b"\0" in data[:8192]:
            continue
        if PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS and PurePosixPath(path).name not in TEXT_NAMES:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            base_raw = (
                read_blob(repo, scope["merge_base"], old_path, maximum)
                if change["kind"] not in {"A", "C"}
                else None
            )
            if base_raw is not None:
                try:
                    base_raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            findings.append(
                finding(
                    "ENCODING.INVALID_UTF8",
                    "native-git",
                    path,
                    "PR 文本文件不是合法 UTF-8",
                    "UTF-8 解码失败，字节位置 {}".format(error.start),
                    "使用 UTF-8 重新保存文件，禁止通过替换解码掩盖问题。",
                    level="blocker",
                )
            )
            continue
        if "\r\n" in text:
            findings.append(
                finding(
                    "ENCODING.CRLF",
                    "native-git",
                    path,
                    "PR 文本文件使用 CRLF 换行",
                    "检测到 CRLF；第一版不阻断",
                    "非 Windows 专用文件建议统一为 LF。",
                    level="advisory",
                )
            )
        for line_number, line in enumerate(text.splitlines(), 1):
            if "\ufffd" not in line:
                continue
            if change["kind"] not in {"A", "C"} and line_number not in scope["changed_lines"].get(path, set()):
                continue
            findings.append(
                finding(
                    "ENCODING.REPLACEMENT_CHARACTER",
                    "native-git",
                    path,
                    "PR 文本包含 Unicode 替换字符",
                    "第 {} 行包含 U+FFFD，通常表示内容曾被错误解码或已经发生乱码".format(line_number),
                    "从原始内容恢复正确字符，并使用 UTF-8 重新保存文件。",
                    level="blocker",
                    line=line_number,
                )
            )
            break
        for index, character in enumerate(text):
            if character in "\n\r\t":
                continue
            category = unicodedata.category(character)
            if category == "Cc":
                line_number = _line_for_index(text, index)
                if change["kind"] not in {"A", "C"} and line_number not in scope["changed_lines"].get(path, set()):
                    continue
                findings.append(
                    finding(
                        "ENCODING.CONTROL_CHARACTER",
                        "native-git",
                        path,
                        "PR 文本包含危险控制字符",
                        "第 {} 行包含 U+{:04X}".format(line_number, ord(character)),
                        "删除控制字符并确认文件内容未被混淆。",
                        level="blocker",
                        line=line_number,
                    )
                )
                break
    return findings, _status("native-git", "危险链接、异常路径、编码和大文件", findings)


def scan_syntax_and_workflows(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    maximum = int(policy["git"]["max_text_scan_bytes"])
    for change in scope["changes"]:
        path = change["path"]
        if change["kind"] == "D":
            continue
        data = read_blob(repo, scope["head"], path, maximum)
        if data is None or b"\0" in data[:8192]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".py", ".pyi"}:
            try:
                ast.parse(text, filename=path)
            except SyntaxError as error:
                findings.append(
                    finding(
                        "QUALITY.PYTHON.SYNTAX",
                        "native-syntax",
                        path,
                        "Python 文件存在明确语法错误",
                        str(error.msg),
                        "修复 Python 语法后重新提交。",
                        level="blocker",
                        line=error.lineno,
                    )
                )
        if suffix in {".yaml", ".yml"}:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as error:
                mark = getattr(error, "problem_mark", None)
                findings.append(
                    finding(
                        "QUALITY.YAML.SYNTAX",
                        "native-syntax",
                        path,
                        "YAML 文件存在明确语法错误",
                        "YAML 无法解析",
                        "修复 YAML 语法或重复键后重新提交。",
                        level="blocker",
                        line=(mark.line + 1) if mark is not None else None,
                    )
                )
        if path.startswith(".github/workflows/") and suffix in {".yaml", ".yml"}:
            for line_number, line in enumerate(text.splitlines(), 1):
                if change["kind"] not in {"A", "C"} and line_number not in scope["changed_lines"].get(path, set()):
                    continue
                matched = USES_RE.match(line)
                if not matched:
                    continue
                reference = matched.group(1)
                if reference.startswith("./"):
                    continue
                if reference.startswith("docker://"):
                    if "@sha256:" not in reference:
                        findings.append(
                            finding(
                                "WORKFLOW.DOCKER_REFERENCE_ADVISORY",
                                "workflow",
                                path,
                                "Workflow Docker 引用未固定 digest",
                                "{}；第一版仅提示".format(reference),
                                "建议固定到 sha256 digest。",
                                level="advisory",
                                line=line_number,
                            )
                        )
                    continue
                if not PINNED_USES_RE.fullmatch(reference):
                    mutable_is_advisory = bool(
                        policy.get("advisory", {}).get(
                            "mutable_action_reference", False
                        )
                    )
                    findings.append(
                        finding(
                            "WORKFLOW.MUTABLE_USES",
                            "workflow",
                            path,
                            "Workflow 使用可移动 Action 或 reusable workflow 引用",
                            reference,
                            (
                                "建议固定为组织审核通过的完整 40 位 Commit SHA；当前仅提示。"
                                if mutable_is_advisory
                                else "替换为组织审核通过的完整 40 位 Commit SHA。"
                            ),
                            level="advisory" if mutable_is_advisory else "blocker",
                            line=line_number,
                        )
                    )
    return findings, _status("native-syntax", "Python/YAML 明确语法和 Workflow 固定引用", findings)


def _normalized_license_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").strip()


ROOT_LEGAL_FILES = {
    "COPYING",
    "COPYING.md",
    "COPYING.txt",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "NOTICE",
    "NOTICE.md",
    "NOTICE.txt",
    "THIRD_PARTY_NOTICES.md",
}


def _is_root_legal_file(path: str) -> bool:
    return "/" not in path and PurePosixPath(path).name in ROOT_LEGAL_FILES


def scan_compliance(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    allowed = set(policy["open_source"]["allowed_licenses"])
    forbidden_licenses = {
        str(value)
        for value in policy["open_source"]
        .get("license_admission", {})
        .get("forbidden", [])
    }
    header_lines = int(policy["git"]["source_header_scan_lines"])

    legal_paths = {
        str(change.get("old_path") or change["path"])
        for change in scope["changes"]
        if _is_root_legal_file(str(change.get("old_path") or change["path"]))
    }
    for legal_path in sorted(legal_paths):
        base = read_blob(repo, scope["merge_base"], legal_path, 4 * 1024 * 1024)
        if base is None:
            continue
        current = read_blob(
            repo,
            scope["head"],
            legal_path,
            4 * 1024 * 1024,
        )
        if current is None:
            findings.append(
                finding(
                    "LEGAL.{}_DELETED".format(PurePosixPath(legal_path).name.upper()),
                    "compliance",
                    legal_path,
                    "PR 删除了原 {} 文件".format(PurePosixPath(legal_path).name),
                    "基础分支存在，PR head 不存在",
                    "恢复原文件和完整内容；允许追加，不能删除或重写。",
                    level="blocker",
                )
            )
        elif _normalized_license_text(base) not in _normalized_license_text(current):
            findings.append(
                finding(
                    "LEGAL.{}_REWRITTEN".format(PurePosixPath(legal_path).name.upper()),
                    "compliance",
                    legal_path,
                    "PR 删除或重写了原 {} 内容".format(PurePosixPath(legal_path).name),
                    "PR head 未完整包含基础分支法律文件内容",
                    "恢复原内容；新增声明只能追加并保持适用范围清晰。",
                    level="blocker",
                )
            )
    for change in scope["changes"]:
        path = change["path"]
        if change["kind"] == "D" or not is_source(path, policy):
            continue
        raw = read_blob(repo, scope["head"], path, int(policy["git"]["max_text_scan_bytes"]))
        if raw is None or b"\0" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="replace")
        current_header = _header(text, header_lines)
        license_matches = list(SPDX_RE.finditer(current_header))
        licenses = [match.group(1) for match in license_matches]
        for license_match in license_matches:
            expression = license_match.group(1)
            line_number = _line_for_index(current_header, license_match.start())
            if change["kind"] not in {"A", "C"} and line_number not in scope["changed_lines"].get(path, set()):
                continue
            if expression not in allowed:
                is_forbidden = expression in forbidden_licenses
                findings.append(
                    finding(
                        "LICENSE.UNSUPPORTED_PR_FILE",
                        "compliance",
                        path,
                        (
                            "PR 文件使用禁止准入的许可证"
                            if is_forbidden
                            else "PR 文件许可证需要法务/合规准入审批"
                        ),
                        "SPDX-License-Identifier: {}".format(expression),
                        (
                            "移除或替换禁止准入的代码，并保留原权利人声明。"
                            if is_forbidden
                            else "提交许可证适用范围和兼容性材料；审批完成前阻断合并与发布。"
                        ),
                        level="blocker",
                        line=line_number,
                    )
                )
        if change["kind"] in {"M", "R", "C"}:
            old_path = change.get("old_path") or path
            base_raw = read_blob(repo, scope["merge_base"], old_path, int(policy["git"]["max_text_scan_bytes"]))
            if base_raw is not None:
                base_header = _header(base_raw.decode("utf-8", errors="replace"), header_lines)
                original_lines = [
                    line.strip()
                    for line in base_header.splitlines()
                    if COPYRIGHT_RE.search(line) or SPDX_RE.search(line)
                ]
                for original in original_lines:
                    if original and original not in current_header:
                        findings.append(
                            finding(
                                "COPYRIGHT.ORIGINAL_HEADER_REMOVED",
                                "compliance",
                                path,
                                "PR 删除或替换了原版权/许可证声明",
                                "基础分支文件头声明在 PR head 中不再存在",
                                "恢复原声明；HYGON 声明只能追加，不能替换原权利人。",
                                level="blocker",
                            )
                        )
                        break
        if change["kind"] != "A":
            continue

        has_copyright = bool(COPYRIGHT_RE.search(current_header))
        if HYGON_COPYRIGHT in current_header and not licenses:
            findings.append(
                finding(
                    "COPYRIGHT.NEW_HYGON_SOURCE_SPDX_MISSING",
                    "compliance",
                    path,
                    "新增 HYGON 源码文件头缺少 SPDX",
                    "文件头包含 HYGON Copyright，但未检测到 SPDX-License-Identifier",
                    "根据仓库实际许可证补充 SPDX；不得凭名称机械选择许可证。",
                    level="blocker",
                )
            )
            continue
        if not has_copyright or not licenses:
            findings.append(
                finding(
                    "COPYRIGHT.NEW_SOURCE_HEADER_REVIEW",
                    "compliance",
                    path,
                    "新增源码的版权和许可证归属待复核",
                    "文件头未同时检测到 Copyright 和 SPDX；PR 门禁不推断原创、上游或第三方归属",
                    "原创源码补充与仓库许可证一致的 HYGON 文件头；上游或第三方源码保留原声明并登记来源。定期全仓扫描将继续复核。",
                    level="advisory",
                )
            )
    return findings, _status(
        "compliance",
        "根目录法律文件、已有版权/SPDX 防删除及新增源码高置信增量检查",
        findings,
    )


def run_native_checks(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    for scanner in (scan_identity, scan_git_and_encoding, scan_syntax_and_workflows, scan_compliance):
        current, status = scanner(repo, scope, policy)
        findings.extend(current)
        statuses.append(status)
    return findings, statuses
