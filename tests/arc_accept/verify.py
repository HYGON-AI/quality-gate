#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Collect ARC_ACCEPT_RESULT files and verify that concurrently running card jobs on one node never share a device."""
import glob, json, sys

rows = [json.load(open(p)) for p in glob.glob('results/**/*.json', recursive=True)]
errors = []
for r in rows:
    if not r.get('passed'):
        errors.append(f"{r['job']} failed: {r['errors']}")
pairs = 0
cards = [r for r in rows if r.get('expected_cards') and isinstance(r['checks'].get('devices'), dict)]
for i, a in enumerate(cards):
    for b in cards[i + 1:]:
        if a['node'] != b['node']:
            continue
        overlap = min(a['end'], b['end']) - max(a['start'], b['start'])
        if overlap <= 0:
            continue
        pairs += 1
        shared = set(a['checks']['devices']['renders']) & set(b['checks']['devices']['renders'])
        if shared:
            errors.append(f"{a['job']} and {b['job']} on {a['node']} overlapped {overlap:.0f}s sharing {sorted(shared)}")
summary = {'results': len(rows), 'concurrent_same_node_pairs': pairs, 'errors': errors,
           'placement': {r['job']: [r['node'], r['checks'].get('devices', {}).get('renders') if isinstance(r['checks'].get('devices'), dict) else None] for r in rows}}
print('ARC_ACCEPT_SUMMARY ' + json.dumps(summary, ensure_ascii=False))
sys.exit(1 if errors or not rows else 0)
