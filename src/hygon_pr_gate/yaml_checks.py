# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Syntax-only YAML stream validation; never construct application objects."""
import re
from pathlib import PurePosixPath

import yaml


def is_template(path, text):
    # Do not exempt Actions expressions (${{ ... }}) or ordinary YAML merely
    # because it contains braces. Only recognize template source locations.
    return (not path.startswith('.github/workflows/')
            and 'templates' in PurePosixPath(path).parts
            and bool(re.search(r'{{-?\s*(?:\.|if\b|range\b|include\b|with\b|end\b)', text)))


def validate_yaml(text, workflow=False):
    documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    if workflow and (len(documents) != 1 or not isinstance(documents[0], yaml.MappingNode)):
        raise yaml.YAMLError('GitHub Actions Workflow must contain one mapping document')
    seen_nodes = set()

    def visit(node):
        if node is None or id(node) in seen_nodes:
            return
        seen_nodes.add(id(node))
        if workflow and not node.tag.startswith('tag:yaml.org,2002:'):
            raise yaml.constructor.ConstructorError(None, None, 'custom tags are not supported in Actions', node.start_mark)
        if isinstance(node, yaml.MappingNode):
            keys = set()
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode):
                    # Distinguish numeric/null keys from quoted strings; preserve
                    # spelling rather than collapsing YAML 1.1 on/yes/true.
                    identity = (key.tag, key.value)
                    if identity in keys:
                        raise yaml.constructor.ConstructorError(None, None, 'duplicate mapping key', key.start_mark)
                    keys.add(identity)
                visit(key)
                visit(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)

    for document in documents:
        visit(document)


def comment_only_change(before, after):
    # Conservative: only suppress existing debt when every non-comment line
    # (including whitespace/indentation and blank lines) is unchanged.
    def significant(text):
        return [line for line in text.splitlines() if not line.lstrip().startswith('#')]
    return significant(before) == significant(after)
