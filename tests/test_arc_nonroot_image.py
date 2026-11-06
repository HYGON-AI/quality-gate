import unittest
from pathlib import Path


class NonrootImageTest(unittest.TestCase):
    def test_pinned_offline_nonroot_account(self):
        text = (Path(__file__).resolve().parents[1] / 'deploy/arc-soak/hcu-nonroot.Dockerfile').read_text(encoding='utf-8')
        self.assertIn('FROM 42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d', text)
        self.assertIn('groupadd --gid 1001 ci-runner', text)
        self.assertIn('useradd --uid 1001 --gid 1001', text)
        self.assertIn('--password "!"', text)
        self.assertEqual(text.strip().splitlines()[-1], 'USER 1001:1001')
        for forbidden in ['apt-get', 'curl ', 'wget ', 'LD_PRELOAD', 'chmod 777', '--privileged']:
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
