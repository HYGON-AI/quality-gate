# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff
from hygon_pr_gate.local_executor import LocalDockerExecutor, LocalExecutionError

ROOT = Path(__file__).resolve().parents[1]


class UniversalScopeTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy(ROOT / 'policies', 'different/project')

    def scan(self, path, content):
        scope = {'head': '1' * 40, 'changes': [{'kind': 'A', 'path': path}],
                 'changed_lines': {path: {1}}}
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=content), patch('hygon_pr_gate.sensitive_diff_check.blob_size', return_value=None):
            return scan_sensitive_diff(Path('/tmp'), scope, self.policy)

    def test_output_is_independent_of_directory_and_markers(self):
        for path in ('demo.py', 'src/demo.py', 'tests/demo.py', 'docs/demo.py'):
            for value in ('amd', 'amdsmi', 'abcdamd', 'XGMIlink'):
                with self.subTest(path=path, value=value):
                    findings, _ = self.scan(path, ('print(%r)\n' % value).encode())
                    self.assertTrue(any(f['level'] == 'blocker' for f in findings))

    def test_text_suffix_and_internal_docs_do_not_exempt_dcu(self):
        for path in ('settings.cfg', 'script', 'docs/internal/note.md'):
            with self.subTest(path=path):
                findings, _ = self.scan(path, b'label=dcu\n')
                self.assertTrue(any(f['level'] == 'blocker' for f in findings))

    def test_unreadable_content_is_invalid(self):
        for content in (None, b'abc\x00def', b'\xfftext'):
            with self.subTest(content=content):
                _, status = self.scan('example', content)
                self.assertEqual(status['state'], 'failed')
                self.assertIn('example', status['detail'])

    def test_notebook_image_payload_is_excluded_but_text_is_checked(self):
        image = {'outputs': [{'data': {'image/png': 'randomDCUrandom dcu amd'}}]}
        self.assertEqual(self.scan('demo.ipynb', json.dumps(image).encode())[0], [])
        image['source'] = ['dcu']
        self.assertTrue(self.scan('demo.ipynb', json.dumps(image).encode())[0])

    def test_semgrep_parse_failure_is_invalid(self):
        executor = LocalDockerExecutor(self.policy, ROOT / 'policies')
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            (reports / 'semgrep.json').write_text(json.dumps({
                'results': [], 'errors': [{'path': '/repo/example.cpp', 'message': 'bad syntax'}]}))
            with patch.object(executor, '_docker'):
                findings, status = executor._semgrep(reports, {'changed_lines': {'example.cpp': {1}}}, reports, ['example.cpp'])
            self.assertEqual(status['state'], 'failed')
            self.assertIn('example.cpp', status['detail'])
            self.assertTrue(findings)

    def test_missing_report_is_invalid(self):
        executor = LocalDockerExecutor(self.policy, ROOT / 'policies')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(executor, '_docker'), self.assertRaisesRegex(ValueError, 'semgrep.json'):
                executor._semgrep(Path(directory), {'changed_lines': {'demo.py': {1}}}, Path(directory), ['demo.py'])


    def test_compiled_contents_are_skipped_but_path_is_checked(self):
        for data in (b'\x7fELF\x00dcu amd', b'BC\xc0\xdedcu', b'!<arch>\ndcu'):
            findings, status = self.scan('lib_dcu.so.1', data)
            self.assertTrue(findings)
            self.assertTrue(all(f['rule_id'].endswith('_PATH') for f in findings))
            self.assertIn('lib_dcu.so.1', status['detail'])
            self.assertIn('跳过源码文本', status['detail'])

    def test_text_with_library_suffix_is_not_exempt(self):
        findings, _ = self.scan('example.so', b'dcu')
        self.assertTrue(findings)

    def test_invalid_notebook_reports_path_and_line(self):
        _, status = self.scan('demo.ipynb', b'{broken')
        self.assertEqual(status['state'], 'failed')
        self.assertRegex(status['detail'], 'demo.ipynb.*第 1 行.*JSON')

    def test_large_compiled_artifact_is_skipped_before_text_limit(self):
        scope = {'head': '1'*40, 'changes': [{'kind': 'A', 'path': 'lib.so'}], 'changed_lines': {}}
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=None), patch('hygon_pr_gate.sensitive_diff_check.blob_size', return_value=8000000), patch('hygon_pr_gate.sensitive_diff_check.read_blob_prefix', return_value=b'\x7fELF'):
            findings, status = scan_sensitive_diff(Path('/tmp'), scope, self.policy)
            self.assertEqual(findings, [])
            self.assertIn('ELF', status['detail'])
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=None), patch('hygon_pr_gate.sensitive_diff_check.blob_size', return_value=8000000), patch('hygon_pr_gate.sensitive_diff_check.read_blob_prefix', return_value=b'text'):
            _, status = scan_sensitive_diff(Path('/tmp'), scope, self.policy)
            self.assertEqual(status['state'], 'failed')
            self.assertRegex(status['detail'], 'lib.so.*8000000.*4194304')

    def test_python_output_values(self):
        positive = [
            'vendor = "amd"\nprint(vendor)\n',
            'print("\\x61md")\n',
            'print("a" + "md")\n',
            'vendor = "amd"\nprint(f"device: {vendor}")\n',
            'vendor = "a"\nvendor += "md"\nprint(vendor)\n',
            'if flag:\n    vendor = "amd"\nelse:\n    vendor = "hcu"\nprint(vendor)\n',
        ]
        negative = [
            'print(len("amd"))\n',
            'message = "amd"\n',
            'result = {"status": "amd"}\n',
            'vendor = "amd"\nvendor = "hcu"\nprint(vendor)\n',
            'vendor = "amd"\ndef show(vendor):\n    print(vendor)\n',
            'def first():\n    vendor = "amd"\ndef second():\n    print(vendor)\n',
        ]
        for code in positive:
            with self.subTest(code=code):
                self.assertTrue(self.scan('demo.py', code.encode())[0])
        for code in negative:
            with self.subTest(code=code):
                self.assertEqual(self.scan('demo.py', code.encode())[0], [])

    def test_incremental_output_uses_changed_assignment(self):
        scope = {'head': '1'*40, 'changes': [{'kind': 'M', 'path': 'demo.py'}],
                 'changed_lines': {'demo.py': {1}}}
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=b'vendor = "amd"\nprint(vendor)\n'):
            findings, _ = scan_sensitive_diff(Path('/tmp'), scope, self.policy)
            self.assertTrue(findings)
            self.assertEqual(findings[0]['line'], 1)

    def test_deleted_lines_do_not_reintroduce_old_findings(self):
        from hygon_pr_gate.local_executor import _filter_changed_lines
        findings = [{'path': 'demo.py', 'line': 1}, {'path': 'demo.py', 'line': 3}]
        self.assertEqual(_filter_changed_lines(findings, {'demo.py': set()}), [])
        self.assertEqual(_filter_changed_lines(findings, {'demo.py': {3}}), [findings[1]])

    def test_partial_precheck_is_not_rendered_as_full_pass(self):
        from hygon_pr_gate.render_summary import render_summary
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'summary.md'
            render_summary({'repository': 'any/project', 'partial': True, 'scope': {
                'merge_base': '0'*40, 'head': '1'*40, 'changes': [], 'commits': []}}, output)
            self.assertIn('内置预检通过，完整门禁未执行', output.read_text())
            self.assertNotIn('✅ Passed', output.read_text())

    def test_external_preflight_and_partial_results(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', directory, *args]).decode().strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.com')
            (repo / 'demo.py').write_text('value = 1\n')
            git('add', '.')
            git('commit', '-qm', 'initial')
            scope = {'head': git('rev-parse', 'HEAD'), 'changes': [{'path': 'demo.py', 'kind': 'M'}]}
            executor = LocalDockerExecutor(self.policy, ROOT / 'policies')
            with self.assertRaisesRegex(LocalExecutionError, '检出版本'):
                executor.scan(repo, dict(scope, head='0'*40), ['ruff'])
            (repo / 'demo.py').write_text('changed = 1\n')
            with self.assertRaisesRegex(LocalExecutionError, '工作区'):
                executor.scan(repo, scope, ['ruff'])
            (repo / 'demo.py').write_text('value = 1\n')
            (repo / 'extra.py').write_text('untracked = 1\n')
            with self.assertRaisesRegex(LocalExecutionError, '未跟踪'):
                executor.scan(repo, scope, ['ruff'])
            (repo / 'extra.py').unlink()
            finding = {'path': 'demo.py', 'line': 1, 'level': 'blocker'}
            with patch.object(executor, '_ruff', return_value=([finding], {'scanner': 'ruff', 'state': 'findings'})), patch.object(executor, '_quality_tools', side_effect=LocalExecutionError('ShellCheck 无法读取脚本')):
                findings, statuses = executor.scan(repo, scope, ['ruff', 'quality-tools'])
            self.assertEqual(findings, [finding])
            self.assertEqual(statuses[-1]['state'], 'failed')
            self.assertIn('ShellCheck 无法读取脚本', statuses[-1]['detail'])

            # Verify the gate keeps the blocker in its final failure report.
            import argparse
            from hygon_pr_gate.audit_pr import run_gate
            finding.update(rule_id='TEST', title='已发现的阻断', evidence='fixture', remediation='修复')
            with tempfile.TemporaryDirectory() as reports:
                args = argparse.Namespace(repo=repo, policy_root=ROOT / 'policies',
                    repository='any/project', base=scope['head'], head=scope['head'],
                    summary=Path(reports) / 'summary.md', native_only=False)
                with patch.object(LocalDockerExecutor, 'scan', return_value=(findings, statuses)):
                    output, code = run_gate(args)
                report = output.read_text()
                self.assertEqual(code, 1)
                self.assertIn('已发现的阻断', report)
                self.assertIn('ShellCheck 无法读取脚本', report)
                self.assertIn('存在阻断问题；⚠️ 扫描无效', report)

    def test_quality_grouping_filters_before_aggregation(self):
        from hygon_quality_security.scanner_parsers import parse_quality_tools
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'quality.json'
            report.write_text(json.dumps({'findings': [
                {'tool': 'shellcheck', 'path': '/repo/run.sh', 'code': 'SC2154',
                 'severity': 'warning', 'line': line, 'message': 'undefined'}
                for line in (2, 20)
            ], 'operational_errors': ['actionlint: report missing']}))
            errors = []
            findings = parse_quality_tools(report, changed_lines={'run.sh': {20}},
                                           operational_errors=errors)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]['line'], 20)
            self.assertEqual(errors, ['actionlint: report missing'])
            self.assertEqual(parse_quality_tools(report, changed_lines={'run.sh': set()},
                                                operational_errors=[]), [])

    def test_remaining_output_regressions(self):
        positives = [
            'print("{}".format("amd"))',
            'print(f"amd device: {device}")',
            'print("\\namd")',
            'vendor = "amd"\nfor item in []:\n    vendor = "hcu"\nprint(vendor)',
            'vendor = "amd"\nwhile False:\n    vendor = "hcu"\nprint(vendor)',
        ]
        for code in positives:
            with self.subTest(code=code):
                self.assertTrue(self.scan('demo.py', code.encode())[0])
        self.assertEqual(self.scan('demo.py', b'assert ready, len("amd")')[0], [])

    def test_file_failure_preserves_findings_and_continues(self):
        scope = {'head': '1'*40, 'changes': [{'kind': 'A', 'path': p} for p in ('a.py', 'b.py', 'c.py')], 'changed_lines': {}}
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', side_effect=[b'print("amd")', b'def broken(:', b'print("xgmi")']):
            findings, status = scan_sensitive_diff(Path('/tmp'), scope, self.policy)
        self.assertEqual(status['state'], 'failed')
        self.assertIn('b.py', status['detail'])
        self.assertEqual({f['path'] for f in findings}, {'a.py', 'c.py'})
