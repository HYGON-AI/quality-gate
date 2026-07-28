# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Block legacy DCU tokens and HCU-visible AMD/XGMI wording added by a PR."""

import ast
import fnmatch
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from hygon_quality_security.models import finding, scanner_status

from .git_scope import read_blob


MAX_SNIPPET_LENGTH = 180
WORD_RE = re.compile(r"[A-Za-z0-9]+")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
CAMEL_BOUNDARY_RE = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)
CONDITION_LINE_RE = re.compile(
    r"^\s*(?:(?:if|elif|else\s+if|while)\b|#\s*(?:if|ifdef|ifndef|elif)\b)",
    re.IGNORECASE,
)
VISIBLE_TEXT_RE = re.compile(
    r"(?:"
    r"\b(?:echo|printf|print|raise|throw|description|help|message|status)\b"
    r"|(?:logger|logging)\s*\."
    r"|\b(?:fprintf|fputs|puts)\s*\("
    r"|\b(?:LOG(?:_[A-Z0-9_]+)?|SPDLOG_[A-Z0-9_]+|"
    r"TORCH_CHECK|TORCH_WARN|WARN|ERROR)\s*\("
    r"|\bstd::(?:cerr|cout|clog)\b"
    r")",
    re.IGNORECASE,
)
OUTPUT_TARGET_TOKENS = {
    "description",
    "detail",
    "error",
    "help",
    "message",
    "msg",
    "reason",
    "status",
    "summary",
    "warning",
}
VISIBLE_METHODS = {
    "critical",
    "debug",
    "error",
    "exception",
    "info",
    "log",
    "log_error_on_rank0",
    "log_info_on_rank0",
    "log_warning_on_rank0",
    "print",
    "skip",
    "warn",
    "warning",
}
CLI_KEYWORDS = {"description", "epilog", "help", "reason"}
TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".cu",
    ".cuh",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".pyi",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {"BUILD", "CMakeLists.txt", "Dockerfile", "Makefile", "WORKSPACE"}


def _text(path: str, data: Optional[bytes]) -> Optional[str]:
    if data is None or b"\0" in data[:8192]:
        return None
    pure = PurePosixPath(path)
    if pure.suffix.lower() not in TEXT_SUFFIXES and pure.name not in TEXT_NAMES:
        return None
    return data.decode("utf-8", errors="replace")


def _snippet(value: str) -> str:
    result = " ".join(value.split())
    if len(result) > MAX_SNIPPET_LENGTH:
        result = result[: MAX_SNIPPET_LENGTH - 3] + "..."
    return result


