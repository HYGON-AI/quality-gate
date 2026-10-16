# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Bounded SPDX expression syntax and conservative structural comparison.

Parsing is not license approval or proof of legal compatibility. Compound
expressions require an explicit centrally reviewed policy entry.
"""

import re
from typing import Any, FrozenSet, Tuple


Node = Tuple[Any, ...]
TOKEN = re.compile(
    r"\(|\)|(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+"
    r"|[A-Za-z0-9][A-Za-z0-9.-]*\+?"
)
OPERATORS = {"AND", "OR", "WITH"}


def _join(operator: str, left: Node, right: Node) -> Node:
    children = []
    for node in (left, right):
        children.extend(node[1] if node[0] == operator else (node,))
    ordered = tuple(sorted(set(children), key=repr))
    return ordered[0] if len(ordered) == 1 else (operator, ordered)


def parse_expression(expression: str) -> Node:
    """Parse AND/OR/WITH/parentheses without executing or guessing IDs."""
    if not expression.strip() or len(expression) > 4096:
        raise ValueError("empty or oversized SPDX expression")
    tokens = []
    offset = 0
    while offset < len(expression):
        if expression[offset].isspace():
            offset += 1
            continue
        match = TOKEN.match(expression, offset)
        if not match:
            raise ValueError("invalid SPDX token at column {}".format(offset + 1))
        tokens.append(match.group())
        offset = match.end()
        if len(tokens) > 256:
            raise ValueError("SPDX expression has too many tokens")
    index = 0

    def identifier() -> str:
        nonlocal index
        if index >= len(tokens) or tokens[index] in OPERATORS | {"(", ")"}:
            raise ValueError("SPDX identifier expected")
        value = tokens[index]
        index += 1
        return value

    def primary(depth: int) -> Node:
        nonlocal index
        if depth > 32:
            raise ValueError("SPDX expression nesting limit exceeded")
        if index < len(tokens) and tokens[index] == "(":
            index += 1
            value = disjunction(depth + 1)
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError("unclosed SPDX parenthesis")
            index += 1
            return value
        value = ("license", identifier())
        if index < len(tokens) and tokens[index] == "WITH":
            index += 1
            exception = identifier()
            if exception.endswith("+") or exception.startswith(("LicenseRef-", "DocumentRef-")):
                raise ValueError("invalid SPDX exception identifier")
            value = ("WITH", value, exception)
        return value

    def conjunction(depth: int) -> Node:
        nonlocal index
        value = primary(depth)
        while index < len(tokens) and tokens[index] == "AND":
            index += 1
            value = _join("AND", value, primary(depth))
        return value

    def disjunction(depth: int) -> Node:
        nonlocal index
        value = conjunction(depth)
        while index < len(tokens) and tokens[index] == "OR":
            index += 1
            value = _join("OR", value, conjunction(depth))
        return value

    node = disjunction(0)
    if index != len(tokens):
        raise ValueError("unexpected SPDX token {!r}".format(tokens[index]))
    return node


def license_ids(node: Node) -> FrozenSet[str]:
    if node[0] == "license":
        return frozenset((node[1],))
    if node[0] == "WITH":
        return license_ids(node[1])
    return frozenset().union(*(license_ids(child) for child in node[1]))


def contains_exception(node: Node) -> bool:
    return node[0] == "WITH" or (
        node[0] in {"AND", "OR"} and any(contains_exception(child) for child in node[1])
    )


def preserves_expression(original: Node, current: Node) -> bool:
    """Only equality or retaining the entire old expression under AND.

    This proves structural retention, not permission to relicense. Admission
    and actual Copyright/license-body preservation are checked separately.
    OR alternatives and WITH exceptions cannot silently replace old terms.
    """
    if original == current:
        return True
    if current[0] != "AND":
        return False
    if original[0] == "AND":
        return set(original[1]).issubset(current[1])
    return original in current[1]
