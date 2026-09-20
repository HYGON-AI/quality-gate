# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Real pinned Gitleaks smoke test. Requires preinstalled policy image."""
import argparse
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
import yaml

from hygon_pr_gate.audit_pr import run_gate

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='gate-secret-test-') as temporary:
        # Hosted test runners are smaller than production. Only resource limits
        # change; scanner image, rules and decision policy remain identical.
        policy_root = Path(temporary) / 'policies'
        shutil.copytree(ROOT / 'policies', policy_root)
        for policy_file in (policy_root / 'pr').glob('*.yaml'):
            policy = yaml.safe_load(policy_file.read_text(encoding='utf-8'))
            policy['external_scanners']['docker_cpus'] = 2
            policy['external_scanners']['docker_memory'] = '2g'
            policy_file.write_text(yaml.safe_dump(policy), encoding='utf-8')
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
            policy_root=policy_root, summary=Path(temporary) / 'summary.md',
            checks='gitleaks', native_only=False))
        text = summary.read_text(encoding='utf-8')
        assert code == 0, 'Secret-only findings must not block: ' + text.replace(marker, '[REDACTED]')
        assert '疑似包含密钥' in text, 'Real scanner must detect synthetic fixture'
        assert marker not in text, 'Secret value must never appear in summary'
        assert 'Blockers / 阻断问题：0' in text
        print('Pinned Gitleaks integration: detected, advisory, redacted, exit 0')
        cases = {
            'dtype-comparisons': ('tensor.py', 'assert key.dtype == torch.bfloat16\n'
                                 'if key_buffer.dtype == torch.float8_e4m3fn:\n    pass\n'),
            'environment-reference': ('config.py', 'api_key = "${API_KEY}"\n'),
            'documentation-placeholder': ('docs/example.md', 'api_key = "your-api-key"\n'),
            'ordinary-key-variable': ('lookup.py', 'key = "cache-entry"\nvalue = mapping[key]\n'),
        }
        for name, (path, source) in cases.items():
            case_base = git('rev-parse', 'HEAD')
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding='utf-8')
            git('add', '.')
            git('commit', '-qm', name)
            summary, code = run_gate(argparse.Namespace(
                repo=repo, repository='test/fixture', base=case_base, head=git('rev-parse', 'HEAD'),
                policy_root=policy_root, summary=Path(temporary) / (name + '.md'),
                checks='gitleaks', native_only=False))
            text = summary.read_text(encoding='utf-8')
            assert code == 0, name + ': ' + text.replace(marker, '[REDACTED]')
            assert marker not in text
            if name != 'dtype-comparisons':
                assert '疑似包含密钥' not in text, name + ': unexpected advisory'
            print('{}: exit 0; secret advisory={}'.format(name, '疑似包含密钥' in text))
        # A credential introduced then removed within this PR must still warn.
        summary, code = run_gate(argparse.Namespace(
            repo=repo, repository='test/fixture', base=base, head=git('rev-parse', 'HEAD'),
            policy_root=policy_root, summary=Path(temporary) / 'history.md',
            checks='gitleaks', native_only=False))
        text = summary.read_text(encoding='utf-8')
        assert code == 0 and '疑似包含密钥' in text and marker not in text
        print('Removed synthetic credential in PR history: advisory retained, redacted, exit 0')


if __name__ == '__main__':
    main()
