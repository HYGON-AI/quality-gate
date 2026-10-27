# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Configuration YAML must not be treated as executable workflow syntax."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.native_checks import scan_syntax_and_workflows
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate import yaml_checks
from hygon_quality_security import quality_driver as driver

ROOT = Path(__file__).resolve().parents[1]


class WorkflowScopeTests(unittest.TestCase):
    def native(self, path, text):
        scope = {'head': 'a' * 40, 'changes': [{'path': path, 'kind': 'A'}],
                 'changed_lines': {path: set(range(1, len(text.splitlines()) + 1))}}
        with patch('hygon_pr_gate.native_checks.read_blob', return_value=text.encode()):
            return scan_syntax_and_workflows(ROOT, scope, load_policy(ROOT / 'policies', 'test/repo'))[0]

    def test_path_classification_is_aligned(self):
        paths = {'.github/workflows/build.yml': True,
                 '.github/workflows/check.yaml': True,
                 '.github/workflows/CI.YML': True,
                 '.github/workflows/configs/hcu-test-map.yaml': False,
                 '.github/workflows/templates/deploy.yaml': False,
                 '.github/workflows/build.yml/config.yaml': False,
                 'docs/workflows/example.yml': False,
                 '.github/workflows/README.md': False}
        for path, expected in paths.items():
            self.assertEqual(yaml_checks.is_workflow_path(path), expected, path)
            self.assertEqual(driver.is_workflow_path(path), expected, path)

    def test_actionlint_receives_only_requested_direct_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            paths = ['.github/workflows/build.yml', '.github/workflows/check.yaml',
                     '.github/workflows/configs/hcu-test-map.yaml']
            for path in paths:
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('jobs: {}\n')
            with patch.object(driver, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as run:
                driver.scan_actionlint(repo, paths[::2])
            self.assertEqual([call.args[0][-1] for call in run.call_args_list], [paths[0]])

    def test_nested_map_never_starts_actionlint(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = '.github/workflows/configs/hcu-test-map.yaml'
            target = repo / path
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({'version': 1, 'jobs': {'test': {'isolate_generated_code': True}}}))
            with patch.object(driver, 'run') as run:
                self.assertEqual(driver.scan_actionlint(repo, [path]), [])
            run.assert_not_called()

    def test_genuine_workflow_errors_remain_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = '.github/workflows/build.yml'
            target = repo / path
            target.parent.mkdir(parents=True)
            target.write_text('jobs: {}\n')
            diagnostic = {'filepath': path, 'line': 1, 'kind': 'syntax-check', 'message': 'unexpected key'}
            result = subprocess.CompletedProcess([], 1, json.dumps(diagnostic).encode(), b'')
            with patch.object(driver, 'run', return_value=result):
                findings = driver.scan_actionlint(repo, [path])
            self.assertEqual(findings[0]['severity'], 'error')

    def test_nested_map_uses_yaml_not_workflow_document_rules(self):
        path = '.github/workflows/configs/data.yaml'
        self.assertEqual(self.native(path, 'one: 1\n---\ntwo: 2\n'), [])
        self.assertTrue(self.native('.github/workflows/build.yml', 'one: 1\n---\ntwo: 2\n'))

    def test_nested_yaml_syntax_and_duplicate_keys_remain_checked(self):
        for text in ('broken: [\n', 'key: one\nkey: two\n'):
            findings = self.native('.github/workflows/configs/data.yaml', text)
            self.assertTrue(any(f['rule_id'] == 'QUALITY.YAML.SYNTAX' and f['level'] == 'blocker' for f in findings))

    def test_reference_checks_apply_only_to_executable_workflows(self):
        text = 'jobs:\n  test:\n    uses: actions/checkout@main\n'
        nested = self.native('.github/workflows/configs/map.yaml', text)
        direct = self.native('.github/workflows/build.yml', text)
        self.assertFalse(any(f['rule_id'].startswith('WORKFLOW.') for f in nested))
        self.assertTrue(any(f['rule_id'].startswith('WORKFLOW.') for f in direct))

    def test_nested_templates_do_not_exempt_real_workflow_expressions(self):
        text = 'name: {{ .Values.name }}'
        self.assertTrue(yaml_checks.is_template('.github/workflows/templates/deploy.yaml', text))
        self.assertTrue(driver.is_yaml_template('.github/workflows/templates/deploy.yaml', text))
        self.assertFalse(yaml_checks.is_template('.github/workflows/build.yml', text))
        self.assertFalse(driver.is_yaml_template('.github/workflows/build.yml', text))


if __name__ == '__main__':
    unittest.main()