def _matches_path(path: str, patterns: Sequence[str]) -> bool:
    for raw in patterns:
        pattern = str(raw)
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def _as_strings(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("{} must be a list of strings".format(label))
    return list(value)


def _merge_strings(*values: Sequence[str]) -> List[str]:
    result: List[str] = []
    for group in values:
        for value in group:
            if value not in result:
                result.append(value)
    return result


def _token_spans(value: str) -> Iterable[Tuple[str, int, int]]:
    for word in WORD_RE.finditer(value):
        raw = word.group(0)
        start = word.start()
        cursor = 0
        for part in CAMEL_BOUNDARY_RE.split(raw):
            part_start = raw.find(part, cursor)
            part_end = part_start + len(part)
            yield part, start + part_start, start + part_end
            cursor = part_end


def _candidate_token_spans(
    value: str, terms: Sequence[str]
) -> Iterable[Tuple[str, int, int]]:
    seen: Set[Tuple[int, int]] = set()
    for token, start, end in _token_spans(value):
        seen.add((start, end))
        yield token, start, end

    uppercase_terms = {term.upper() for term in terms if term}
    for word in WORD_RE.finditer(value):
        raw = word.group(0)
        for term in uppercase_terms:
            cursor = 0
            while True:
                index = raw.find(term, cursor)
                if index < 0:
                    break
                end = index + len(term)
                previous = raw[index - 1] if index else ""
                if (not previous or not previous.isupper()) and (
                    word.start() + index,
                    word.start() + end,
                ) not in seen:
                    seen.add((word.start() + index, word.start() + end))
                    yield term, word.start() + index, word.start() + end
                cursor = index + 1


def _covered(start: int, end: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def _containing_identifier(value: str, start: int, end: int) -> str:
    for match in IDENTIFIER_RE.finditer(value):
        if match.start() <= start and end <= match.end():
            return match.group(0)
    return ""


def _term_matches(
    value: str,
    terms: Sequence[str],
    *,
    allowed_url_patterns: Sequence[re.Pattern] = (),
    allowed_identifiers: Sequence[str] = (),
    allowed_identifier_patterns: Sequence[re.Pattern] = (),
    allowed_patterns: Sequence[re.Pattern] = (),
) -> List[Tuple[str, int, int]]:
    expected = {term.lower() for term in terms}
    allowed_url_spans = [
        (match.start(), match.end())
        for match in URL_RE.finditer(value)
        if any(pattern.fullmatch(match.group(0)) for pattern in allowed_url_patterns)
    ]
    allowed_spans: List[Tuple[int, int]] = []
    for pattern in allowed_patterns:
        allowed_spans.extend(
            (match.start(), match.end()) for match in pattern.finditer(value)
        )
    allowed_names = {name.lower() for name in allowed_identifiers}
    result = []
    for token, start, end in _candidate_token_spans(value, terms):
        if token.lower() not in expected:
            continue
        if _covered(start, end, allowed_url_spans):
            continue
        if _covered(start, end, allowed_spans):
            continue
        identifier = _containing_identifier(value, start, end)
        if identifier and identifier.lower() in allowed_names:
            continue
        if identifier and any(
            pattern.fullmatch(identifier) for pattern in allowed_identifier_patterns
        ):
            continue
        result.append((token, start, end))
    return result


def _compile_patterns(
    values: Sequence[str], label: str, flags: int = re.IGNORECASE
) -> List[re.Pattern]:
    result = []
    for value in values:
        try:
            result.append(re.compile(value, flags))
        except re.error as error:
            raise ValueError("{} contains invalid regex {!r}: {}".format(label, value, error))
    return result


def _node_lines(node: ast.AST) -> range:
    start = int(getattr(node, "lineno", 0) or 0)
    end = int(getattr(node, "end_lineno", start) or start)
    return range(start, end + 1)


def _is_added(node: ast.AST, added_lines: Set[int]) -> bool:
    return any(number in added_lines for number in _node_lines(node))


def _string_nodes(node: ast.AST) -> Iterable[ast.Constant]:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child


def _call_name(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def _target_names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _target_names(item)


def _has_hcu_token(value: str) -> bool:
    return any(token.lower() == "hcu" for token, _, _ in _token_spans(value))


def _has_output_token(value: str) -> bool:
    return any(
        token.lower() in OUTPUT_TARGET_TOKENS for token, _, _ in _token_spans(value)
    )


def _node_mentions_hcu(node: ast.AST, markers: Sequence[str]) -> bool:
    marker_names = {value.lower() for value in markers}
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if child.id.lower() in marker_names or _has_hcu_token(child.id):
                return True
        elif isinstance(child, ast.Attribute):
            if child.attr.lower() in marker_names or _has_hcu_token(child.attr):
                return True
        elif (
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and _has_hcu_token(child.value)
        ):
            return True
    return False


def _hcu_truth_states(
    node: ast.AST, markers: Sequence[str]
) -> Tuple[Set[bool], Set[bool], bool]:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        true_states, false_states, mentions_hcu = _hcu_truth_states(
            node.operand, markers
        )
        return false_states, true_states, mentions_hcu
    if isinstance(node, ast.BoolOp):
        values = [_hcu_truth_states(item, markers) for item in node.values]
        mentions_hcu = any(item[2] for item in values)
        if isinstance(node.op, ast.And):
            true_states = set.intersection(*(item[0] for item in values))
            false_states = set.union(*(item[1] for item in values))
            return true_states, false_states, mentions_hcu
        if isinstance(node.op, ast.Or):
            true_states = set.union(*(item[0] for item in values))
            false_states = set.intersection(*(item[1] for item in values))
            return true_states, false_states, mentions_hcu
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        true_states, false_states, mentions_hcu = _hcu_truth_states(
            node.left, markers
        )
        right = node.comparators[0]
        if mentions_hcu and isinstance(right, ast.Constant) and isinstance(
            right.value, bool
        ):
            if isinstance(node.ops[0], (ast.Eq, ast.Is)):
                if right.value:
                    return true_states, false_states, True
                return false_states, true_states, True
            if isinstance(node.ops[0], (ast.NotEq, ast.IsNot)):
                if right.value:
                    return false_states, true_states, True
                return true_states, false_states, True
        comparison_mentions_hcu = _node_mentions_hcu(
            node.left, markers
        ) or _node_mentions_hcu(right, markers)
        if comparison_mentions_hcu:
            if isinstance(node.ops[0], (ast.Eq, ast.Is, ast.In)):
                return {True}, {False}, True
            if isinstance(node.ops[0], (ast.NotEq, ast.IsNot, ast.NotIn)):
                return {False}, {True}, True
    if _node_mentions_hcu(node, markers):
        return {True}, {False}, True
    return {False, True}, {False, True}, False


class _PythonRuntimeVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path_owned: bool,
        added_lines: Set[int],
        markers: Sequence[str],
        runtime_terms: Sequence[str],
        allowed_patterns: Sequence[re.Pattern],
    ) -> None:
        self.context = path_owned
        self.added_lines = added_lines
        self.markers = markers
        self.runtime_terms = runtime_terms
        self.allowed_patterns = allowed_patterns
        self.matches: List[Tuple[int, str, str, str]] = []
        self.seen: Set[Tuple[int, str, str]] = set()

    def _visit_in_context(self, nodes: Sequence[ast.stmt], context: bool) -> None:
        previous = self.context
        self.context = context
        for node in nodes:
            self.visit(node)
        self.context = previous

    def _record_strings(self, node: ast.AST, sink: str) -> None:
        if not self.context:
            return
        for string in _string_nodes(node):
            if not _is_added(string, self.added_lines):
                continue
            for term, _, _ in _term_matches(
                string.value,
                self.runtime_terms,
                allowed_patterns=self.allowed_patterns,
            ):
                line = int(getattr(string, "lineno", 1) or 1)
                key = (line, term.lower(), string.value)
                if key in self.seen:
                    continue
                self.seen.add(key)
                self.matches.append((line, sink, term, string.value))

    def visit_If(self, node: ast.If) -> None:
        true_states, false_states, mentions_hcu = _hcu_truth_states(
            node.test, self.markers
        )
        if mentions_hcu:
            self._visit_in_context(node.body, True in true_states)
            self._visit_in_context(node.orelse, True in false_states)
        else:
            self._visit_in_context(node.body, self.context)
            self._visit_in_context(node.orelse, self.context)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_in_context(node.body, self.context or _has_hcu_token(node.name))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_in_context(node.body, self.context or _has_hcu_token(node.name))

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node).lower()
        if name in VISIBLE_METHODS:
            self._record_strings(node, "{}()".format(name))
        elif name in {"argumentparser", "add_argument"}:
            for keyword in node.keywords:
                if keyword.arg in CLI_KEYWORDS:
                    self._record_strings(keyword.value, "{}({}=)".format(name, keyword.arg))
        else:
            for keyword in node.keywords:
                if keyword.arg and _has_output_token(keyword.arg):
                    self._record_strings(
                        keyword.value, "{}({}=)".format(name or "call", keyword.arg)
                    )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            self._record_strings(node.exc, "raise")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(
            _has_output_token(name)
            for target in node.targets
            for name in _target_names(target)
        ):
            self._record_strings(node.value, "visible message assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and any(
            _has_output_token(name) for name in _target_names(node.target)
        ):
            self._record_strings(node.value, "visible message assignment")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _has_output_token(key.value)
            ):
                self._record_strings(value, "visible status field")
        self.generic_visit(node)


