# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Real pinned Gitleaks smoke test. Requires preinstalled policy image."""
import argparse
import secrets
import subprocess
import tempfile
from pathlib import Path

from hygon_pr_gate.audit_pr import run_gate

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='gate-secret-test-') as temporary:
        repo = Path(temporary) / 'repo'
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()
        git('init', '-q')
        git('config', 'user.name', 'Hygon Developer')
        git('config', 'user.email', 'developer@hygon.com')
        (repo / 'README.md').write_text('Synthetic scanner test\n')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        base = git('rev-parse', 'HEAD')
        # Generated test data, not a credential for any service.
        marker = secrets.token_hex(24)
        (repo / 'config.py').write_text('api_key = "{}"\n'.format(marker))
        git('add', '.')
        git('commit', '-qm', 'synthetic fixture')
        summary, code = run_gate(argparse.Namespace(
            repo=repo, repository='test/fixture', base=base, head=git('rev-parse', 'HEAD'),
            policy_root=ROOT / 'policies', summary=Path(temporary) / 'summary.md',
            checks='gitleaks', native_only=False))
        text = summary.read_text(encoding='utf-8')
        assert code == 0, 'Secret-only findings must not block: ' + text.replace(marker, '[REDACTED]')
        assert '疑似包含密钥' in text, 'Real scanner must detect synthetic fixture'
        assert marker not in text, 'Secret value must never appear in summary'
        assert 'Blockers / 阻断问题：0' in text
        print('Pinned Gitleaks integration: detected, advisory, redacted, exit 0')


if __name__ == '__main__':
    main()
