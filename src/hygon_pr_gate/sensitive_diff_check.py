# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Advise on legacy DCU tokens and visible AMD/XGMI wording added by a PR."""

import ast
import fnmatch
import json
import string
import itertools
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from hygon_quality_security.models import finding, scanner_status

from .git_scope import read_blob, blob_size, read_blob_prefix
from .artifacts import compiled_format


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
    if data is None:
        raise ValueError("{}：文件无法读取或超过内容检查上限，敏感字段检查未完成".format(path))
    if data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")):
        return None
    if b"\0" in data:
        raise ValueError("{}：二进制内容无法完成敏感字段检查".format(path))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("{}：内容不是有效 UTF-8，敏感字段检查未完成".format(path)) from error
    if path.endswith(".ipynb"):
        try:
            json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("{}：第 {} 行第 {} 列 Notebook JSON 解析失败：{}".format(path, error.lineno, error.colno, error.msg)) from error
        # Mask image values only, preserving original line numbers.
        spans = []
        for match in re.finditer(r'"image/[^"\\]*"\s*:\s*', text):
            _, length = json.JSONDecoder().raw_decode(text[match.end():])
            spans.append((match.end(), match.end() + length))
        for start, end in reversed(spans):
            text = text[:start] + "".join("\n" if c == "\n" else " " for c in text[start:end]) + text[end:]
    return text


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
        # Camel splitting turns complete mixed-case words (AmD, XgMi) into
        # unrelated pieces. Recover only a whole word, never a substring.
        span = (word.start(), word.end())
        if raw.upper() in uppercase_terms and span not in seen:
            seen.add(span)
            yield raw, word.start(), word.end()
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
    substring: bool = False,
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
    candidates = (
        ((m.group(), m.start(), m.end()) for m in re.finditer("|".join(re.escape(t) for t in terms), value, re.IGNORECASE))
        if substring else _candidate_token_spans(value, terms)
    )
    for token, start, end in candidates:
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


def _node_mentions_markers(
    node: ast.AST, markers: Sequence[str], token: str = ""
) -> bool:
    marker_names = {value.lower() for value in markers}
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if child.id.lower() in marker_names or (
                token and any(
                    part.lower() == token
                    for part, _, _ in _token_spans(child.id)
                )
            ):
                return True
        elif isinstance(child, ast.Attribute):
            if child.attr.lower() in marker_names or (
                token and any(
                    part.lower() == token
                    for part, _, _ in _token_spans(child.attr)
                )
            ):
                return True
        elif (
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and (
                child.value.lower() in marker_names
                or (
                    token
                    and any(
                        part.lower() == token
                        for part, _, _ in _token_spans(child.value)
                    )
                )
            )
        ):
            return True
    return False


