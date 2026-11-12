# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Production PR gate no longer exposes or requires Semgrep."""
import inspect
import unittest
import subprocess
from unittest.mock import patch
from pathlib import Path
import yaml
from hygon_pr_gate.audit_pr import ALL_CHECKS, _selected_checks, _check_display_name
from hygon_pr_gate.local_executor import LocalDockerExecutor
from hygon_pr_gate.policy import load_policy

ROOT = Path(__file__).resolve().parents[1]


class SemgrepRemovedTests(unittest.TestCase):
    def test_cli_rejects_removed_scanner(self):
        self.assertNotIn('semgrep', ALL_CHECKS)
        self.assertNotIn('semgrep', _selected_checks('all'))
        with self.assertRaisesRegex(ValueError, 'unknown PR check'):
            _selected_checks('semgrep')

    def test_security_name_preserved_with_gitleaks_only(self):
        self.assertEqual(_check_display_name(['gitleaks'])[0], 'Code security')
        workflow = yaml.safe_load((ROOT / '.github/workflows/pr-quality-gate.yml').read_text(encoding='utf-8'))
        matrix = workflow['jobs']['incremental_check']['strategy']['matrix']['include']
        security = next(row for row in matrix if row['check_id'] == 'security-check')
        self.assertEqual(security['scanners'], 'gitleaks')
        self.assertEqual(workflow['jobs']['hygon-pr-gate-result-check']['name'], 'All required checks')

    def test_executor_defaults_exclude_semgrep(self):
        default = inspect.signature(LocalDockerExecutor.scan).parameters['scanner_names'].default
        self.assertEqual(default, ('gitleaks', 'ruff', 'quality-tools'))

    def test_scan_needs_no_semgrep_image_or_report(self):
        with patch('os.getuid', return_value=1000, create=True), patch('os.getgid', return_value=1000, create=True):
            executor = LocalDockerExecutor(load_policy(ROOT / 'policies', 'test/repo'), ROOT / 'policies')
        executor.images.pop('semgrep', None)
        scope = {'head': 'abc', 'changes': []}
        def git(*args):
            return subprocess.CompletedProcess([], 0, b'abc\n' if 'rev-parse' in args else b'', b'')
        with patch('hygon_pr_gate.local_executor.git', side_effect=git), \
             patch.object(executor, '_semgrep', side_effect=AssertionError('removed')) as removed, \
             patch.object(executor, '_gitleaks', return_value=([], {'scanner': 'gitleaks', 'state': 'passed'})), \
             patch.object(executor, '_ruff', return_value=([], {'scanner': 'ruff', 'state': 'passed'})), \
             patch.object(executor, '_quality_tools', return_value=([], {'scanner': 'quality-tools', 'state': 'passed'})):
            findings, statuses = executor.scan(ROOT, scope)
            self.assertEqual(findings, [])
            self.assertEqual(len(statuses), 3)
            removed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
