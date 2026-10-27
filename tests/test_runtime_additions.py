# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Long build expressions must stay analyzable without bypassing scan limits."""
import ast
import unittest

from hygon_pr_gate.sensitive_diff_check import _PythonRuntimeVisitor


def visitor(text):
    return _PythonRuntimeVisitor(
        path_owned=True, source_text=text,
        added_lines=set(range(1, len(text.splitlines()) + 1)),
        markers=['hcu'], non_hcu_markers=['cuda'], runtime_terms=['amd'],
        allowed_patterns=[],
    )


class RuntimeAdditionTests(unittest.TestCase):
    def test_lightop_shaped_glob_chains(self):
        for additions in (27, 35, 150):
            with self.subTest(additions=additions):
                text = 'op_files = ' + ' + '.join(
                    'glob.glob("./csrc/part%d/*.cu")' % i
                    for i in range(additions + 1)) + '\n'
                v = visitor(text)
                v.visit(ast.parse(text))
                self.assertEqual(v.values['op_files'], [])
                self.assertEqual(v.matches, [])

    def test_long_literal_list_chain_is_not_a_string(self):
        text = 'files = ' + ' + '.join('["part%d.cu"]' % i for i in range(80))
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(v.values['files'], [])
        self.assertEqual(v.matches, [])

    def test_long_string_chain_still_detects_split_sensitive_word(self):
        text = 'message = ' + ' + '.join(['"am"'] + ['""'] * 80 + ['"d"'])
        text += '\nprint(message)\n'
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(v.values['message'][0][0], 'amd')
        self.assertTrue(any(match[2] == 'amd' for match in v.matches))

    def test_right_nested_additions_preserve_grouping(self):
        text = 'value = 10000000000000000.0 + (1.0 + 1.0)\n'
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertEqual(v.values['value'][0][0], 10000000000000002.0)

    def test_long_right_nested_strings_are_detected(self):
        expression = '"d"'
        for _ in range(70):
            expression = '"" + (' + expression + ')'
        text = 'print("am" + (' + expression + '))\n'
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertTrue(v.matches)

    def test_long_chain_preserves_incremental_origin(self):
        parts = ['    "am",'] + ['    "",'] * 35 + ['    "d",']
        text = 'message = (\n' + '\n'.join(p[:-1] + ' +' for p in parts[:-1])
        text += '\n' + parts[-1][:-1] + '\n)\nprint(message)\n'
        v = visitor(text)
        changed_line = len(parts) + 1
        v.added_lines = {changed_line}
        v.visit(ast.parse(text))
        self.assertIn(changed_line, v.values['message'][0][1])
        self.assertTrue(any(match[0] == changed_line for match in v.matches))

    def test_unknown_left_does_not_expand_right_candidates(self):
        text = 'result = unknown + "{}{}".format(choices, choices)\n'
        v = visitor(text)
        v.values['choices'] = [(str(i), frozenset({1})) for i in range(21)]
        v.visit(ast.parse(text))
        self.assertEqual(v.values['result'], [])

    def test_calls_inside_unknown_additions_are_still_visited(self):
        text = 'files = ' + ' + '.join(['unknown'] * 40 + ['producer(print("amd"))'])
        v = visitor(text)
        v.visit(ast.parse(text))
        self.assertTrue(v.matches)

    def test_addition_walk_does_not_depend_on_python_recursion_limit(self):
        expression = ast.Constant(value='am', lineno=1, end_lineno=1)
        for _ in range(1200):
            expression = ast.BinOp(
                left=expression, op=ast.Add(),
                right=ast.Constant(value='', lineno=1, end_lineno=1),
                lineno=1, end_lineno=1,
            )
        expression = ast.BinOp(
            left=expression, op=ast.Add(),
            right=ast.Constant(value='d', lineno=1, end_lineno=1),
            lineno=1, end_lineno=1,
        )
        call = ast.Call(func=ast.Name(id='print', ctx=ast.Load()),
                        args=[expression], keywords=[], lineno=1, end_lineno=1)
        v = visitor('print(message)\n')
        v.visit(call)
        self.assertTrue(v.matches)

    def test_long_additions_still_consume_work_budget(self):
        text = 'message = ' + ' + '.join(['"x"'] * 80)
        v = visitor(text)
        v.MAX_OPERATIONS = 40
        with self.assertRaisesRegex(RuntimeError, 'work/time'):
            v.visit(ast.parse(text))

    def test_long_strings_keep_size_limit(self):
        text = 'message = ' + ' + '.join([repr('x' * 1000)] * 70)
        with self.assertRaisesRegex(RuntimeError, 'string'):
            visitor(text).visit(ast.parse(text))

    def test_long_additions_keep_candidate_limit(self):
        text = 'message = ' + ' + '.join(['""'] * 35 + ['left', 'right'])
        v = visitor(text)
        v.values['left'] = [('left%d_' % i, frozenset({1})) for i in range(21)]
        v.values['right'] = [('right%d' % i, frozenset({1})) for i in range(21)]
        with self.assertRaisesRegex(RuntimeError, 'candidates'):
            v.visit(ast.parse(text))

    def test_non_addition_nesting_keeps_depth_limit(self):
        text = 'value = ' + '"{}".format(' * 25 + '"amd"' + ')' * 25
        with self.assertRaisesRegex(RuntimeError, 'expression depth'):
            visitor(text).visit(ast.parse(text))


if __name__ == '__main__':
    unittest.main()
