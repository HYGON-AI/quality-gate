# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Presentation-only notice changes must not hide substantive removals."""
import unittest
import textwrap
from pathlib import Path
from unittest.mock import patch

from hygon_pr_gate.native_checks import scan_compliance
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.header_notices import MIT_NOTICE, BSD_NOTICE, APACHE_NOTICE

ROOT = Path(__file__).resolve().parents[1]


class HeaderPreservationTests(unittest.TestCase):
    def scan(self, old, new, path='source.py'):
        scope = dict(head='head', merge_base='base', commits=[],
                     changed_lines={path: set(range(1, 200))},
                     changes=[dict(kind='A' if old is None else 'M', path=path)])
        def read(repo, ref, name, maximum):
            text = new if ref == 'head' else old
            return text.encode() if text is not None else None
        with patch('hygon_pr_gate.native_checks.read_blob', side_effect=read):
            findings, _ = scan_compliance(Path('.'), scope, load_policy(ROOT / 'policies', 'test/repo'))
        return findings

    def test_copyright_reflow_and_comment_wrapper(self):
        old = '# Copyright (c) 2026 Original Author Company.\n# SPDX-License-Identifier: MIT\n'
        new = '/* Copyright (c) 2026\n * Original Author Company.\n * SPDX-License-Identifier: MIT\n */\n'
        self.assertEqual(self.scan(old, new), [])

    def test_doxygen_comment_wrapper(self):
        old = '# Copyright Original Author\n# SPDX-License-Identifier: MIT\n'
        new = '/** Copyright Original Author\n * SPDX-License-Identifier: MIT\n */\n'
        self.assertEqual(self.scan(old, new), [])

    def test_reflowed_original_holder_cannot_be_deleted(self):
        old = '# Copyright (c) 2026\n# Original Author Company.\n# SPDX-License-Identifier: MIT\n'
        new = '# Copyright (c) 2026\n# SPDX-License-Identifier: MIT\n'
        self.assertIn('COPYRIGHT.ORIGINAL_HEADER_REMOVED', [f['rule_id'] for f in self.scan(old, new)])

    def test_root_legal_reflow(self):
        self.assertEqual(self.scan('Original legal terms\nremain here.\n', 'Original legal\nterms remain here.\n', 'LICENSE'), [])

    def test_root_legal_word_deleted(self):
        self.assertTrue(self.scan('Original legal terms\nremain here.\n', 'Original terms remain here.\n', 'LICENSE'))

    def test_root_legal_negation_inserted(self):
        self.assertTrue(self.scan('Redistribution is permitted.', 'Redistribution is not permitted.', 'LICENSE'))

    def test_license_name_only_is_not_approved(self):
        findings = self.scan(None, '# Copyright Original Author\n# Licensed under MIT\n')
        self.assertEqual([f['level'] for f in findings], ['advisory'])

    def test_license_in_code_string_is_not_header(self):
        text = '# Copyright Original Author\nvalue = """' + MIT_NOTICE + '"""\n'
        self.assertEqual([f['level'] for f in self.scan(None, text)], ['advisory'])

    def test_commented_notice_inside_code_string_is_not_header(self):
        text = '# Copyright Original Author\nvalue = """\n' + render_notice(MIT_NOTICE) + '\n"""\n'
        self.assertEqual([f['level'] for f in self.scan(None, text)], ['advisory'])

    def test_unknown_traditional_is_advisory(self):
        self.assertEqual([f['level'] for f in self.scan(None, '# Copyright Original Author\n# Licensed under Custom-License\n')], ['advisory'])

    def test_removed_spdx_does_not_hide_behind_body(self):
        body = render_notice(MIT_NOTICE)
        self.assertIn('COPYRIGHT.ORIGINAL_HEADER_REMOVED', [f['rule_id'] for f in self.scan('# SPDX-License-Identifier: MIT\n' + body, body)])

    def test_holder_substring_does_not_count_as_preserved(self):
        self.assertTrue(self.scan('# Copyright Owner\n# SPDX-License-Identifier: MIT\n', '# Copyright OwnerTwo\n# SPDX-License-Identifier: MIT\n'))

    def test_bsd_bullets_accepted(self):
        body = BSD_NOTICE.replace('1. ', '* ').replace('2. ', '* ').replace('3. ', '* ')
        self.assertEqual(self.scan(None, render_notice(body)), [])

    def test_apache_https_accepted(self):
        self.assertEqual(self.scan(None, render_notice(APACHE_NOTICE.replace('http://', 'https://'))), [])

    def test_hygon_traditional_without_spdx_accepted(self):
        text = render_notice(MIT_NOTICE).replace('Original Author', '(c) 2026 Hygon Information Technology Co., Ltd.')
        self.assertEqual(self.scan(None, text), [])

    def test_docstring_traditional_accepted(self):
        self.assertEqual(self.scan(None, '"""Copyright Original Author\n\n' + MIT_NOTICE + '\n"""\n'), [])

    def test_traditional_without_holder_is_advisory(self):
        text = render_notice(MIT_NOTICE).replace('# Copyright Original Author\n', '')
        self.assertEqual([f['level'] for f in self.scan(None, text)], ['advisory'])


def render_notice(body):
    return '# Copyright Original Author\n#\n' + '\n'.join('# ' + line for line in body.splitlines()) + '\n'


def notice_case(body, variant):
    def test(self):
        original = render_notice(body)
        if variant == 'complete':
            self.assertEqual(self.scan(None, original), [])
        elif variant == 'reflow':
            wrapped = textwrap.fill(' '.join(body.split()), width=65)
            current = '/* Copyright Original Author\n *\n' + '\n'.join(' * ' + line for line in wrapped.splitlines()) + '\n */\n'
            self.assertEqual(self.scan(original, current), [])
        elif variant == 'partial':
            self.assertEqual([f['level'] for f in self.scan(None, render_notice(body[:len(body)//2]))], ['advisory'])
        elif variant == 'body_removed':
            current = '# Copyright Original Author\n# SPDX-License-Identifier: MIT\n'
            findings = self.scan(original, current)
            self.assertIn('LICENSE.ORIGINAL_NOTICE_REMOVED', [f['rule_id'] for f in findings])
        elif variant == 'word_deleted':
            # A legal term is removed, not merely a Copyright/SPDX marker.
            current = original.replace('MERCHANTABILITY', '').replace('WARRANTIES', '')
            self.assertIn('LICENSE.ORIGINAL_NOTICE_REMOVED', [f['rule_id'] for f in self.scan(original, current)])
        elif variant == 'holder_removed':
            self.assertIn('COPYRIGHT.ORIGINAL_HEADER_REMOVED', [f['rule_id'] for f in self.scan(original, original.replace('# Copyright Original Author\n', ''))])
    return test


for license_id, body in [('MIT', MIT_NOTICE), ('BSD', BSD_NOTICE), ('Apache', APACHE_NOTICE)]:
    for variant in ('complete', 'reflow', 'partial', 'body_removed', 'word_deleted', 'holder_removed'):
        setattr(HeaderPreservationTests, 'test_' + license_id + '_' + variant, notice_case(body, variant))


if __name__ == '__main__':
    unittest.main()
