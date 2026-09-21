# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Run patched Semgrep executor on pinned incident source, without executing it."""
import json
from pathlib import Path
import tempfile
import urllib.request

from hygon_pr_gate.local_executor import LocalDockerExecutor
from hygon_pr_gate.policy import load_policy
from hygon_pr_gate.render_summary import render_summary


def main():
    root = Path(__file__).resolve().parents[1]
    url = 'https://raw.githubusercontent.com/HYGON-AI/rocSHMEM-das/a296ec7dad6aefa0103837eff1df98219ac759ad/src/gda/topology.cpp'
    source = urllib.request.urlopen(url, timeout=30).read().decode('utf-8')
    policy = load_policy(root / 'policies', 'HYGON-AI/rocSHMEM-das')
    with tempfile.TemporaryDirectory(prefix='gate-cpp-replay-') as directory:
        repo = Path(directory)
        path = 'src/gda/topology.cpp'
        (repo / path).parent.mkdir(parents=True)
        (repo / path).write_text(source, encoding='utf-8')
        reports = repo / 'reports'
        reports.mkdir()
        executor = LocalDockerExecutor(policy, root / 'policies')
        executor.docker_cpus = '2'
        executor.docker_memory = '4g'
        findings, status = executor._semgrep(repo, {'changed_lines': {path: {1}}}, reports, [path])
        assert status['state'] == 'partial', status
        assert any(item['rule_id'] == 'SAST.SEMGREP.CPP_PARSER_COMPATIBILITY' and item['line'] == 1136 for item in findings)
        assert not any(item['level'] == 'blocker' for item in findings)
        summary = repo / 'summary.md'
        render_summary(dict(repository='HYGON-AI/rocSHMEM-das', display_name='Secrets & SAST',
                            statuses=[status], findings=findings, gate_version='local candidate (unreleased)',
                            scope=dict(merge_base='unknown', head='a296ec7dad6aefa0103837eff1df98219ac759ad', changes=[path], commits=[])), summary)
        print(json.dumps({'status': status, 'findings': findings}, ensure_ascii=False), flush=True)
        print(summary.read_text(encoding='utf-8'), flush=True)


if __name__ == '__main__':
    main()
