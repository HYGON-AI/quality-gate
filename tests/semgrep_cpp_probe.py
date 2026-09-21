# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Explicit, offline production-image probe for C++ structured bindings.

Run on Linux: python tests/semgrep_cpp_probe.py --gate-root /path/to/gate
Does not execute target code or alter the runner. Nonzero on unexpected results.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

IMAGE = 'docker.xuanyuan.run/semgrep/semgrep@sha256:16783c52158c4c874576f53579b42b3e793210546e2dfac4c5e49e18038ac383'
PREFIX = '#include <map>\n#include <vector>\nvoid demo() {\nstd::map<int, std::vector<int>> groups;\n'
CASES = {
    'structured': PREFIX + 'for (auto& [id, values] : groups) { (void)id; (void)values; }\n}\n',
    'ordinary': PREFIX + 'for (auto& entry : groups) { auto& id = entry.first; auto& values = entry.second; (void)id; (void)values; }\n}\n',
    'invalid': PREFIX + 'for (auto& entry : groups {\n}\n',
    'positive-system': '#include <cstdlib>\nvoid demo(const char* input) { system(input); }\n',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate-root', type=Path, required=True)
    parser.add_argument('--image', default=IMAGE)
    parser.add_argument('--expect-fixed', action='store_true')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--incident', action='store_true', help='Fetch pinned PR source, scan only; never execute it')
    args = parser.parse_args()
    cases = dict(CASES)
    if args.incident:
        url = 'https://raw.githubusercontent.com/HYGON-AI/rocSHMEM-das/a296ec7dad6aefa0103837eff1df98219ac759ad/src/gda/topology.cpp'
        source = urllib.request.urlopen(url, timeout=30).read().decode('utf-8')
        old = 'for (auto& [oamId, gpus] : oamToGpus) {'
        assert source.count(old) == 1
        cases = {'incident': source, 'incident-ordinary': source.replace(old, 'for (auto& entry : oamToGpus) { auto& oamId = entry.first; auto& gpus = entry.second;')}
    if args.cases:
        cases = {name: cases[name] for name in args.cases}
    with tempfile.TemporaryDirectory(prefix='gate-cpp-probe-') as directory:
        root = Path(directory)
        for name, source in cases.items():
            (root / (name + '.cpp')).write_text(source)
        for name in cases:
            compile_result = None if args.incident else subprocess.run(['g++', '-std=c++17', '-pedantic-errors', '-fsyntax-only', str(root / (name + '.cpp'))], capture_output=True, text=True)
            scan = subprocess.run([
                'docker', 'run', '--rm', '--pull=never', '--network=none',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--cpus', '2', '--memory', '4g',
                '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp', '-e', 'SEMGREP_SEND_METRICS=off',
                '-e', 'SEMGREP_ENABLE_VERSION_CHECK=0',
                '-v', f'{root}:/repo:rw', '-v', f'{args.gate_root.resolve() / "policies/semgrep"}:/rules:ro',
                '-w', '/repo', args.image, 'semgrep', 'scan', '--config', '/rules/hygon-security-v1.yml',
                '--metrics', 'off', '--json', '--output', f'/repo/{name}.json', '--error', f'/repo/{name}.cpp',
            ], capture_output=True, text=True, timeout=180)
            report = json.loads((root / (name + '.json')).read_text())
            print(json.dumps({'case': name, 'compiler_exit': compile_result.returncode if compile_result else None, 'scanner_exit': scan.returncode,
                              'errors': report.get('errors'), 'findings': len(report.get('results', []))}), flush=True)
            if compile_result:
                assert (compile_result.returncode == 0) == (name != 'invalid')
            assert scan.returncode in (0, 1), scan.stderr
            if name in ('ordinary', 'structured', 'incident-ordinary'):
                assert not report.get('errors'), report.get('errors')
            elif name == 'incident':
                if args.expect_fixed:
                    assert not report.get('errors'), report.get('errors')
                else:
                    assert any('single name expected for simple var' in error.get('message', '') for error in report.get('errors', []))
            elif name == 'invalid':
                # This pinned scanner tolerates this malformed range-for. It is
                # not a C++ compiler; record this coverage gap explicitly.
                assert not report.get('errors'), report.get('errors')
            elif name == 'positive-system':
                assert not report.get('errors'), report.get('errors')
                assert any(item['check_id'].endswith('hygon.c.system-call') for item in report.get('results', [])), report


if __name__ == '__main__':
    main()
