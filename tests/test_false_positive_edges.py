# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Synthetic boundaries: accepted input paired with genuinely invalid input."""
import unittest

import yaml

from hygon_pr_gate.yaml_checks import validate_yaml, comment_only_change, is_template
from hygon_quality_security.quality_driver import distinct_typed_key_lines


class YamlEdges(unittest.TestCase):
    def test_linter_typed_key_filter_is_narrow(self):
        self.assertEqual(distinct_typed_key_lines('1: n\n"1": s\n"1": duplicate\n'), {2})
        self.assertEqual(distinct_typed_key_lines('a: one\n"a": two\n'), set())
        self.assertEqual(distinct_typed_key_lines('1: n\n"1": [broken\n'), set())
        self.assertEqual(distinct_typed_key_lines('v: &a [*a]\n'), set())

    def test_valid_streams(self):
        cases = {
            'empty': '',
            'comments': '# explanation\n',
            'terminator': '---\nkind: Service\n...\n',
            'empty_document': '---\n---\nkind: Service\n',
            'separate_keys': 'key: one\n---\nkey: two\n',
            'nested_keys': 'left: {name: one}\nright: {name: two}\n',
            'literal': 'script: |\n  key: one\n  key: two\n  ---\n',
            'merge_sequence': 'a: &a {x: 1}\nb: &b {y: 2}\nc: {<<: [*a, *b], x: 3}\n',
            'tagged_sequence': 'value: !Join [",", [one, two]]\n',
            'unicode_crlf': '\ufeff名称: 测试\r\nkind: Service\r\n',
            'typed_keys': '1: numeric\n"1": string\n',
            'null_string_keys': 'null: empty\n"null": word\n',
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                validate_yaml(source)

    def test_invalid_streams(self):
        for source in ('a: 1\n"a": 2\n', 'x: {a: 1, a: 2}\n',
                       'x: *missing\n', 'x: [1\n', 'x: 1\n---\ny: [bad\n'):
            with self.subTest(source=source):
                with self.assertRaises(yaml.YAMLError):
                    validate_yaml(source)

    def test_actions_expressions_and_boolean_spelling(self):
        validate_yaml('name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n'
                      '    steps:\n      - run: echo "${{ github.ref }}"\n', workflow=True)
        validate_yaml('on: push\nyes: value\ntrue: other\n')

    def test_actions_custom_tag_rejected(self):
        with self.assertRaises(yaml.YAMLError):
            validate_yaml('jobs: !Ref value\n', workflow=True)

    def test_braces_outside_template_not_exempt(self):
        self.assertFalse(is_template('deploy.yaml', 'value: {{ .Values.name }}'))
        self.assertFalse(is_template('.github/workflows/build.yml', '{{ .Values.name }}'))
        self.assertFalse(is_template('templates/config.yml', 'name: ordinary'))

    def test_comment_debt_conservative(self):
        self.assertTrue(comment_only_change('x: [bad\n', '# note\nx: [bad\n'))
        self.assertFalse(comment_only_change('x: [bad\n', 'x: [bad\ny: changed\n'))
        self.assertFalse(comment_only_change('  x: [bad\n', ' x: [bad\n'))


if __name__ == '__main__':
    unittest.main()
