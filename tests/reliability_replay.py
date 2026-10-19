# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Opt-in read-only native replay of an existing historical Git range."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

from hygon_pr_gate.audit_pr import run_gate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    # Linux-only explicit replay; no production process/node configuration changes.
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    args.policy_root = ROOT / 'policies'
    args.checks = 'identity,compliance,sensitive-diff'
    args.display_name = 'Code compliance'
    args.github_annotations = False
    args.native_only = False
    started = time.monotonic()
    _, code = run_gate(args)
    print(json.dumps(dict(exit=code, elapsed_seconds=round(time.monotonic()-started, 3),
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        python=sys.version.split()[0], repository=args.repository)), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
