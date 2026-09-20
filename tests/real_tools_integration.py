# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Explicit integration test: requires the policy's preinstalled Docker images."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from hygon_pr_gate.audit_pr import run_gate

ROOT = Path(__file__).resolve().parents[1]
HEADER = '# Copyright (c) 2026 Hygon Information Technology Co., Ltd.\n# SPDX-License-Identifier: Apache-2.0\n'
CASES = {
    'yaml-multidoc': ({'deploy.yaml': 'kind: Deployment\n---\nkind: Service\n'}, 0, '本检查通过'),
    'yaml-typed-keys': ({'config.yaml': '1: number\n"1": string\nnull: empty\n"null": word\n'}, 0, '本检查通过'),
    'yaml-block-string': ({'config.yaml': 'script: |\n  key: one\n  key: two\n  ---\n'}, 0, '本检查通过'),
    'yaml-template': ({'charts/demo/templates/deploy.yaml': 'name: {{ .Values.name }}\n'}, 0, '模板 YAML 需要渲染后验证'),
    'yaml-later-error': ({'deploy.yaml': 'kind: Deployment\n---\nvalue: [broken\n'}, 2, 'YAML'),
    'clean': ({'demo.py': HEADER + 'print(len("amd"))\nassert True, len("amd")\n'}, 0, '本检查通过'),
    'wording': ({'demo.py': HEADER + 'print("{}".format("amd"))\nprint("\\namd")\n'}, 0, 'AMD/XGMI'),
    'semgrep': ({'demo.py': HEADER + 'import subprocess\nsubprocess.run("echo hello", shell=True)\n'}, 0, '静态分析发现潜在安全问题'),
    'ruff': ({'demo.py': HEADER + 'value = 0\ndef f():\n    print(value)\n    value = 1\n'}, 2, 'F823'),
    'shellcheck': ({'run.sh': '#!/bin/sh\n' + HEADER + 'echo "$undefined_variable"\n'}, 0, 'Shell 脚本存在风险问题'),
    'actionlint': ({'.github/workflows/check.yml': 'name: Test\non: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n        invalid-key: true\n'}, 2, 'invalid-key'),
    'yamllint': ({'config.yml': 'key: one\nkey: two\n'}, 2, 'duplication of key'),
    'quality-incremental': ({'config.yml': 'key: one\nkey: two\nother: one\nother: two\n'}, 2, 'duplication of key "other"'),
    'lizard': ({'demo.py': HEADER + 'def f(value):\n' + ''.join('    if value == %d:\n        value += 1\n' % i for i in range(30)) + '    return value\n'}, 0, '复杂度'),
    'failure-retains-blocker': ({'a.py': HEADER + 'import subprocess\nprint("amd")\nsubprocess.run("echo hello", shell=True)\n', 'z.py': HEADER + 'def broken(:\n'}, 1, '存在阻断问题；⚠️ 扫描无效'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', choices=sorted(CASES))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    previous = args.output / 'results.json'
    results = json.loads(previous.read_text()) if args.cases and previous.exists() else []
    with tempfile.TemporaryDirectory(prefix='gate-integration-') as temporary:
        for name, (files, expected, marker) in CASES.items():
            if args.cases and name not in args.cases:
                continue
            results = [item for item in results if item['case'] != name]
            repo = Path(temporary) / name
            repo.mkdir()
            def git(*params):
                return subprocess.check_output(['git', '-C', str(repo), *params], stderr=subprocess.PIPE).decode().strip()
            git('init', '-q')
            git('config', 'user.name', 'Hygon Developer')
            git('config', 'user.email', 'developer@hygon.com')
            (repo / 'README.md').write_text('Integration fixture\n')
            if name == 'quality-incremental':
                (repo / 'config.yml').write_text('key: one\nkey: two\n')
            git('add', '.')
            git('commit', '-qm', 'baseline')
            base = git('rev-parse', 'HEAD')
            for path, source in files.items():
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source)
            git('add', '.')
            git('commit', '-qm', 'fixture')
            summary, code = run_gate(argparse.Namespace(repo=repo, repository='test/fixture', base=base,
                head=git('rev-parse', 'HEAD'), policy_root=ROOT / 'policies',
                summary=args.output / (name + '.md'), native_only=False))
            text = summary.read_text()
            passed = code == expected and marker in text
            if name == 'failure-retains-blocker':
                passed = passed and '静态分析发现潜在安全问题' in text and 'z.py' in text
            results.append({'case': name, 'exit': code, 'expected': expected, 'passed': passed})
            print(json.dumps(results[-1]), flush=True)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if not all(item['passed'] for item in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
