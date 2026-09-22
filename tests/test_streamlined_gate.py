# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""v2.0.7 scope, diagnostic retention and workflow compatibility contracts."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from hygon_pr_gate.local_executor import LocalDockerExecutor, LocalExecutionError
from hygon_pr_gate.policy import load_policy
from hygon_quality_security import quality_driver as driver

ROOT = Path(__file__).resolve().parents[1]


class StreamlinedGateTests(unittest.TestCase):
    def executor(self):
        with patch('os.getuid', return_value=1000, create=True), patch('os.getgid', return_value=1000, create=True):
            return LocalDockerExecutor(load_policy(ROOT / 'policies', 'test/repo'), ROOT / 'policies')

    def test_excluded_languages_never_start_semgrep(self):
        executor = self.executor()
        with patch.object(executor, '_docker') as docker:
            for paths in ([], ['x.cpp', 'x.h', 'x.c', 'x.cu', 'x.hpp', 'x.CXX'], ['x.go', 'x.rs', 'x.sh']):
                findings, status = executor._semgrep(ROOT, {}, ROOT, paths)
                self.assertEqual(findings, [])
                self.assertEqual(status['state'], 'not-applicable')
                self.assertIn('C/C++', status['detail'])
            docker.assert_not_called()

    def test_mixed_targets_scan_only_python_js_ts(self):
        executor = self.executor()
        targets = ['a.py', 'a.pyi', 'a.js', 'a.jsx', 'a.ts', 'a.tsx', 'UPPER.PY']
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            (reports / 'semgrep.json').write_text('{"results": [], "errors": []}')
            with patch.object(executor, '_docker') as docker:
                _, status = executor._semgrep(ROOT, {'changed_lines': {}}, reports, targets + ['x.cpp', 'x.h'])
                arguments = docker.call_args.args[3]
                self.assertEqual([v for v in arguments if v.startswith('/repo/')], ['/repo/' + v for v in targets])
                self.assertEqual(status['state'], 'passed')

    def test_applicable_scan_missing_report_or_crash_does_not_pass(self):
        executor = self.executor()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(executor, '_docker'), self.assertRaises(ValueError):
                executor._semgrep(ROOT, {'changed_lines': {}}, Path(directory), ['x.py'])
            with patch.object(executor, '_docker', side_effect=LocalExecutionError('crash')), self.assertRaises(LocalExecutionError):
                executor._semgrep(ROOT, {'changed_lines': {}}, Path(directory), ['x.ts'])

    def test_shellcheck_style_only_removed(self):
        document = {'comments': [dict(level=level, code=index, file='a.sh', line=1, message=level)
                                  for index, level in enumerate(['style', 'info', 'warning', 'error'])]}
        result = subprocess.CompletedProcess([], 1, json.dumps(document).encode(), b'')
        with patch.object(driver, 'run', return_value=result):
            findings = driver.scan_shellcheck(ROOT, ['a.sh'])
        self.assertEqual([v['severity'] for v in findings], ['info', 'warning', 'error'])

    def test_yaml_configuration_has_no_style_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / 'a.yml').write_text('a: 1\n')
            with patch.object(driver, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as run:
                self.assertEqual(driver.scan_yamllint(repo, ['a.yml']), [])
                command = run.call_args.args[0]
                self.assertEqual(yaml.safe_load(command[command.index('-d') + 1]), {'rules': {'key-duplicates': 'enable'}})

    def test_driver_never_runs_lizard_and_preserves_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            with patch('sys.argv', ['driver', '--repo', directory, '--output', str(report)]), \
                 patch.object(driver, 'tracked_files', return_value=[]), \
                 patch.object(driver, 'scan_shellcheck', return_value=[]), \
                 patch.object(driver, 'scan_actionlint', side_effect=RuntimeError('tool unavailable')), \
                 patch.object(driver, 'scan_yamllint', return_value=[]):
                self.assertEqual(driver.main(), 1)
                self.assertIn('actionlint: tool unavailable', json.loads(report.read_text())['operational_errors'])
        self.assertFalse(hasattr(driver, 'scan_lizard'))

    def test_workflow_names_ids_version_and_aggregate_preserved(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/pr-quality-gate.yml').read_text(encoding='utf-8'))
        jobs = workflow['jobs']
        self.assertEqual(set(jobs), {'incremental_check', 'hygon-pr-gate-result-check'})
        matrix = jobs['incremental_check']['strategy']['matrix']['include']
        self.assertEqual([item['display_name'] for item in matrix], ['Code compliance', 'Code quality', 'Code security'])
        self.assertEqual([item['check_id'] for item in matrix], ['governance-compliance-check', 'repository-integrity-quality-check', 'security-check'])
        self.assertEqual(jobs['hygon-pr-gate-result-check']['name'], 'All required checks')
        self.assertEqual(workflow['env']['QUALITY_GATE_VERSION'], 'v2.0.7')


if __name__ == '__main__':
    unittest.main()
