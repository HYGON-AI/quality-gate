# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Independent governance cases using real, unpublished Git commits."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from hygon_pr_gate.git_scope import collect_scope
from hygon_pr_gate.native_checks import scan_identity, scan_compliance
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.render_summary import render_summary
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff
from hygon_pr_gate.sensitive_diff_check import _term_matches

ROOT = Path(__file__).resolve().parents[1]
HEADER = '# Copyright (c) 2026 Hygon Information Technology Co., Ltd.\n'
SPDX = '# SPDX-License-Identifier: Apache-2.0\n'
UPSTREAM = '# Copyright (c) Original Upstream Author\n'
FORBIDDEN = 'su' + 'gon'


class CoreGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='core-gate-')
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.autocrlf', 'false')
        self.write('base.py', UPSTREAM + SPDX + 'VALUE = 1\n')
        self.base = self.commit()
        self.policy = load_policy(ROOT / 'policies', 'HYGON-AI/sglang-das')

    def git(self, *args, env=None):
        return subprocess.check_output(['git', '-C', str(self.repo), *args],
                                       env=env, stderr=subprocess.PIPE).decode().strip()

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def commit(self, **fields):
        env = os.environ.copy()
        for role in ('AUTHOR', 'COMMITTER'):
            env['GIT_' + role + '_NAME'] = fields.get(role.lower() + '_name', 'Synthetic Fixture')
            env['GIT_' + role + '_EMAIL'] = fields.get(role.lower() + '_email', 'fixture@example.invalid')
        self.git('add', '.', env=env)
        self.git('commit', '-q', '--allow-empty', '-m', fields.get('subject', 'test: synthetic case'),
                 '-m', fields.get('body', 'Synthetic regression only.'), env=env)
        return self.git('rev-parse', 'HEAD')

    def check(self, scanner, expected, head=None, line=None, path=None, title=None):
        head = head or self.commit()
        scope = collect_scope(self.repo, self.base, head)
        findings, status = scanner(self.repo, scope, self.policy)
        self.assertEqual([(f['rule_id'], f['level']) for f in findings], expected)
        for item in findings:
            if line is not None:
                self.assertEqual(item.get('line'), line)
            if path is not None:
                self.assertEqual(item['path'], path)
        output = self.repo / 'case-summary.md'
        render_summary(dict(repository='synthetic/unpublished', scope=scope,
                            display_name=self._testMethodName, findings=findings,
                            statuses=[status]), output)
        summary = output.read_text(encoding='utf-8')
        self.assertIn('Blockers / 阻断问题：{}'.format(sum(f['level'] == 'blocker' for f in findings)), summary)
        self.assertIn('Advisories / 提示问题：{}'.format(sum(f['level'] == 'advisory' for f in findings)), summary)
        if path:
            self.assertIn(path, summary)
        if line:
            self.assertIn('`{}` 第 {} 行'.format(path, line), summary)
        if title:
            self.assertIn(title, summary)
        report = os.environ.get('GITHUB_STEP_SUMMARY')
        if report and os.environ.get('CORE_GOVERNANCE_SUMMARIES') == '1':
            with open(report, 'a', encoding='utf-8') as stream:
                stream.write('\n<details><summary>PASS: {} — synthetic expected-result test</summary>\n\n{}\n\n</details>\n'.format(self._testMethodName, summary))
        return findings, summary

    def test_header_valid_hygon(self):
        self.write('good.py', HEADER + SPDX + 'VALUE = 1\n')
        self.check(scan_compliance, [])

    def test_header_valid_upstream(self):
        self.write('good.py', UPSTREAM + SPDX + 'VALUE = 1\n')
        self.check(scan_compliance, [])

    def test_header_missing_spdx_blocks(self):
        self.write('bad.py', HEADER + 'VALUE = 1\n')
        self.check(scan_compliance, [('COPYRIGHT.NEW_HYGON_SOURCE_SPDX_MISSING', 'blocker')], path='bad.py')

    def test_header_unclassified_is_advisory(self):
        self.write('unknown.py', 'VALUE = 1\n')
        self.check(scan_compliance, [('COPYRIGHT.NEW_SOURCE_HEADER_REVIEW', 'advisory')], path='unknown.py')

    def test_header_unapproved_license_blocks(self):
        self.write('bad.py', HEADER + '# SPDX-License-Identifier: GPL-3.0-only\nVALUE = 1\n')
        self.check(scan_compliance, [('LICENSE.UNSUPPORTED_PR_FILE', 'blocker')], path='bad.py', line=2)

    def test_header_preserved_with_addition(self):
        self.write('base.py', UPSTREAM + HEADER + SPDX + 'VALUE = 2\n')
        self.check(scan_compliance, [])

    def test_header_replaced_blocks(self):
        self.write('base.py', HEADER + SPDX + 'VALUE = 2\n')
        self.check(scan_compliance, [('COPYRIGHT.ORIGINAL_HEADER_REMOVED', 'blocker')], path='base.py')

    def test_identity_earlier_bad_commit_still_detected(self):
        bad = self.commit(subject='test: ' + FORBIDDEN)
        head = self.commit()
        findings, summary = self.check(scan_identity, [('IDENTITY.FORBIDDEN_COMMIT_SUBJECT', 'blocker')], head=head)
        self.assertEqual(findings[0]['commit'], bad)
        self.assertIn(bad[:12], summary)

    def test_wording_amd_output_is_advisory(self):
        self.write('src/hcu/runtime.py', 'print("AMD GPU with XGMI")\n')
        self.check(scan_sensitive_diff, [('SENSITIVE_DIFF.HCU_RUNTIME_WORDING', 'advisory')] * 2, path='src/hcu/runtime.py', line=1)

    def test_wording_mixed_case_is_advisory(self):
        self.write('src/hcu/runtime.py', 'print("AmD GPU with XgMi")\n')
        self.check(scan_sensitive_diff, [('SENSITIVE_DIFF.HCU_RUNTIME_WORDING', 'advisory')] * 2, path='src/hcu/runtime.py', line=1)

    def test_identity_added_content_blocks_at_exact_line(self):
        self.write('src/identity.py', HEADER + SPDX + 'VALUE = "' + FORBIDDEN + '"\n')
        self.check(scan_identity, [('IDENTITY.FORBIDDEN_CONTENT', 'blocker')], path='src/identity.py', line=3)

    def test_identity_unchanged_historical_content_allowed(self):
        self.write('src/identity.py', 'VALUE = "' + FORBIDDEN + '"\nOTHER = 1\n')
        self.base = self.commit()
        self.write('src/identity.py', 'VALUE = "' + FORBIDDEN + '"\nOTHER = 2\n')
        self.check(scan_identity, [])

    def test_wording_identifiers_comments_allowed(self):
        self.write('src/compat.py', '# AMD XGMI compatibility\nAMDGPU_TARGETS = "gfx"\nCPU = "amd64"\n')
        self.check(scan_sensitive_diff, [])

    def test_wording_incidental_substring_allowed(self):
        self.write('src/hcu/runtime.py', 'print("abcdamd")\n')
        self.check(scan_sensitive_diff, [])

    def test_wording_case_fix_keeps_word_boundaries(self):
        for word in ('AmD', 'aMd', 'amd', 'AMD', 'XgMi', 'xGmI'):
            with self.subTest(word=word):
                self.assertEqual(len(_term_matches(word, ['amd', 'xgmi'])), 1)
        for word in ('amd64', 'abcdamd', 'xgmi2', 'examplexgmi', 'AmD64'):
            with self.subTest(word=word):
                self.assertEqual(_term_matches(word, ['amd', 'xgmi']), [])

    def test_wording_unchanged_legacy_not_reported(self):
        self.write('src/hcu/runtime.py', 'print("AMD GPU with XGMI")\nVALUE = 1\n')
        self.base = self.commit()
        self.write('src/hcu/runtime.py', 'print("AMD GPU with XGMI")\nVALUE = 2\n')
        self.check(scan_sensitive_diff, [])


