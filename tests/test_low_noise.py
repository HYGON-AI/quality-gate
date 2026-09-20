# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.native_checks import scan_syntax_and_workflows
from hygon_pr_gate.policy import load_policy
from hygon_quality_security.scanner_parsers import parse_gitleaks
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff
from hygon_pr_gate.audit_pr import _emit_github_annotations
from hygon_quality_security.secret_placeholders import deterministic_placeholder_reason
from hygon_pr_gate.render_summary import render_summary
import contextlib
import io

ROOT = Path(__file__).resolve().parents[1]


class YamlRegressionTests(unittest.TestCase):
    def scan(self, text, path='deploy.yaml', previous=None):
        policy = load_policy(ROOT / 'policies', 'any/project')
        scope = {'head': 'head', 'merge_base': 'base', 'changed_lines': {path: {1}},
                 'changes': [{'kind': 'A' if previous is None else 'M', 'path': path}]}
        def blob(repo, ref, name, maximum):
            return (text if ref == 'head' else previous).encode()
        with patch('hygon_pr_gate.native_checks.read_blob', side_effect=blob):
            return scan_syntax_and_workflows(Path('.'), scope, policy)[0]

    def blockers(self, *args, **kwargs):
        return [f for f in self.scan(*args, **kwargs) if f['level'] == 'blocker']

    def test_kubernetes_multi_document(self):
        self.assertEqual(self.blockers('kind: Deployment\n---\nkind: Service\n'), [])

    def test_malformed_second_document(self):
        self.assertTrue(self.blockers('kind: Deployment\n---\nvalue: [broken\n'))

    def test_custom_tag_is_syntax_not_python_execution(self):
        self.assertEqual(self.blockers('value: !Ref Resource\n'), [])

    def test_duplicate_key_blocks(self):
        self.assertTrue(self.blockers('a: 1\na: 2\n'))

    def test_workflow_must_be_single_mapping(self):
        for value in ('name: test\n---\nname: other\n', '- not-a-workflow\n', ''):
            self.assertTrue(self.blockers(value, '.github/workflows/test.yml'))

    def test_old_syntax_debt_is_advisory(self):
        findings = self.scan('# new comment\nx: [broken\n', previous='x: [broken\n')
        self.assertTrue(findings)
        self.assertFalse(any(f['level'] == 'blocker' for f in findings))

    def test_new_syntax_error_blocks(self):
        self.assertTrue(self.blockers('x: [broken\n', previous='x: [valid]\n'))

    def test_helm_template_is_explicitly_unvalidated(self):
        findings = self.scan('value: {{ .Values.name }}\n', 'charts/demo/templates/app.yaml')
        self.assertTrue(findings)
        self.assertTrue(all(f['level'] == 'advisory' for f in findings))

    def test_actions_expression_is_not_template_exemption(self):
        self.assertTrue(self.blockers('name: ${{ github.ref }}\njobs: [broken\n', '.github/workflows/test.yml'))

    def test_yaml_alias_cycle_does_not_recurse_forever(self):
        self.assertEqual(self.blockers('value: &a [*a]\n'), [])

    def test_merge_key_override_is_legal(self):
        self.assertEqual(self.blockers('base: &base {a: 1}\nvalue: {<<: *base, a: 2}\n'), [])

    def test_new_breakage_with_existing_error_still_blocks(self):
        self.assertTrue(self.blockers('x: [broken\ny: [also broken\n', previous='x: [broken\n'))


class AdvisoryRegressionTests(unittest.TestCase):
    def test_placeholder_requires_source_evidence(self):
        policy = load_policy(ROOT / 'policies', 'any/project')
        config = policy['quality_security']['scanners']['gitleaks']['placeholder_filter']
        item = {'RuleID': 'generic-api-key', 'File': 'docs/example.md', 'StartLine': 1}
        for line, expected in [('api_key = "your-api-key"', 'placeholder-literal'),
                               ('api_key = "${API_KEY}"', 'template-reference'),
                               ('api_key = "synthetic-not-an-approved-placeholder"', None)]:
            with patch('hygon_quality_security.secret_placeholders._source_line', return_value=line):
                self.assertEqual(deterministic_placeholder_reason(item, source_repo=Path('.'),
                    target_commit='a'*40, config=config), expected)
        with patch('hygon_quality_security.secret_placeholders._source_line', return_value=None):
            self.assertIsNone(deterministic_placeholder_reason(item, source_repo=Path('.'),
                target_commit='a'*40, config=config))

    def test_summary_keeps_advisory_details_and_escapes_html(self):
        findings = [{'path': 'a.py', 'line': i+1, 'title': 'review', 'level': 'advisory',
                     'evidence': '<script>sample</script>', 'remediation': 'verify'} for i in range(120)]
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.md'
            render_summary({'repository': 'test/project', 'findings': findings,
                            'scope': {'merge_base': 'a'*40, 'head': 'b'*40, 'changes': [], 'commits': []}}, summary)
            text = summary.read_text(encoding='utf-8')
            self.assertIn('第 120 行', text)
            self.assertNotIn('<script>', text)
            self.assertIn('&lt;script&gt;', text)

    def test_secrets_are_advisory_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            marker = 'SYNTHETIC_CREDENTIAL_NEVER_A_REAL_SECRET'
            path.write_text(json.dumps([{'RuleID': 'generic-api-key', 'File': 'example.py',
                                        'StartLine': 1, 'Secret': marker, 'Match': marker}]))
            findings, _ = parse_gitleaks(path)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]['level'], 'advisory')
            self.assertNotIn(marker, json.dumps(findings))

    def test_missing_or_malformed_secret_report_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            with self.assertRaises(ValueError):
                parse_gitleaks(path)
            path.write_text('{}')
            with self.assertRaises(ValueError):
                parse_gitleaks(path)

    def test_wording_is_not_a_blocker(self):
        policy = load_policy(ROOT / 'policies', 'any/project')
        scope = {'head': 'head', 'changes': [{'kind': 'A', 'path': 'src/hcu/runtime.py'}], 'changed_lines': {}}
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=b'print("AMD GPU with XGMI")\n'):
            findings, _ = scan_sensitive_diff(Path('.'), scope, policy)
        self.assertTrue(findings)
        self.assertTrue(all(f['level'] == 'advisory' for f in findings))
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', return_value=b'print("abcdamd")\n'):
            findings, _ = scan_sensitive_diff(Path('.'), scope, policy)
        self.assertEqual(findings, [])

    def test_ui_deduplicates_advisories_but_keeps_blockers(self):
        advisory = {'rule_id': 'TEST', 'path': 'a.py', 'level': 'advisory'}
        blocker = dict(advisory, level='blocker')
        data = {'findings': [dict(advisory, line=i) for i in range(100)] + [blocker]}
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            _emit_github_annotations(data)
        self.assertEqual(stream.getvalue().count('::warning '), 1)
        self.assertEqual(stream.getvalue().count('::error '), 1)
        self.assertEqual(len(data['findings']), 101)


if __name__ == '__main__':
    unittest.main()
