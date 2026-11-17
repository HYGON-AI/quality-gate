# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
import gzip
import io
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from hygon_pr_gate.artifacts import review_artifact_format
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.sensitive_diff_check import scan_sensitive_diff

ROOT = Path(__file__).resolve().parents[1]


class BinaryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.policy = load_policy(ROOT / 'policies', 'test/repo')
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            info = tarfile.TarInfo('note.txt')
            info.size = 3
            archive.addfile(info, io.BytesIO(b'dcu'))
        tar = stream.getvalue()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('archive/data.pkl', b'untrusted payload')
        self.samples = {'model.pt': stream.getvalue(), 'data.tar': tar, 'data.tgz': gzip.compress(tar)}

    def git(self, *args, data=None):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], input=data).strip()

    def scan(self, path, data):
        blob = self.git('hash-object', '-w', '--stdin', data=data)
        tree = self.git('mktree', data=b'100644 blob ' + blob + b'\t' + path.encode() + b'\n').decode()
        scope = {'head': tree, 'changes': [{'kind': 'A', 'path': path}], 'changed_lines': {}}
        return scan_sensitive_diff(self.repo, scope, self.policy)

    def test_real_formats_require_manual_review(self):
        for path, data in self.samples.items():
            with self.subTest(path=path):
                findings, status = self.scan(path, data)
                self.assertEqual(status['state'], 'findings')
                self.assertEqual(findings[0]['rule_id'], 'SENSITIVE_DIFF.BINARY_ARTIFACT_REVIEW')
                self.assertEqual(findings[0]['level'], 'advisory')
                self.assertIn('内容未扫描', status['detail'])

    def test_header_recognition_before_text_limit_keeps_path_check(self):
        self.policy['git']['max_text_scan_bytes'] = 32
        for path, data in self.samples.items():
            findings, status = self.scan('dcu_' + path, data)
            self.assertNotEqual(status['state'], 'failed')
            self.assertTrue(any(f['rule_id'].endswith('_PATH') for f in findings))

    def test_renamed_text_is_scanned(self):
        for path in self.samples:
            findings, status = self.scan(path, b'dcu\n')
            self.assertNotEqual(status['state'], 'failed')
            self.assertTrue(any(f['rule_id'].endswith('_CONTENT') for f in findings))

    def test_unknown_mismatch_and_pickle_remain_invalid(self):
        for path, data in [('model.pt', b'\x80\x02pickle\0'), ('note.md', self.samples['data.tar']),
                           ('data.tgz', b'\x1f\x8b\x08\xe0' + b'\0' * 20), ('model.pt', b'PK\x03\x04\0')]:
            with self.subTest(path=path, data=data[:8]):
                self.assertEqual(self.scan(path, data)[1]['state'], 'failed')

    def test_invalid_tar_checksum_is_not_exempt(self):
        data = bytearray(self.samples['data.tar'])
        data[0] ^= 1
        self.assertIsNone(review_artifact_format('data.tar', data))
        self.assertEqual(self.scan('data.tar', bytes(data))[1]['state'], 'failed')

    def test_oversized_text_still_invalid(self):
        self.policy['git']['max_text_scan_bytes'] = 32
        for path in self.samples:
            self.assertEqual(self.scan(path, b'a' * 33)[1]['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
