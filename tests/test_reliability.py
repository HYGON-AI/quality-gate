# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Bounded regression cases for incidents seen with stable v2.0.7."""
import ast
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.git_scope import collect_scope
from hygon_pr_gate.local_executor import LocalDockerExecutor
from hygon_pr_gate.native_checks import scan_compliance
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.sensitive_diff_check import _PythonRuntimeVisitor, scan_sensitive_diff

ROOT = Path(__file__).resolve().parents[1]
HEADER = '# Copyright (c) 2026 Hygon Information Technology Co., Ltd.\n'


def visitor(text):
    return _PythonRuntimeVisitor(path_owned=True, source_text=text,
        added_lines=set(range(1, len(text.splitlines()) + 1)), markers=['hcu'],
        non_hcu_markers=['cuda'], runtime_terms=['amd'], allowed_patterns=[])


class AnalysisBoundsTests(unittest.TestCase):
    def test_unchanged_branch_values_do_not_double(self):
        text = 'flag = True\n' + 'if condition: pass\n' * 12
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(len(v.values['flag']), 1)

    def test_loops_deduplicate_unchanged_values(self):
        text = 'flag = True\n' + 'for x in xs: pass\nwhile condition: pass\n' * 6
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(len(v.values['flag']), 1)

    def test_candidate_overflow_is_explicit(self):
        text = 'value = "start"\n' + ''.join('if cond: value = "v%d"\n' % i for i in range(300))
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            visitor(text).visit(ast.parse(text))

    def test_string_growth_is_explicit(self):
        text = 's = "x"\n' + 's = s + s\n' * 20
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            visitor(text).visit(ast.parse(text))

    def test_boolean_and_integer_are_not_merged(self):
        text = 'if cond: x = True\nelse: x = 1\n'
        v = visitor(text); v.visit(ast.parse(text))
        self.assertEqual(len(v.values['x']), 2)

    def test_five_hundred_branches_stay_bounded(self):
        text = 'flag = True\n' + 'if condition: pass\n' * 500
        v = visitor(text); v.visit(ast.parse(text))
        self.assertEqual(len(v.values['flag']), 1)

    def test_dedup_preserves_incremental_origins(self):
        text = 'if cond: x = "amd"\nelse: x = "amd"\nprint(x)\n'
        v = visitor(text); v.added_lines = {2}; v.visit(ast.parse(text))
        self.assertEqual(v.values['x'][0][1], frozenset({1, 2}))
        self.assertTrue(v.matches)

    def test_work_budget_is_explicit(self):
        v = visitor('x = 1'); v.MAX_OPERATIONS = 1
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            v.visit(ast.parse('x = 1'))

    def test_format_combinations_are_not_silently_truncated(self):
        text = 'x = "0"\n' + ''.join('if cond: x = "%d"\n' % i for i in range(20))
        text += 's = "{}-{}".format(x, x)\n'
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            visitor(text).visit(ast.parse(text))


class ScopeReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Hygon Fixture')
        self.git('config', 'user.email', 'fixture@hygon.com')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.autocrlf', 'false')
        self.write('README.md', 'fixture\n')
        self.base = self.commit()
        self.policy = load_policy(ROOT / 'policies', 'test/repo')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, path, text):
        p = self.repo / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'test: fixture', '--allow-empty')
        return self.git('rev-parse', 'HEAD')

    def scope(self):
        return collect_scope(self.repo, self.base, self.commit())

    def test_attribute_cannot_hide_added_lines(self):
        self.write('.gitattributes', '*.py -diff\n')
        self.write('demo.py', 'x = 1\n')
        scope = self.scope()
        self.assertEqual(scope['changed_lines']['demo.py'], {1})

    def test_textconv_cannot_hide_changed_source(self):
        self.write('demo.py', 'x = 1\n')
        self.write('.gitattributes', '*.py diff=hidden\n')
        self.base = self.commit()
        self.git('config', 'diff.hidden.textconv', 'echo hidden')
        self.write('demo.py', 'x = 2\n')
        self.assertEqual(self.scope()['changed_lines']['demo.py'], {1})

    def test_missing_submodule_commit_is_not_a_missing_blob(self):
        self.write('.gitmodules', '[submodule "lib"]\n\tpath = vendor/lib\n\turl = https://example.invalid/lib\n')
        self.git('add', '.')
        self.git('update-index', '--add', '--cacheinfo', '160000,' + '1' * 40 + ',vendor/lib')
        self.git('commit', '-qm', 'test: gitlink')
        scope = collect_scope(self.repo, self.base, self.git('rev-parse', 'HEAD'))
        findings, status = scan_sensitive_diff(self.repo, scope, self.policy)
        self.assertNotEqual(status['state'], 'failed', status)
        self.assertIn('gitlink', status['detail'])
        self.assertEqual(scope['changed_lines']['vendor/lib'], set())

    def test_openmdw_approved_header(self):
        self.write('demo.py', HEADER + '# SPDX-License-Identifier: OpenMDW-1.1\nx = 1\n')
        findings, _ = scan_compliance(self.repo, self.scope(), self.policy)
        self.assertEqual(findings, [])

    def test_unknown_license_still_requires_approval(self):
        self.write('demo.py', HEADER + '# SPDX-License-Identifier: Unapproved-1.0\nx = 1\n')
        findings, _ = scan_compliance(self.repo, self.scope(), self.policy)
        self.assertTrue(any(f['rule_id'] == 'LICENSE.UNSUPPORTED_PR_FILE' and f['level'] == 'blocker' for f in findings))

    def test_openmdw_original_notice_cannot_be_replaced(self):
        self.write('demo.py', HEADER + '# SPDX-License-Identifier: OpenMDW-1.1\nx = 1\n')
        self.base = self.commit()
        self.write('demo.py', HEADER + '# SPDX-License-Identifier: MIT\nx = 1\n')
        findings, _ = scan_compliance(self.repo, self.scope(), self.policy)
        self.assertTrue(any(f['rule_id'] == 'COPYRIGHT.ORIGINAL_HEADER_REMOVED' for f in findings))

    def test_only_deletions_does_not_fabricate_added_lines(self):
        self.write('demo.py', 'a = 1\nb = 2\n')
        self.base = self.commit(); self.write('demo.py', 'a = 1\n')
        self.assertEqual(self.scope()['changed_lines']['demo.py'], set())

    def test_analysis_budget_marks_scan_invalid(self):
        self.write('demo.py', 's = "x"\n' + 's = s + s\n' * 20)
        _, status = scan_sensitive_diff(self.repo, self.scope(), self.policy)
        self.assertEqual(status['state'], 'failed')
        self.assertIn('budget', status['detail'])