def _marker_truth_states(
    node: ast.AST, markers: Sequence[str], token: str = ""
) -> Tuple[Set[bool], Set[bool], bool]:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        true_states, false_states, mentions_marker = _marker_truth_states(
            node.operand, markers, token
        )
        return false_states, true_states, mentions_marker
    if isinstance(node, ast.BoolOp):
        values = [_marker_truth_states(item, markers, token) for item in node.values]
        mentions_marker = any(item[2] for item in values)
        if isinstance(node.op, ast.And):
            true_states = set.intersection(*(item[0] for item in values))
            false_states = set.union(*(item[1] for item in values))
            return true_states, false_states, mentions_marker
        if isinstance(node.op, ast.Or):
            true_states = set.union(*(item[0] for item in values))
            false_states = set.intersection(*(item[1] for item in values))
            return true_states, false_states, mentions_marker
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        true_states, false_states, mentions_marker = _marker_truth_states(
            node.left, markers, token
        )
        right = node.comparators[0]
        if mentions_marker and isinstance(right, ast.Constant) and isinstance(
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
        comparison_mentions_marker = _node_mentions_markers(
            node.left, markers, token
        ) or _node_mentions_markers(right, markers, token)
        if comparison_mentions_marker:
            if isinstance(node.ops[0], (ast.Eq, ast.Is, ast.In)):
                return {True}, {False}, True
            if isinstance(node.ops[0], (ast.NotEq, ast.IsNot, ast.NotIn)):
                return {False}, {True}, True
    if _node_mentions_markers(node, markers, token):
        return {True}, {False}, True
    return {False, True}, {False, True}, False


def _hcu_truth_states(
    node: ast.AST, markers: Sequence[str]
) -> Tuple[Set[bool], Set[bool], bool]:
    return _marker_truth_states(node, markers, "hcu")


class _PythonRuntimeVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path_owned: bool,
        source_text: str,
        added_lines: Set[int],
        markers: Sequence[str],
        non_hcu_markers: Sequence[str],
        runtime_terms: Sequence[str],
        allowed_patterns: Sequence[re.Pattern],
    ) -> None:
        self.values = {}
        self.context = path_owned
        self.source_text = source_text
        self.added_lines = added_lines
        self.markers = markers
        self.non_hcu_markers = non_hcu_markers
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

    def _values(self, node, depth=0):
        """Evaluate a bounded subset of expressions without running target code."""
        if depth > 20:
            return []
        location = frozenset({getattr(node, 'lineno', 1)})
        if isinstance(node, ast.Constant):
            return [(node.value, location)]
        if isinstance(node, ast.Name):
            return self.values.get(node.id, [])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            result = []
            for left, ls in self._values(node.left, depth + 1):
                for right, rs in self._values(node.right, depth + 1):
                    if type(left) == type(right) and isinstance(left, (str, int, float)):
                        result.append((left + right, ls | rs))
                        if len(result) > 64:
                            return []
            return result
        if isinstance(node, ast.JoinedStr):
            result = [('', frozenset())]
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    if part.format_spec is not None:
                        values = [("\ufffc", location)]
                    else:
                        values = [(repr(v) if part.conversion == 114 else ascii(v) if part.conversion == 97 else str(v), ls)
                              for v, ls in self._values(part.value, depth + 1)] or [("\ufffc", location)]
                else:
                    values = self._values(part, depth + 1)
                result = [(a + str(b), la | lb) for a, la in result for b, lb in values]
                if len(result) > 64:
                    return []
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format':
            templates = self._values(node.func.value, depth + 1)
            arguments = [self._values(arg, depth + 1) or [("\ufffc", location)] for arg in node.args]
            keywords = {k.arg: self._values(k.value, depth + 1) or [("\ufffc", location)] for k in node.keywords if k.arg}
            results = []
            for template, source in templates:
                if not isinstance(template, str):
                    continue
                for combo in itertools.islice(itertools.product(*(arguments + list(keywords.values()))), 64):
                    positional = combo[:len(arguments)]
                    named = dict(zip(keywords, combo[len(arguments):]))
                    result, origins, auto = '', source, 0
                    try:
                        for literal, field, spec, conversion in string.Formatter().parse(template):
                            result += literal
                            if field is None:
                                continue
                            if field == '':
                                field, auto = str(auto), auto + 1
                            value, origin = positional[int(field)] if field.isdigit() else named.get(field, ("\ufffc", location))
                            origins |= origin
                            if spec or value == "\ufffc":
                                result += "\ufffc"
                            else:
                                result += repr(value) if conversion == 'r' else ascii(value) if conversion == 'a' else str(value)
                        results.append((result, origins))
                    except (ValueError, IndexError):
                        continue
            return results
        # Arbitrary function calls are not their arguments' output values.
        return []

    def _record_strings(self, node: ast.AST, sink: str, arguments: bool = False) -> None:
        expressions = list(node.args) if arguments and isinstance(node, ast.Call) else [node]
        if isinstance(node, ast.Call) and _call_name(node).lower() == 'print':
            expressions.extend(k.value for k in node.keywords if k.arg in {'sep', 'end'})
        for expression in expressions:
            for value, origins in self._values(expression):
                if not isinstance(value, str):
                    continue
                # Direct multiline literals retain their per-line incremental scope.
                for offset, part in enumerate(value.splitlines() or [value]):
                    if isinstance(expression, ast.Constant):
                        relevant = {min(expression.lineno + offset, getattr(expression, "end_lineno", expression.lineno))}
                    else:
                        relevant = set(origins) | set(range(expression.lineno, getattr(expression, 'end_lineno', expression.lineno) + 1))
                    changed = relevant & self.added_lines
                    if not changed:
                        continue
                    line = min(changed)
                    for term, _, _ in _term_matches(part, self.runtime_terms,
                            allowed_patterns=self.allowed_patterns, substring=False):
                        key = (line, term.lower(), part)
                        if key not in self.seen:
                            self.seen.add(key)
                            self.matches.append((line, sink, term, part))

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        before = dict(self.values)
        for statement in node.body:
            self.visit(statement)
        positive = dict(self.values)
        self.values = dict(before)
        for statement in node.orelse:
            self.visit(statement)
        negative = self.values
        self.values = {key: positive.get(key, []) + negative.get(key, [])
                       for key in positive.keys() | negative.keys()}

    def visit_For(self, node):
        self.visit(node.iter)
        if isinstance(node.iter, (ast.List, ast.Tuple, ast.Set)) and not node.iter.elts:
            for statement in node.orelse:
                self.visit(statement)
            return
        before = dict(self.values)
        for name in _target_names(node.target):
            self.values.pop(name, None)
        for statement in node.body:
            self.visit(statement)
        self.values = {key: before.get(key, []) + self.values.get(key, [])
                       for key in before.keys() | self.values.keys()}
        for statement in node.orelse:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.visit(node.test)
        before = dict(self.values)
        if not (isinstance(node.test, ast.Constant) and not node.test.value):
            for statement in node.body:
                self.visit(statement)
        self.values = {key: before.get(key, []) + self.values.get(key, [])
                       for key in before.keys() | self.values.keys()}
        for statement in node.orelse:
            self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous = self.values
        self.values = dict(previous)
        for statement in node.body:
            self.visit(statement)
        self.values = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.values
        self.values = dict(previous)
        # Local assignments and parameters shadow outer names, even before assignment.
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                self.values.pop(child.id, None)
            if isinstance(child, ast.arg):
                self.values.pop(child.arg, None)
        for statement in node.body:
            self.visit(statement)
        self.values = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node).lower()
        if name in VISIBLE_METHODS:
            self._record_strings(node, '{}()'.format(name), arguments=True)
        elif name in {'argumentparser', 'add_argument'}:
            for keyword in node.keywords:
                if keyword.arg in CLI_KEYWORDS:
                    self._record_strings(keyword.value, '{}({}=)'.format(name, keyword.arg))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            self._record_strings(node.exc, 'raise', arguments=True)
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if node.msg is not None:
            self._record_strings(node.msg, 'assert')
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        values = self._values(node.value)
        for target in node.targets:
            for name in _target_names(target):
                self.values[name] = values if isinstance(target, ast.Name) else []
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for name in _target_names(node.target):
            self.values[name] = self._values(node.value) if node.value is not None else []
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            expression = ast.BinOp(left=node.target, op=node.op, right=node.value)
            self.values[node.target.id] = self._values(expression)
        self.generic_visit(node)



