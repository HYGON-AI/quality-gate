# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Read real Git blobs and ensure medium-sized indexes remain fully scanned."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from hygon_pr_gate.git_scope import read_blob
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff

ROOT = Path(__file__).resolve().parents[1]


class LargeTextScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.policy = load_policy(ROOT / 'policies', 'test/repo')
        self.path = 'assets/index.jsonl'

    def git(self, *args, data=None):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], input=data).strip()

    def commit_blob(self, content):
        blob = self.git('hash-object', '-w', '--stdin', data=content)
        # Keep a flat filename in the temporary Git tree; the content is JSONL.
        self.path = 'index.jsonl'
        return self.git('mktree', data=b'100644 blob ' + blob + b'\tindex.jsonl\n').decode()

    def scan(self, tree, policy=None):
        scope = {'head': tree, 'changes': [{'kind': 'A', 'path': self.path}], 'changed_lines': {}}
        return scan_sensitive_diff(self.repo, scope, policy or self.policy)

    def test_lightop_sized_index_scanned_to_end(self):
        self.assertEqual(self.policy['git']['max_text_scan_bytes'], 16 * 1024 * 1024)
        # Put the finding after the old limit; no partial-prefix scan can pass.
        tail = b'\n{"label":"dcu"}\n'
        content = b' ' * (8803433 - len(tail)) + tail
        tree = self.commit_blob(content)
        self.policy['git']['max_text_scan_bytes'] = 4194304
        _, status = self.scan(tree)
        self.assertEqual(status['state'], 'failed')
        self.policy['git']['max_text_scan_bytes'] = 16777216
        findings, status = self.scan(tree)
        self.assertNotEqual(status['state'], 'failed')
        self.assertTrue(any('dcu' in str(f).lower() for f in findings))

    def test_exact_boundary_read_and_oversized_rejection(self):
        maximum = self.policy['git']['max_text_scan_bytes']
        content = b' ' * maximum
        tree = self.commit_blob(content)
        self.assertEqual(len(read_blob(self.repo, tree, self.path, maximum)), maximum)
        tree = self.commit_blob(content + b' ')
        self.assertIsNone(read_blob(self.repo, tree, self.path, maximum))
        _, status = self.scan(tree)
        self.assertEqual(status['state'], 'failed')
        self.assertIn(str(maximum + 1), status['detail'])
