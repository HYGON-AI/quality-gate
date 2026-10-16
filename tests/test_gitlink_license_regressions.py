# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Regression fixtures for Gitlinks and compound SPDX header changes."""

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.git_scope import collect_scope
from hygon_pr_gate.license_expressions import parse_expression, preserves_expression
from hygon_pr_gate.native_checks import scan_compliance
from hygon_pr_gate.policy import _validate_central_policy, load_policy
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff


ROOT = Path(__file__).resolve().parents[1]
HYGON = '# Copyright (c) 2026 Hygon Information Technology Co., Ltd.\n'
HEADER = HYGON + '# SPDX-License-Identifier: MIT\n'


class ExpressionTests(unittest.TestCase):
    def test_commutative_order_parentheses_and_association(self):
        self.assertEqual(parse_expression('MIT AND (Apache-2.0 AND BSD-3-Clause)'),
                         parse_expression('BSD-3-Clause AND MIT AND Apache-2.0'))
        self.assertEqual(parse_expression('MIT AND MIT'), parse_expression('MIT'))

    def test_and_has_higher_precedence_than_or(self):
        self.assertEqual(parse_expression('MIT OR Apache-2.0 AND BSD-3-Clause'),
                         parse_expression('MIT OR (Apache-2.0 AND BSD-3-Clause)'))
        self.assertNotEqual(parse_expression('(MIT OR Apache-2.0) AND BSD-3-Clause'),
                            parse_expression('MIT OR Apache-2.0 AND BSD-3-Clause'))

    def test_with_and_license_references_are_not_plain_license_ids(self):
        self.assertNotEqual(parse_expression('MIT WITH Example-exception'), parse_expression('MIT'))
        self.assertEqual(parse_expression('DocumentRef-upstream:LicenseRef-custom')[0], 'license')
        self.assertEqual(parse_expression('GPL-2.0+')[1], 'GPL-2.0+')

    def test_invalid_and_bounded_inputs(self):
        for value in ('', 'MIT AND', 'MIT OR OR MIT', '(MIT', 'MIT)',
                      '(MIT OR Apache-2.0) WITH Example', 'MIT WITH',
                      'MIT WITH Example+', 'MIT WITH LicenseRef-custom',
                      'MIT;Apache-2.0', 'MIT and Apache-2.0', 'MIT++',
                      'x' * 4097, ' AND '.join(['MIT'] * 130),
                      '(' * 34 + 'MIT' + ')' * 34):
            with self.subTest(value=value[:100]), self.assertRaises(ValueError):
                parse_expression(value)

    def test_retention_is_not_a_license_id_substring_check(self):
        old = parse_expression('MIT')
        self.assertTrue(preserves_expression(old, parse_expression('Apache-2.0 AND MIT')))
        for value in ('Apache-2.0 OR MIT', 'MIT WITH Example-exception',
                      'LicenseRef-MIT', 'Apache-2.0'):
            self.assertFalse(preserves_expression(old, parse_expression(value)))
        self.assertFalse(preserves_expression(parse_expression('MIT AND Apache-2.0'), old))


class LicenseAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy(ROOT / 'policies', 'test/repo')

    def scan(self, old, new, approved=()):
        policy = copy.deepcopy(self.policy)
        policy['open_source']['license_admission']['approved_expressions'] = list(approved)
        scope = dict(head='head', merge_base='base', commits=[],
                     changed_lines={'source.py': set(range(1, 100))},
                     changes=[dict(kind='A' if old is None else 'M', path='source.py')])
        def read(repo, ref, name, maximum):
            text = new if ref == 'head' else old
            return text.encode() if text is not None else None
        with patch('hygon_pr_gate.native_checks.read_blob', side_effect=read):
            findings, _ = scan_compliance(Path('.'), scope, policy)
        return findings

    def test_default_does_not_approve_compound_or_unknown_licenses(self):
        self.assertEqual(self.policy['open_source']['license_admission']['approved_expressions'], [])
        for expression in ('MIT AND Apache-2.0', 'MIT OR Apache-2.0',
                           'MIT WITH Example-exception', 'MIT AND LicenseRef-custom'):
            findings = self.scan(None, HYGON + '# SPDX-License-Identifier: ' + expression + '\n')
            self.assertEqual([f['rule_id'] for f in findings], ['LICENSE.UNSUPPORTED_PR_FILE'])
            self.assertEqual(findings[0]['level'], 'blocker')

    def test_aiter_header_no_longer_claims_copyright_was_removed(self):
        new = '# SPDX-License-Identifier: Apache-2.0 AND MIT\n# Copyright 2023-2024 SGLang Team\n' + HYGON
        findings = self.scan(HEADER, new)
        self.assertEqual([f['rule_id'] for f in findings], ['LICENSE.UNSUPPORTED_PR_FILE'])
        self.assertIn('复合许可证', findings[0]['title'])

    def test_only_explicitly_reviewed_combination_can_pass(self):
        new = HYGON + '# SPDX-License-Identifier: (Apache-2.0 AND MIT)\n'
        self.assertEqual(self.scan(HEADER, new, ['MIT AND Apache-2.0']), [])
        changed_operator = HYGON + '# SPDX-License-Identifier: Apache-2.0 OR MIT\n'
        rules = [f['rule_id'] for f in self.scan(HEADER, changed_operator, ['MIT AND Apache-2.0'])]
        self.assertIn('LICENSE.UNSUPPORTED_PR_FILE', rules)
        self.assertIn('LICENSE.ORIGINAL_SPDX_CHANGED', rules)

    def test_actual_copyright_removal_still_blocks(self):
        findings = self.scan(HEADER, '# SPDX-License-Identifier: Apache-2.0 AND MIT\n',
                             ['MIT AND Apache-2.0'])
        self.assertIn('COPYRIGHT.ORIGINAL_HEADER_REMOVED', [f['rule_id'] for f in findings])

    def test_spdx_removal_and_replacement_have_specific_diagnostics(self):
        self.assertEqual([f['rule_id'] for f in self.scan(HEADER, HYGON)],
                         ['LICENSE.ORIGINAL_SPDX_REMOVED'])
        self.assertEqual([f['rule_id'] for f in self.scan(HEADER, HYGON + '# SPDX-License-Identifier: Apache-2.0\n')],
                         ['LICENSE.ORIGINAL_SPDX_CHANGED'])

    def test_invalid_syntax_is_not_a_legal_approval_candidate(self):
        for expression in ('MIT AND', ''):
            findings = self.scan(None, HYGON + '# SPDX-License-Identifier: ' + expression + '\n')
            self.assertEqual([f['rule_id'] for f in findings], ['LICENSE.INVALID_SPDX_EXPRESSION'])

    def test_and_cannot_discard_original_compound_terms(self):
        old = HYGON + '# SPDX-License-Identifier: Apache-2.0 AND MIT\n'
        self.assertIn('LICENSE.ORIGINAL_SPDX_CHANGED', [f['rule_id'] for f in self.scan(old, HEADER)])

    def test_explicit_policy_is_validated_without_expanding_default_license_set(self):
        policy = copy.deepcopy(self.policy)
        policy['open_source']['license_admission']['approved_expressions'] = ['Apache-2.0 AND MIT']
        _validate_central_policy(policy, policy['open_source'])
        for values in ('MIT AND Apache-2.0', ['MIT'], ['MIT AND GPL-3.0-only'],
                       ['MIT WITH Example-exception'], ['MIT AND']):
            policy['open_source']['license_admission']['approved_expressions'] = values
            with self.subTest(values=values), self.assertRaises(ValueError):
                _validate_central_policy(policy, policy['open_source'])


class GitlinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gitlink-gate-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.autocrlf', 'false')
        self.write('base.py', HEADER + 'VALUE = 1\n')
        self.policy = load_policy(ROOT / 'policies', 'test/repo')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, path, text):
        p = self.repo/path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        self.git('add', path)

    def link(self, path, oid):
        self.git('update-index', '--add', '--cacheinfo', '160000,' + oid + ',' + path)

    def commit(self):
        self.git('commit', '-q', '-m', 'test: synthetic Gitlink fixture')
        return self.git('rev-parse', 'HEAD')

    def test_two_missing_submodule_objects_do_not_invalidate_parent_text_scan(self):
        paths = ('3rdparty/composable_kernel', '3rdparty/moe_c')
        for path in paths:
            self.link(path, '1' * 40)
        base = self.commit()
        for path in paths:
            self.link(path, '2' * 40)
        head = self.commit()
        scope = collect_scope(self.repo, base, head)
        self.assertEqual(len(scope['changes']), 2)
        self.assertTrue(all(c['old_mode'] == c['new_mode'] == '160000' for c in scope['changes']))
        with patch('hygon_pr_gate.sensitive_diff_check.read_blob', side_effect=AssertionError('must not read Gitlinks')):
            findings, status = scan_sensitive_diff(self.repo, scope, self.policy)
        self.assertEqual(findings, [])
        self.assertEqual(status['state'], 'passed')
        self.assertIn('本次未扫描子模块内部源码', status['detail'])
        self.assertIn('1' * 40, status['detail'])
        self.assertIn('2' * 40, status['detail'])

    def test_new_gitlink_path_is_still_checked(self):
        base = self.commit()
        self.link('vendor/dcu_backend', '3' * 40)
        head = self.commit()
        findings, status = scan_sensitive_diff(self.repo, collect_scope(self.repo, base, head), self.policy)
        self.assertEqual(status['state'], 'findings')
        self.assertEqual([f['rule_id'] for f in findings], ['SENSITIVE_DIFF.LEGACY_DCU_PATH'])
        self.assertEqual(findings[0]['level'], 'advisory')

    def test_gitlink_to_regular_file_is_not_skipped(self):
        self.link('3rdparty/component.py', '4' * 40)
        base = self.commit()
        self.git('update-index', '--force-remove', '3rdparty/component.py')
        self.write('3rdparty/component.py', 'print("AMD")\n')
        head = self.commit()
        scope = collect_scope(self.repo, base, head)
        change = next(c for c in scope['changes'] if c['path'] == '3rdparty/component.py')
        self.assertEqual((change['old_mode'], change['new_mode']), ('160000', '100644'))
        findings, _ = scan_sensitive_diff(self.repo, scope, self.policy)
        self.assertTrue(any(f['rule_id'] == 'SENSITIVE_DIFF.HCU_RUNTIME_WORDING' for f in findings))

    def test_regular_file_to_gitlink_is_not_read_as_text(self):
        self.write('3rdparty/component.py', 'VALUE = 1\n')
        base = self.commit()
        self.git('update-index', '--force-remove', '3rdparty/component.py')
        self.link('3rdparty/component.py', '5' * 40)
        head = self.commit()
        findings, status = scan_sensitive_diff(self.repo, collect_scope(self.repo, base, head), self.policy)
        self.assertEqual(findings, [])
        self.assertEqual(status['state'], 'passed')

    def test_deleted_and_renamed_gitlinks_keep_valid_scope(self):
        self.link('old-component', '6' * 40)
        self.link('deleted-component', '7' * 40)
        base = self.commit()
        self.git('update-index', '--force-remove', 'old-component', 'deleted-component')
        self.link('renamed-component', '6' * 40)
        head = self.commit()
        scope = collect_scope(self.repo, base, head)
        self.assertEqual({c['kind'] for c in scope['changes']}, {'D', 'R'})
        findings, status = scan_sensitive_diff(self.repo, scope, self.policy)
        self.assertEqual(findings, [])
        self.assertEqual(status['state'], 'passed')


if __name__ == '__main__':
    unittest.main()