def _python_runtime_matches(
    text: str,
    *,
    path_owned: bool,
    added_lines: Set[int],
    markers: Sequence[str],
    non_hcu_markers: Sequence[str],
    runtime_terms: Sequence[str],
    allowed_patterns: Sequence[re.Pattern],
) -> List[Tuple[int, str, str, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise ValueError("Python 输出检查无法解析第 {} 行：{}".format(error.lineno, error.msg)) from error
    visitor = _PythonRuntimeVisitor(
        path_owned=path_owned,
        source_text=text,
        added_lines=added_lines,
        markers=markers,
        non_hcu_markers=non_hcu_markers,
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


def _text_non_hcu_branches(
    value: str, markers: Sequence[str]
) -> Optional[Tuple[bool, bool]]:
    lowered = value.lower()
    if not any(marker.lower() in lowered for marker in markers):
        return None
    # Compound vendor conditions are intentionally not narrowed: a true branch
    # can still be reachable from HCU through the other operand.
    if "||" in value or "&&" in value:
        return None
    negated = bool(
        re.search(r"(?:!\s*|\bnot\s+)[a-z_][a-z0-9_.]*", lowered)
        or re.search(r"==\s*(?:false|0)\b", lowered)
        or re.search(r"!=\s*(?:true|1)\b", lowered)
    )
    return (True, False) if negated else (False, True)


def _near_hcu_condition(
    lines: Sequence[str],
    index: int,
    markers: Sequence[str],
    non_hcu_markers: Sequence[str],
    path_owned: bool,
) -> Optional[bool]:
    for previous in range(index, max(-1, index - 20), -1):
        value = lines[previous]
        if value.lstrip().startswith(("//", "/*", "*")):
            continue
        if CONDITION_LINE_RE.search(value):
            branches = _text_hcu_branches(value, markers)
            if branches is not None:
                return branches[0]
            if path_owned:
                branches = _text_non_hcu_branches(value, non_hcu_markers)
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
    lines: Sequence[str],
    path_owned: bool,
    markers: Sequence[str],
    non_hcu_markers: Sequence[str],
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
            if branches is None and current_owned:
                branches = _text_non_hcu_branches(stripped, non_hcu_markers)
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
            if branches is None and stack[-1]["remaining_owned"]:
                branches = _text_non_hcu_branches(stripped, non_hcu_markers)
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
    non_hcu_markers: Sequence[str],
    runtime_terms: Sequence[str],
    allowed_patterns: Sequence[re.Pattern],
) -> List[Tuple[int, str, str, str]]:
    result = []
    for start, end in _output_windows(lines):
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
                substring=False,
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
    config = policy.get("sensitive_diff") or {}
    if config.get("enabled") is not True:
        raise ValueError("sensitive_diff policy must be enabled")
    legacy = config.get("legacy_dcu") or {}
    runtime = config.get("hcu_runtime") or {}

    legacy_terms = _as_strings(legacy.get("terms"), "sensitive_diff.legacy_dcu.terms")
    runtime_terms = _as_strings(runtime.get("terms"), "sensitive_diff.hcu_runtime.terms")
    if not legacy_terms or not runtime_terms:
        raise ValueError("sensitive_diff legacy and runtime terms must be configured")

    legacy_excluded = _as_strings(
        legacy.get("excluded_paths"),
        "legacy_dcu.excluded_paths",
    )
    legacy_advisory = _as_strings(
        legacy.get("advisory_paths"),
        "legacy_dcu.advisory_paths",
    )
    allowed_identifiers = _as_strings(
        legacy.get("allowed_identifiers"),
        "legacy_dcu.allowed_identifiers",
    )
    allowed_identifier_patterns = _compile_patterns(
        _as_strings(
            legacy.get("allowed_identifier_patterns"),
            "legacy_dcu.allowed_identifier_patterns",
        ),
        "legacy_dcu.allowed_identifier_patterns",
        flags=0,
    )
    allowed_url_patterns = _compile_patterns(
        _as_strings(
            legacy.get("allowed_url_patterns"),
            "legacy_dcu.allowed_url_patterns",
        ),
        "legacy_dcu.allowed_url_patterns",
    )
    allowed_content_patterns = _compile_patterns(
        _as_strings(
            legacy.get("allowed_content_patterns"),
            "legacy_dcu.allowed_content_patterns",
        ),
        "legacy_dcu.allowed_content_patterns",
    )

    hcu_owned_paths = _as_strings(
        runtime.get("hcu_owned_paths"),
        "hcu_runtime.hcu_owned_paths",
    )
    runtime_excluded = _as_strings(
        runtime.get("excluded_paths"),
        "hcu_runtime.excluded_paths",
    )
    markers = _as_strings(
        runtime.get("hcu_markers"),
        "hcu_runtime.hcu_markers",
    )
    non_hcu_markers = _as_strings(
        runtime.get("non_hcu_markers"),
        "hcu_runtime.non_hcu_markers",
    )
    allowed_runtime_patterns = _compile_patterns(
        _as_strings(
            runtime.get("allowed_output_patterns"),
            "hcu_runtime.allowed_output_patterns",
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
        level: str = "advisory",
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
                level=level,
                line=line,
            )
        )

    skipped = []
    errors = []
    for change in scope["changes"]:
        if change["kind"] == "D":
            continue
        path = change["path"]
        legacy_path_excluded = _matches_path(path, legacy_excluded)
        # Lexical matches cannot establish HYGON ownership or distinguish an
        # external API/ABI from an obsolete product name. Keep manual review.
        legacy_level = "advisory"
        if change["kind"] in {"A", "C", "R"} and not legacy_path_excluded:
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
                    level=legacy_level,
                )

        try:
            data = read_blob(repo, scope["head"], path, maximum)
            if data is None:
                size = blob_size(repo, scope["head"], path)
                if size is None:
                    raise ValueError("{}：目标提交中的 Git 对象不存在或无法读取".format(path))
                kind = compiled_format(read_blob_prefix(repo, scope["head"], path))
                if not kind:
                    if size > maximum:
                        raise ValueError("{}：文件大小 {} 字节超过内容检查上限 {} 字节".format(path, size, maximum))
                    raise ValueError("{}：Git 对象内容读取失败".format(path))
            else:
                kind = compiled_format(data)
            if kind:
                skipped.append("{}：识别为{}，跳过源码文本和敏感输出检查；文件路径、大小和链接仍检查".format(path, kind))
                continue
            text = _text(path, data)
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
                        allowed_patterns=allowed_content_patterns,
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
                            level=legacy_level,
                        )

            path_owned = True
            if PurePosixPath(path).suffix.lower() == ".py":
                try:
                    ast.parse(text)
                except SyntaxError as error:
                    raise ValueError("{}：第 {} 行 Python 语法无法解析：{}".format(path, error.lineno, error.msg)) from error
                runtime_matches = _python_runtime_matches(
                    text,
                    path_owned=path_owned,
                    added_lines=added_lines,
                    markers=markers,
                    non_hcu_markers=non_hcu_markers,
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
                    non_hcu_markers=non_hcu_markers,
                    runtime_terms=runtime_terms,
                    allowed_patterns=allowed_runtime_patterns,
                )
            for number, sink, term, value in runtime_matches:
                add_finding(
                    "SENSITIVE_DIFF.HCU_RUNTIME_WORDING",
                    path,
                    number,
                    "Visible output contains AMD/XGMI wording; ownership requires review",
                    term,
                    "{} contains token {!r}: {}.".format(sink, term, _snippet(value)),
                    "Use HCU device wording for hardware and HSL for HCU links; "
                    "keep ROCm/HIP wording when it describes the software stack.",
                )
        except (ValueError, OSError, RuntimeError) as error:
            errors.append("{}：{}".format(path, error))

    return findings, scanner_status(
        "sensitive-diff",
        "failed" if errors else "findings" if findings else "passed",
        detail=(
            "检查新增内容；敏感词命中仅提示，需核实归属和语义，不要求替换合法上游接口、版权或真实后端名称。"
            + ("\n检查未完成：\n" + "\n".join(errors) if errors else "")
            + ("\n已跳过：\n" + "\n".join(skipped) if skipped else "")
        ),
        finding_count=len(findings),
    )
