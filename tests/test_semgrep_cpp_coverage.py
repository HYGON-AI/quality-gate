# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Characterize coverage failures separately from vulnerability findings.

These tests preserve current behavior; they do not approve partial scans.
The companion semgrep_cpp_probe.py exercises the pinned real parser.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hygon_pr_gate.local_executor import LocalDockerExecutor, LocalExecutionError
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.render_summary import render_summary

from hygon_quality_security.scanner_parsers import parse_semgrep


class SemgrepCppCoverageTests(unittest.TestCase):
    def parse(self, document, policy=None):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'semgrep.json'
            report.write_text(json.dumps(document), encoding='utf-8')
            return parse_semgrep(report, policy)

    def known(self, **overrides):
        error = dict(code=2, level='warn', type='Other syntax error', path='/repo/src/gda/topology.cpp',
                     message='Other syntax error at line /repo/src/gda/topology.cpp:1136:\n single name expected for simple var')
        error.update(overrides)
        return error

    def enabled(self):
        return {'cpp_simple_var_compatibility_advisory': True}

    def test_known_warning_is_located_advisory(self):
        findings, errors = self.parse({'results': [], 'errors': [self.known()]}, self.enabled())
        self.assertEqual(errors, [])
        self.assertEqual(findings[0]['level'], 'advisory')
        self.assertEqual(findings[0]['line'], 1136)

    def test_near_misses_are_still_invalid(self):
        for change in [dict(code=3), dict(code='2'), dict(level='error'), dict(type='Parse error'),
                       dict(path='/repo/demo.py'), dict(path='/repo/other.cpp'),
                       dict(message='single name expected for simple var'),
                       dict(message=self.known()['message'] + ' unexpected crash')]:
            with self.subTest(change=change):
                _, errors = self.parse({'results': [], 'errors': [self.known(**change)]}, self.enabled())
                self.assertTrue(errors)

    def test_malformed_errors_are_not_silently_ignored(self):
        for errors in ['bad', [None], None, {}]:
            with self.subTest(errors=errors), self.assertRaises(ValueError):
                self.parse({'results': [], 'errors': errors}, self.enabled())

    def test_missing_results_is_invalid_not_empty_success(self):
        with self.assertRaises(ValueError):
            self.parse({'errors': []}, self.enabled())

    def execute(self, errors, results=None, docker_error=None):
        root = Path(__file__).resolve().parents[1]
        policy = load_policy(root / 'policies', 'any/project')
        # Only portability stubs; actual Linux Docker is tested separately.
        with patch('os.getuid', return_value=1000, create=True), patch('os.getgid', return_value=1000, create=True):
            executor = LocalDockerExecutor(policy, root / 'policies')
        executor.quality['scanners']['semgrep']['block_rule_ids'] = ['fixture.blocker']
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            (reports / 'semgrep.json').write_text(json.dumps({'results': results or [], 'errors': errors}), encoding='utf-8')
            with patch.object(executor, '_docker', side_effect=docker_error):
                return executor._semgrep(reports, {'changed_lines': {'src/gda/topology.cpp': {1}}}, reports, ['src/gda/topology.cpp'])

    def test_coverage_warning_survives_changed_line_filter(self):
        findings, status = self.execute([self.known()])
        self.assertEqual(status['state'], 'partial')
        self.assertEqual(findings[0]['line'], 1136)

    def test_unknown_error_takes_precedence(self):
        findings, status = self.execute([self.known(), {'message': 'out of memory'}])
        self.assertEqual(status['state'], 'failed')
        self.assertIn('out of memory', status['detail'])
        self.assertTrue(findings)

    def test_real_blocker_retained_with_partial_scan(self):
        results = [dict(check_id='fixture.blocker', path='/repo/src/gda/topology.cpp',
                        start={'line': 1}, extra={'severity': 'ERROR', 'message': 'real finding'})]
        findings, status = self.execute([self.known()], results)
        self.assertEqual(status['state'], 'partial')
        self.assertTrue(any(item['level'] == 'blocker' for item in findings))

    def test_container_failure_not_downgraded(self):
        with self.assertRaises(LocalExecutionError):
            self.execute([self.known()], docker_error=LocalExecutionError('container crashed'))

    def test_partial_summary_is_not_full_pass(self):
        findings, status = self.execute([self.known()])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'summary.md'
            render_summary(dict(repository='test/repo', findings=findings, statuses=[status],
                                scope=dict(merge_base='a'*40, head='b'*40, changes=[], commits=[])), path)
            text = path.read_text(encoding='utf-8')
            self.assertIn('扫描覆盖不完整', text.split('<details>')[0])
            self.assertNotIn('本检查通过', text)
            self.assertIn('1136', text)

    def test_cpp_parse_failure_is_coverage_not_vulnerability(self):
        findings, errors = self.parse({'results': [], 'errors': [{
            'code': 2, 'level': 'warn', 'type': 'Other syntax error', 'path': '/repo/src/gda/topology.cpp',
            'message': 'Other syntax error at line /repo/src/gda/topology.cpp:1136: single name expected for simple var',
        }]})
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['rule_id'], 'SAST.SEMGREP.COVERAGE')
        self.assertEqual(findings[0]['level'], 'review')
        self.assertEqual(findings[0]['path'], 'src/gda/topology.cpp')

    def test_clean_report_has_no_coverage_error(self):
        self.assertEqual(self.parse({'results': [], 'errors': []}), ([], []))

    def test_missing_report_is_not_clean_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                parse_semgrep(Path(directory) / 'missing.json')

    def test_unscoped_tool_error_is_retained(self):
        findings, errors = self.parse({'results': [], 'errors': [{'message': 'tool failure'}]})
        self.assertEqual(findings, [])
        self.assertEqual(errors, ['tool failure'])


if __name__ == '__main__':
    unittest.main()