class ExecutorReliabilityTests(unittest.TestCase):
    def executor(self):
        with patch('os.getuid', return_value=1000, create=True), patch('os.getgid', return_value=1000, create=True):
            return LocalDockerExecutor(load_policy(ROOT / 'policies', 'test/repo'), ROOT / 'policies')

    def test_ruff_mandatory_rules_are_isolated(self):
        e = self.executor()
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp); (reports / 'ruff.json').write_text('[]')
            with patch.object(e, '_docker') as docker:
                e._ruff(ROOT, {'changed_lines': {}}, reports, ['demo.py'])
            args = docker.call_args.args[3]
            self.assertIn('--isolated', args)
            self.assertIn('--ignore-noqa', args)

    def test_missing_report_keeps_exit_and_safe_cause(self):
        e = self.executor()
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.CompletedProcess([], 1, b'', b'OSError: [Errno 28] No space left on device\npassword=secret-not-to-print')
            with patch.object(e, '_docker', return_value=result):
                with self.assertRaises(ValueError) as error:
                    e._semgrep(ROOT, {'changed_lines': {}}, Path(tmp), ['demo.py'])
            self.assertIn('exit=1', str(error.exception))
            self.assertIn('No space left', str(error.exception))
            self.assertNotIn('secret-not-to-print', str(error.exception))

    def test_memory_error_cannot_turn_into_passed(self):
        from hygon_pr_gate.audit_pr import build_parser, run_gate
        with tempfile.TemporaryDirectory() as tmp:
            args = build_parser().parse_args(['--repo', tmp, '--repository', 'test/repo',
                '--base', 'a'*40, '--head', 'b'*40, '--policy-root', str(ROOT/'policies'),
                '--checks', 'identity', '--summary', str(Path(tmp)/'result.md')])
            with patch('hygon_pr_gate.audit_pr.collect_scope', side_effect=MemoryError()):
                report, code = run_gate(args)
            self.assertEqual(code, 1)
            self.assertIn('MemoryError', report.read_text(encoding='utf-8'))

    def test_malformed_report_never_echoes_content(self):
        from hygon_pr_gate.local_executor import _require_report
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'semgrep.json'
            report.write_text('private-code-secret')
            with self.assertRaisesRegex(ValueError, 'malformed') as error:
                _require_report(report, subprocess.CompletedProcess([], 0, b'private-code-secret', b''))
            self.assertNotIn('private-code-secret', str(error.exception))

    def test_tool_timeout_and_missing_image_are_classified(self):
        from hygon_pr_gate.local_executor import _run, LocalExecutionError
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(['docker'], 2)):
            with self.assertRaisesRegex(LocalExecutionError, 'timed out'):
                _run(['docker'], timeout=2)
        result = subprocess.CompletedProcess([], 1, b'', b'No such image: private-registry/secret')
        with patch('subprocess.run', return_value=result):
            with self.assertRaisesRegex(LocalExecutionError, 'pinned image missing') as error:
                _run(['docker'])
            self.assertNotIn('private-registry', str(error.exception))

    def test_docker_timeout_removes_only_own_container(self):
        from hygon_pr_gate.local_executor import LocalExecutionError
        e = self.executor()
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp); cid = 'a'*64
            def execute(command, **kwargs):
                if command[:2] == ['docker', 'run']:
                    Path(command[command.index('--cidfile')+1]).write_text(cid)
                    raise LocalExecutionError('timeout')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch.object(e, '_verify_image'), patch('hygon_pr_gate.local_executor._run', side_effect=execute) as run:
                with self.assertRaises(LocalExecutionError):
                    e._docker('semgrep', ROOT, reports, ['semgrep'])
            self.assertEqual(run.call_args.args[0], ['docker', 'rm', '-f', cid])
            self.assertFalse((reports/'semgrep.cid').exists())


if __name__ == '__main__':
    unittest.main()
