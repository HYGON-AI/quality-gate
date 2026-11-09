# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Only visible consumers should fail on bounded candidate-count overflow."""
import ast
import unittest

from hygon_pr_gate.sensitive_diff_check import _PythonRuntimeVisitor


def kernel_name():
    return 'name = "kernel"\n' + ''.join(
        'if flag_%d:\n    name += "_feature%d"\n' % (i, i)
        for i in range(12))


def visitor(text, added=None):
    return _PythonRuntimeVisitor(
        path_owned=True, source_text=text,
        added_lines=set(range(1, len(text.splitlines()) + 1)) if added is None else added,
        markers=['hcu'], non_hcu_markers=['cuda'], runtime_terms=['amd', 'xgmi'],
        allowed_patterns=[],
    )


class RuntimeCandidateTests(unittest.TestCase):
    def scan(self, text, added=None):
        v = visitor(text, added)
        v.visit(ast.parse(text))
        return v

    def test_unused_kernel_names_do_not_invalidate_scan(self):
        text = 'def kernel():\n' + ''.join('    ' + line + '\n' for line in
                                               (kernel_name() + 'return name\n').splitlines())
        v = self.scan(text)
        self.assertEqual(v.matches, [])
        self.assertLess(v.operations, 30000)
        self.assertEqual(v.MAX_VALUES, 256)

    def test_independent_output_after_overflow_is_still_checked(self):
        v = self.scan(kernel_name() + 'print("am" + "d")\n')
        self.assertTrue(any(m[2] == 'amd' for m in v.matches))

    def test_overwritten_value_is_fully_checked(self):
        for assignment in ('name = "amd"', 'name: str = "amd"'):
            with self.subTest(assignment=assignment):
                v = self.scan(kernel_name() + assignment + '\nprint(name)\n')
                self.assertTrue(any(m[2] == 'amd' for m in v.matches))

    def test_propagation_remains_fail_closed_at_output(self):
        cases = [
            'print(name)', 'logger.warning(name)', 'raise ValueError(name)',
            'assert condition, name', 'parser.add_argument("--x", help=name)',
            'ArgumentParser(description=name)', 'print("ok", end=name)',
            'alias = name\nprint(alias)', 'alias: str = name\nprint(alias)',
            'name += "suffix"\nprint(name)',
            'alias = f"prefix {name}"\nprint(alias)',
            'alias = "{}".format(name)\nprint(alias)',
            'alias = "prefix" + name\nprint(alias)',
            'alias = name + "suffix"\nprint(alias)',
            'if condition: name = "safe"\nprint(name)',
            'if condition:\n    alias = name\nelse:\n    alias = "safe"\nprint(alias)',
            'for item in items: name = "safe"\nprint(name)',
            'while condition: name = "safe"\nprint(name)',
        ]
        for tail in cases:
            with self.subTest(tail=tail):
                with self.assertRaisesRegex(RuntimeError, 'candidates'):
                    self.scan(kernel_name() + tail + '\n')

    def test_overflow_introduced_inside_branch_or_loop_propagates(self):
        for header in ('if condition:', 'for item in items:', 'while condition:'):
            with self.subTest(header=header):
                body = ''.join('    ' + line + '\n' for line in kernel_name().splitlines())
                with self.assertRaisesRegex(RuntimeError, 'candidates'):
                    self.scan('name = "safe"\n' + header + '\n' + body + 'print(name)\n')

    def test_both_branches_overwrite_overflow(self):
        v = self.scan(kernel_name() + 'if condition: name = "amd"\nelse: name = "hcu"\nprint(name)\n')
        self.assertTrue(v.matches)

    def test_ordinary_values_preserve_incremental_origins(self):
        text = kernel_name() + 'message = "am" + "d"\nprint(message)\n'
        line = len(text.splitlines()) - 1
        v = self.scan(text, {line})
        self.assertTrue(any(m[0] == line and m[2] == 'amd' for m in v.matches))

    def test_direct_expression_overflow_still_fails(self):
        v = visitor('print(left + right)\n')
        v.values['left'] = [('left%d_' % i, frozenset({1})) for i in range(20)]
        v.values['right'] = [('right%d' % i, frozenset({1})) for i in range(20)]
        with self.assertRaisesRegex(RuntimeError, 'candidates'):
            v.visit(ast.parse('print(left + right)\n'))

    def test_candidate_boundary_is_unchanged(self):
        for count in (256, 257):
            with self.subTest(count=count):
                v = visitor('')
                values = [(str(i), frozenset({1})) for i in range(count)]
                if count == 256:
                    self.assertEqual(len(v._bounded(values)), 256)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'candidates'):
                        v._bounded(values)

    def test_nested_visible_call_is_not_skipped_by_deferred_assignment(self):
        with self.assertRaisesRegex(RuntimeError, 'candidates'):
            self.scan(kernel_name() + 'alias = name + str(print(name))\n')
        v = self.scan(kernel_name() + 'alias = name + str(print("amd"))\n')
        self.assertTrue(v.matches)

    def test_other_limits_are_not_deferred(self):
        v = visitor(kernel_name())
        v.MAX_OPERATIONS = 10
        with self.assertRaisesRegex(RuntimeError, 'work/time'):
            v.visit(ast.parse(kernel_name()))
        v = visitor('name = "too long"\n')
        v.MAX_STRING = 2
        with self.assertRaisesRegex(RuntimeError, 'string'):
            v.visit(ast.parse('name = "too long"\n'))


if __name__ == '__main__':
    unittest.main()