def _python_runtime_matches(
    text: str,
    *,
    path_owned: bool,
    added_lines: Set[int],
    markers: Sequence[str],
    runtime_terms: Sequence[str],
    allowed_patterns: Sequence[re.Pattern],
) -> List[Tuple[int, str, str, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    visitor = _PythonRuntimeVisitor(
        path_owned=path_owned,
        added_lines=added_lines,
        markers=markers,
        runtime_terms=runtime_terms,
        allowed_patterns=allowed_patterns,
    )
    visitor.visit(tree)
    return visitor.matches


def _text_hcu_branches(
    value: str, markers: Sequence[str]
) -> Optional[Tuple[bool, bool]]:
    lowered = value.lower()
    marker_values = [marker.lower() for marker in markers]
    if not any(marker in lowered for marker in marker_values) and not _has_hcu_token(
        value
    ):
        return None

    negated = bool(
        re.search(r"(?:!\s*|\bnot\s+)(?:[a-z_][a-z0-9_.]*hcu)", lowered)
        or re.search(r"!=\s*['\"]?hcu\b", lowered)
        or re.search(r"\bnot\s+in\b.*['\"]hcu['\"]", lowered)
    )
    if "||" in value:
        return (True, True) if negated else (True, False)
    if "&&" in value:
        return (False, True) if negated else (True, True)
    return (False, True) if negated else (True, False)


def _near_hcu_condition(
    lines: Sequence[str], index: int, markers: Sequence[str]
) -> Optional[bool]:
    for previous in range(index, max(-1, index - 20), -1):
        value = lines[previous]
        if value.lstrip().startswith(("//", "/*", "*")):
            continue
        if CONDITION_LINE_RE.search(value):
            branches = _text_hcu_branches(value, markers)
            if branches is not None:
                return branches[0]
        if previous != index and value.strip().lower() in {
            "else",
            "else:",
            "fi",
            "}",
        }:
            break
    return None


def _without_c_comments(lines: Sequence[str]) -> List[str]:
    result: List[str] = []
    in_block = False
    for line in lines:
        visible: List[str] = []
        quote = ""
        escaped = False
        index = 0
        while index < len(line):
            pair = line[index : index + 2]
            char = line[index]
            if in_block:
                if pair == "*/":
                    in_block = False
                    index += 2
                else:
                    index += 1
                continue
            if quote:
                visible.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                index += 1
                continue
            if pair == "//":
                break
            if pair == "/*":
                in_block = True
                index += 2
                continue
            if char in {"'", '"'}:
                quote = char
            visible.append(char)
            index += 1
        result.append("".join(visible))
    return result


def _shell_hcu_contexts(
    lines: Sequence[str], path_owned: bool, markers: Sequence[str]
) -> List[bool]:
    contexts: List[bool] = []
    stack: List[Dict[str, bool]] = []
    current_possible = True
    current_owned = path_owned
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if re.match(r"^if\b", lowered):
            branches = _text_hcu_branches(stripped, markers)
            then_possible = (
                current_possible
                if branches is None
                else current_possible and branches[0]
            )
            remaining_possible = (
                current_possible
                if branches is None
                else current_possible and branches[1]
            )
            then_owned = current_owned or (branches is not None and then_possible)
            remaining_owned = current_owned or (
                branches is not None and remaining_possible
            )
            stack.append(
                {
                    "parent_possible": current_possible,
                    "parent_owned": current_owned,
                    "remaining_possible": remaining_possible,
                    "remaining_owned": remaining_owned,
                }
            )
            current_possible = then_possible
            current_owned = then_owned
        elif re.match(r"^elif\b", lowered) and stack:
            branches = _text_hcu_branches(stripped, markers)
            remaining_possible = stack[-1]["remaining_possible"]
            remaining_owned = stack[-1]["remaining_owned"]
            current_possible = (
                remaining_possible
                if branches is None
                else remaining_possible and branches[0]
            )
            current_owned = remaining_owned or (
                branches is not None and current_possible
            )
            stack[-1]["remaining_possible"] = (
                remaining_possible
                if branches is None
                else remaining_possible and branches[1]
            )
            stack[-1]["remaining_owned"] = remaining_owned or (
                branches is not None and stack[-1]["remaining_possible"]
            )
        elif re.match(r"^else\b", lowered) and stack:
            current_possible = stack[-1]["remaining_possible"]
            current_owned = stack[-1]["remaining_owned"]

        contexts.append(current_possible and current_owned)

        if re.match(r"^fi\b", lowered) and stack:
            frame = stack.pop()
            current_possible = frame["parent_possible"]
            current_owned = frame["parent_owned"]
    return contexts


def _output_windows(lines: Sequence[str]) -> Iterable[Tuple[int, int]]:
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if (
            not stripped
            or stripped.startswith(("#", "//", "/*", "*"))
            or not VISIBLE_TEXT_RE.search(line)
        ):
            index += 1
            continue

        end = index
        balance = line.count("(") - line.count(")")
        stream_output = bool(
            re.search(r"\bstd::(?:cerr|cout|clog)\b", line, re.IGNORECASE)
        )
        while (
            (balance > 0 or (stream_output and ";" not in lines[end]))
            and end + 1 < len(lines)
            and end - index < 50
        ):
            end += 1
            balance += lines[end].count("(") - lines[end].count(")")
        yield index, end
        index = end + 1


def _text_runtime_matches(
    path: str,
    lines: Sequence[str],
    *,
    path_owned: bool,
    added_lines: Set[int],
    markers: Sequence[str],
    runtime_terms: Sequence[str],
    allowed_patterns: Sequence[re.Pattern],
) -> List[Tuple[int, str, str, str]]:
    result = []
    suffix = PurePosixPath(path).suffix.lower()
    shell_contexts = (
        _shell_hcu_contexts(lines, path_owned, markers)
        if suffix in {".bash", ".ksh", ".sh", ".zsh"}
        else None
    )
    condition_lines = lines if shell_contexts is not None else _without_c_comments(lines)
    for start, end in _output_windows(lines):
        if shell_contexts is not None:
            hcu_context = shell_contexts[start]
        else:
            nearby_context = _near_hcu_condition(condition_lines, start, markers)
            hcu_context = path_owned if nearby_context is None else nearby_context
        if not hcu_context:
            continue
        for index in range(start, end + 1):
            number = index + 1
            if number not in added_lines:
                continue
            line = lines[index]
            stripped = line.lstrip()
            if not stripped or stripped.startswith(("#", "//", "/*", "*")):
                continue
            for term, _, _ in _term_matches(
                line,
                runtime_terms,
                allowed_patterns=allowed_patterns,
            ):
                result.append((number, "visible output", term, line))
    return result


def _added_lines(change: Dict[str, Any], text: str, scope: Dict[str, Any]) -> Set[int]:
    if change["kind"] in {"A", "C"}:
        return set(range(1, len(text.splitlines()) + 1))
    return set(scope["changed_lines"].get(change["path"], set()))


def scan_sensitive_diff(
    repo: Path,
    scope: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile = policy.get("profile", {})
    profile_checks = profile.get("checks", {})
    if not (
        profile_checks.get("sensitive_diff") is True
        or profile_checks.get("hcu_runtime_wording") is True
    ):
        return [], scanner_status(
            "sensitive-diff",
            "disabled",
            detail="Sensitive platform wording check is disabled for this repository.",
        )

    config = policy.get("sensitive_diff") or {}
    if config.get("enabled") is not True:
        raise ValueError("sensitive_diff policy must be enabled")
    profile_config = profile.get("sensitive_diff") or {}
    legacy = config.get("legacy_dcu") or {}
    profile_legacy = profile_config.get("legacy_dcu") or {}
    runtime = config.get("hcu_runtime") or {}
    profile_runtime = profile_config.get("hcu_runtime") or {}

    legacy_terms = _as_strings(legacy.get("terms"), "sensitive_diff.legacy_dcu.terms")
    runtime_terms = _as_strings(runtime.get("terms"), "sensitive_diff.hcu_runtime.terms")
    if not legacy_terms or not runtime_terms:
        raise ValueError("sensitive_diff legacy and runtime terms must be configured")

    legacy_excluded = _merge_strings(
        _as_strings(legacy.get("excluded_paths"), "legacy_dcu.excluded_paths"),
        _as_strings(profile_legacy.get("excluded_paths"), "profile legacy_dcu.excluded_paths"),
        _as_strings(profile.get("third_party_paths"), "profile.third_party_paths"),
        _as_strings(profile.get("generated_paths"), "profile.generated_paths"),
    )
    allowed_identifiers = _merge_strings(
        _as_strings(legacy.get("allowed_identifiers"), "legacy_dcu.allowed_identifiers"),
        _as_strings(
            profile_legacy.get("allowed_identifiers"),
            "profile legacy_dcu.allowed_identifiers",
        ),
    )
    allowed_identifier_patterns = _compile_patterns(
        _merge_strings(
            _as_strings(
                legacy.get("allowed_identifier_patterns"),
                "legacy_dcu.allowed_identifier_patterns",
            ),
            _as_strings(
                profile_legacy.get("allowed_identifier_patterns"),
                "profile legacy_dcu.allowed_identifier_patterns",
            ),
        ),
        "legacy_dcu.allowed_identifier_patterns",
        flags=0,
    )
    allowed_url_patterns = _compile_patterns(
        _merge_strings(
            _as_strings(
                legacy.get("allowed_url_patterns"),
                "legacy_dcu.allowed_url_patterns",
            ),
            _as_strings(
                profile_legacy.get("allowed_url_patterns"),
                "profile legacy_dcu.allowed_url_patterns",
            ),
        ),
        "legacy_dcu.allowed_url_patterns",
    )

    hcu_owned_paths = _merge_strings(
        _as_strings(runtime.get("hcu_owned_paths"), "hcu_runtime.hcu_owned_paths"),
        _as_strings(
            profile_runtime.get("hcu_owned_paths"),
            "profile hcu_runtime.hcu_owned_paths",
        ),
    )
    runtime_excluded = _merge_strings(
        _as_strings(runtime.get("excluded_paths"), "hcu_runtime.excluded_paths"),
        _as_strings(
            profile_runtime.get("excluded_paths"),
            "profile hcu_runtime.excluded_paths",
        ),
        _as_strings(profile.get("third_party_paths"), "profile.third_party_paths"),
        _as_strings(profile.get("generated_paths"), "profile.generated_paths"),
    )
    markers = _merge_strings(
        _as_strings(runtime.get("hcu_markers"), "hcu_runtime.hcu_markers"),
        _as_strings(profile_runtime.get("hcu_markers"), "profile hcu_runtime.hcu_markers"),
    )
    allowed_runtime_patterns = _compile_patterns(
        _merge_strings(
            _as_strings(
                runtime.get("allowed_output_patterns"),
                "hcu_runtime.allowed_output_patterns",
            ),
            _as_strings(
                profile_runtime.get("allowed_output_patterns"),
                "profile hcu_runtime.allowed_output_patterns",
            ),
        ),
        "hcu_runtime.allowed_output_patterns",
    )

    maximum = int(policy["git"]["max_text_scan_bytes"])
    findings: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, int, str]] = set()

    def add_finding(
        rule_id: str,
        path: str,
        line: int,
        title: str,
        term: str,
        evidence: str,
        remediation: str,
    ) -> None:
        key = (rule_id, path, line, term.lower())
        if key in seen:
            return
        seen.add(key)
        findings.append(
            finding(
                rule_id,
                "sensitive-diff",
                path,
                title,
                evidence,
                remediation,
                level="blocker",
                line=line,
            )
        )

    for change in scope["changes"]:
        if change["kind"] == "D":
            continue
        path = change["path"]
        legacy_path_excluded = _matches_path(path, legacy_excluded)
        if not legacy_path_excluded:
            for term, _, _ in _term_matches(
                path,
                legacy_terms,
                allowed_identifiers=allowed_identifiers,
                allowed_identifier_patterns=allowed_identifier_patterns,
            ):
                add_finding(
                    "SENSITIVE_DIFF.LEGACY_DCU_PATH",
                    path,
                    1,
                    "Changed destination path contains a legacy DCU token",
                    term,
                    "Destination path contains token {!r}: {!r}.".format(term, path),
                    "Rename repository-owned HCU paths; allowlist only "
                    "verified external contracts.",
                )

        text = _text(path, read_blob(repo, scope["head"], path, maximum))
        if text is None:
            continue
        added_lines = _added_lines(change, text, scope)
        lines = text.splitlines()

        if not legacy_path_excluded:
            for number in sorted(added_lines):
                if number < 1 or number > len(lines):
                    continue
                line = lines[number - 1]
                for term, _, _ in _term_matches(
                    line,
                    legacy_terms,
                    allowed_url_patterns=allowed_url_patterns,
                    allowed_identifiers=allowed_identifiers,
                    allowed_identifier_patterns=allowed_identifier_patterns,
                ):
                    add_finding(
                        "SENSITIVE_DIFF.LEGACY_DCU_CONTENT",
                        path,
                        number,
                        "Added content contains a legacy DCU token",
                        term,
                        "Line {} contains token {!r}: {}.".format(
                            number, term, _snippet(line)
                        ),
                        "Rename repository-owned HCU identifiers and visible wording; "
                        "allowlist only verified dependency, API, ABI, or macro contracts.",
                    )

        if _matches_path(path, runtime_excluded):
            continue
        path_owned = _matches_path(path, hcu_owned_paths)
        if PurePosixPath(path).suffix.lower() == ".py":
            runtime_matches = _python_runtime_matches(
                text,
                path_owned=path_owned,
                added_lines=added_lines,
                markers=markers,
                runtime_terms=runtime_terms,
                allowed_patterns=allowed_runtime_patterns,
            )
        else:
            runtime_matches = _text_runtime_matches(
                path,
                lines,
                path_owned=path_owned,
                added_lines=added_lines,
                markers=markers,
                runtime_terms=runtime_terms,
                allowed_patterns=allowed_runtime_patterns,
            )
        for number, sink, term, value in runtime_matches:
            add_finding(
                "SENSITIVE_DIFF.HCU_RUNTIME_WORDING",
                path,
                number,
                "HCU user-visible output contains AMD/XGMI wording",
                term,
                "{} contains token {!r}: {}.".format(sink, term, _snippet(value)),
                "Use HCU device wording for hardware and HSL for HCU links; "
                "keep ROCm/HIP wording when it describes the software stack.",
            )

    return findings, scanner_status(
        "sensitive-diff",
        "findings" if findings else "passed",
        detail=(
            "Added lines and new files only. DCU uses token matching; AMD/XGMI "
            "requires HCU ownership and a user-visible output sink."
        ),
        finding_count=len(findings),
    )
