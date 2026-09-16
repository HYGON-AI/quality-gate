# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Explicit bootstrap tests; the missing-PyYAML case installs from real PyPI."""
import os
from pathlib import Path
import subprocess
import sys
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
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        self.bin.joinpath('mktemp').symlink_to('/usr/bin/mktemp')
        self.env = dict(os.environ, GITHUB_ACTION_PATH=str(ROOT),
                        RUNNER_TEMP=str(self.directory), GITHUB_OUTPUT=str(self.output),
                        GITHUB_STEP_SUMMARY=str(self.summary), PATH=str(self.bin), VIRTUAL_ENV='')

    def run_script(self):
        return subprocess.run(['/bin/bash', str(ROOT / 'scripts/prepare-python.sh')],
                              env=self.env, cwd=self.directory, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)

    def clean_python(self):
        base = self.directory / 'base'
        subprocess.run([sys.executable, '-I', '-m', 'venv', str(base)], check=True)
        self.env['VIRTUAL_ENV'] = str(base)
        python = str(base / 'bin/python')
        subprocess.run([python, '-I', '-c',
                        'import importlib.util; assert importlib.util.find_spec("yaml") is None'], check=True)
        return python

    def block_network(self):
        self.env.update(https_proxy='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
                        http_proxy='http://127.0.0.1:9', HTTP_PROXY='http://127.0.0.1:9',
                        no_proxy='', NO_PROXY='')

    def test_no_python_explains_failure(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('未找到 Python 3.9+', result.stdout)
        self.assertFalse(self.output.exists())
        self.assertIn('启动失败', self.summary.read_text())

    def test_old_python_is_rejected(self):
        if not Path('/usr/bin/python3.8').exists():
            self.skipTest('Python 3.8 is not installed')
        self.bin.joinpath('python3').symlink_to('/usr/bin/python3.8')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('跳过不满足 Python 3.9+', result.stdout)

    def test_incomplete_checkout_explains_failure(self):
        self.env['GITHUB_ACTION_PATH'] = str(self.directory)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('门禁检出不完整', result.stdout)

    def test_generic_python3_reused_offline(self):
        subprocess.run([sys.executable, '-E', '-c', 'import yaml'], check=True)
        self.bin.joinpath('python3').symlink_to(sys.executable)
        self.block_network()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('无需下载或安装', result.stdout)
        self.assertFalse(list(self.directory.glob('quality-gate-python.*')))

    def test_dependency_download_failure_is_explicit(self):
        self.clean_python()
        self.block_network()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('安装 PyYAML 6.0.3', result.stdout)
        self.assertIn('源码扫描尚未开始', result.stdout)
        self.assertFalse(self.output.exists())

    def test_virtualenv_missing_yaml_installs_isolated_and_starts_gate(self):
        base_python = self.clean_python()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
        interpreter = outputs['python-path']
        self.assertNotEqual(interpreter, base_python)
        subprocess.run([base_python, '-I', '-c',
                        'import importlib.util; assert importlib.util.find_spec("yaml") is None'], check=True)
        subprocess.run([interpreter, '-I', '-c',
                        'import yaml; assert yaml.__version__ == "6.0.3"'], check=True)
        environment = dict(self.env, PYTHONPATH=str(ROOT / 'src'))
        check = subprocess.run([interpreter, '-m', 'hygon_pr_gate', '--help'],
                               cwd=self.directory, env=environment, capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        # The same installed environment can be reused without network on the next job.
        self.env['VIRTUAL_ENV'] = str(Path(interpreter).parent.parent)
        self.block_network()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('无需下载或安装', result.stdout)


if __name__ == '__main__':
    unittest.main()
