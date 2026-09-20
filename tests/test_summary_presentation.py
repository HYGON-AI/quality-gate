# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path
from hygon_pr_gate.render_summary import render_summary


class SummaryPresentationTests(unittest.TestCase):
    def render(self, **extra):
        data = dict(repository='test/repo', display_name='Checks',
                    scope=dict(merge_base='a'*40, head='b'*40, changes=[], commits=[]),
                    gate_version='v2.0.5-dev', gate_sha='c'*40)
        data.update(extra)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'summary.md'
            render_summary(data, path)
            return path.read_text(encoding='utf-8')

    def test_clean_is_concise_and_traceable(self):
        text = self.render()
        visible = text.split('<details>')[0]
        self.assertIn('本检查通过', visible)
        self.assertIn('v2.0.5-dev', visible)
        self.assertIn('c'*40, visible)
        self.assertNotIn('Repository /', visible)
        self.assertEqual(text.count('本检查通过'), 1)

    def test_no_target_scanner_row_is_not_marked_passed(self):
        text = self.render(statuses=[dict(scanner='ruff', state='not-applicable', detail='无 Python 变更')])
        self.assertIn('| Ruff | 无需检查 |', text)
        self.assertNotIn('| Ruff | Passed / 通过 |', text)

    def test_blockers_remain_outside_details(self):
        text = self.render(findings=[dict(level='blocker', title='broken syntax', path='a.py', line=3)])
        self.assertIn('broken syntax', text.split('</details>')[1])
        self.assertIn('第 3 行', text)

    def test_failed_and_partial_are_not_success(self):
        self.assertNotIn('本检查通过', self.render(operational_error='scanner failed'))
        self.assertNotIn('本检查通过', self.render(partial=True))

    def test_same_location_groups_without_losing_evidence(self):
        text = self.render(findings=[
            dict(level='blocker', path='a.yaml', line=2, title='native', evidence='evidence one'),
            dict(level='blocker', path='a.yaml', line=2, title='yamllint', evidence='evidence two')])
        self.assertEqual(text.count('### `a.yaml` 第 2 行'), 1)
        self.assertIn('evidence one', text)
        self.assertIn('evidence two', text)
        self.assertIn('Blockers / 阻断问题：2', text)


if __name__ == '__main__':
    unittest.main()
