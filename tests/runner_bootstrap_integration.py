# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Explicit integration test requiring uv plus access to GitHub and PyPI; no mocked installer."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RunnerBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gate-bootstrap-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.output = self.directory / 'outputs'
        self.summary = self.directory / 'summary'
        self.env = dict(os.environ, GITHUB_ACTION_PATH=str(ROOT),
                        RUNNER_TEMP=str(self.directory), GITHUB_OUTPUT=str(self.output),
                        GITHUB_STEP_SUMMARY=str(self.summary), GATE_BOOTSTRAP_UV=os.environ.get('GATE_BOOTSTRAP_UV', ''))

    def run_script(self):
        return subprocess.run(['bash', str(ROOT / 'scripts/prepare-python.sh')],
                              env=self.env, cwd=self.directory, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)

    def test_missing_uv_explains_failure(self):
        self.env['GATE_BOOTSTRAP_UV'] = '/nonexistent/uv'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('setup-uv 未提供可执行的 uv', result.stdout)
        self.assertFalse(self.output.exists())
        self.assertIn('启动失败', self.summary.read_text())

    def test_incomplete_checkout_explains_failure(self):
        self.env['GITHUB_ACTION_PATH'] = str(self.directory)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('门禁检出不完整', result.stdout)
        self.assertFalse(self.output.exists())

    def test_python_download_failure_is_explicit(self):
        self.env.update(https_proxy='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
                        http_proxy='http://127.0.0.1:9', HTTP_PROXY='http://127.0.0.1:9',
                        no_proxy='', NO_PROXY='')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('下载并准备 Python 3.11', result.stdout)
        self.assertIn('源码扫描尚未开始', result.stdout)
        self.assertFalse(self.output.exists())

    def test_clean_python_installs_dependency_and_starts_gate(self):
        # A fresh installation directory forces a real managed Python download.
        self.env['PYTHONPATH'] = '/nonexistent/host-packages'
        environments = []
        for _ in range(2):
            result = self.run_script()
            self.assertEqual(result.returncode, 0, result.stdout)
            outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
            interpreter = outputs['python-path']
            environments.append(interpreter)
            subprocess.run([interpreter, '-I', '-c',
                            'import sys, yaml; assert sys.version_info[:2] == (3, 11); assert yaml.__version__ == "6.0.3"'], check=True)
            environment = dict(self.env, PYTHONPATH=str(ROOT / 'src'))
            check = subprocess.run([interpreter, '-m', 'hygon_pr_gate', '--help'],
                                   cwd=self.directory, env=environment, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(outputs['gate-path'], str(ROOT))
        self.assertNotEqual(*environments)


if __name__ == '__main__':
    unittest.main()