def metadata_case(field, value, blocked, title):
    def test(self):
        head = self.commit(**{field: value})
        expected = [('IDENTITY.FORBIDDEN_COMMIT_' + field.upper(), 'blocker')] if blocked else []
        findings, summary = self.check(scan_identity, expected, head=head, title=title if blocked else None)
        if blocked:
            self.assertEqual(findings[0]['commit'], head)
            self.assertIn(head[:12], summary)
    return test


for field, title in [('author_email', '作者邮箱'), ('committer_email', '提交者邮箱'),
                     ('subject', 'Commit 标题'), ('body', 'Commit 正文')]:
    for label, value in [('hygon', 'developer@hygon.com'), ('public', '123+fixture@users.noreply.github.com')]:
        setattr(CoreGovernanceTests, 'test_' + field + '_allows_' + label,
                metadata_case(field, value, False, title))
    for label, word in [('first', FORBIDDEN), ('mixed_case', ('ro' + 'gon').upper())]:
        value = 'fixture@' + word + '.invalid' if field.endswith('email') else 'test: synthetic ' + word
        setattr(CoreGovernanceTests, 'test_' + field + '_blocks_' + label,
                metadata_case(field, value, True, title))


def license_template_case(license_id, category, upstream_header):
    def test(self):
        spdx = '# SPDX-License-Identifier: ' + license_id + '\n'
        modified = '# Modified by Hygon Information Technology Co., Ltd., 2026.\n'
        if category == 'H1':
            self.write('new.py', HEADER + spdx + 'VALUE = 1\n')
        else:
            original = UPSTREAM + spdx if upstream_header else ''
            self.write('base.py', original + 'VALUE = 1\n')
            self.base = self.commit()
            addition = ''
            if license_id == 'Apache-2.0':
                addition = HEADER + ('' if upstream_header else spdx) + modified if category == 'H2' else modified
            self.write('base.py', original + addition + 'VALUE = 2\n')
            if license_id != 'Apache-2.0' and category == 'H2':
                self.write('NOTICE', 'HYGON original contributions recorded for synthetic test.\n')
        self.check(scan_compliance, [])
    return test


for license_id in ('Apache-2.0', 'MIT', 'BSD-3-Clause'):
    for category in ('H1', 'H2', 'H3'):
        setattr(CoreGovernanceTests, 'test_template_' + license_id.replace('-', '_').replace('.', '_') + '_' + category,
                license_template_case(license_id, category, True))
for category in ('H2', 'H3'):
    setattr(CoreGovernanceTests, 'test_template_Apache_no_upstream_header_' + category,
            license_template_case('Apache-2.0', category, False))


if __name__ == '__main__':
    unittest.main()
