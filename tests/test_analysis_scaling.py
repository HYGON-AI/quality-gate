# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Analysis joins must scale without changing values, origins or limits."""
import ast
import itertools
import unittest

from hygon_pr_gate.sensitive_diff_check import _PythonRuntimeVisitor


def visitor(text):
    return _PythonRuntimeVisitor(
        path_owned=True, source_text=text,
        added_lines=set(range(1, len(text.splitlines()) + 1)),
        markers=['hcu'], non_hcu_markers=['cuda'], runtime_terms=['amd'],
        allowed_patterns=[],
    )


class AnalysisScalingTests(unittest.TestCase):
    def test_many_bindings_and_unchanged_branches_fit_existing_budget(self):
        text = ''.join('value_%d = "constant"\n' % i for i in range(1300))
        text += 'if condition: pass\n' * 200
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(v.MAX_OPERATIONS, 500000)
        self.assertLess(v.operations, 350000)
        self.assertEqual(v.values['value_0'], [('constant', frozenset({1}))])

    def test_many_bindings_and_loops_fit_existing_budget(self):
        text = ''.join('value_%d = "constant"\n' % i for i in range(1300))
        text += ('for item in items: pass\nwhile condition: pass\n') * 100
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertLess(v.operations, 350000)

    def test_changed_equal_strings_keep_both_origins(self):
        text = 'value = "amd"\nif condition:\n    value = "amd"\nprint(value)\n'
        v = visitor(text)
        v.added_lines = {3}
        v.visit(ast.parse(text))
        self.assertEqual(v.values['value'], [('amd', frozenset({1, 3}))])
        self.assertTrue(any(match[0] == 3 for match in v.matches))

    def test_shared_binding_remains_immutable_across_later_join(self):
        v = visitor('')
        original = [('amd', frozenset({1}))]
        shared = v._merge({'x': original}, {'x': original})
        changed = v._merge(shared, {'x': [('hcu', frozenset({2}))]})
        self.assertEqual(original, [('amd', frozenset({1}))])
        self.assertEqual(changed['x'], [('amd', frozenset({1})), ('hcu', frozenset({2}))])

    def test_join_matches_reference_for_typed_and_missing_states(self):
        # Equal Python values can have different types; list equality is not
        # sufficient to decide that two branch states are interchangeable.
        v = visitor('')
        cases = [[], [(True, frozenset({1}))], [(1, frozenset({1}))],
                 [('amd', frozenset({1}))], [('amd', frozenset({2}))],
                 [('hcu', frozenset({3})), ('amd', frozenset({4}))]]
        for left_values, right_values in itertools.product(cases, repeat=2):
            for missing in (None, 'left', 'right'):
                left = {} if missing == 'left' else {'x': left_values}
                right = {} if missing == 'right' else {'x': right_values}
                expected = {key: v._bounded(itertools.chain(left.get(key, ()), right.get(key, ())))
                            for key in left.keys() | right.keys()}
                actual = v._merge(left, right)
                signature = lambda rows: [(type(value), value, origins) for value, origins in rows]
                self.assertEqual(set(actual), set(expected))
                for key in expected:
                    self.assertEqual(signature(actual[key]), signature(expected[key]))

    def test_changed_candidates_still_exhaust_limit(self):
        text = 'value = "start"\n' + ''.join('if condition: value = "v%d"\n' % i for i in range(300))
        with self.assertRaisesRegex(RuntimeError, 'candidates'):
            visitor(text).visit(ast.parse(text))

    def test_join_work_remains_budgeted(self):
        v = visitor('')
        v.MAX_OPERATIONS = 5
        state = {'x%d' % i: [('same', frozenset({1}))] for i in range(20)}
        with self.assertRaisesRegex(RuntimeError, 'work/time'):
            v._merge(state, state)


if __name__ == '__main__':
    unittest.main()
