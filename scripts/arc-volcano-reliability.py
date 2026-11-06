#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Fixed, bounded CPU reliability probes, executed from a trusted commit only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
import uuid

S = importlib.util.spec_from_file_location('pilot', Path(__file__).with_name('arc-volcano-pilot.py'))
pilot = importlib.util.module_from_spec(S)
S.loader.exec_module(pilot)
MODES = ('queue', 'compute-timeout', 'github-timeout', 'cancel', 'runner-loss', 'recovery')
RUN_LABEL = 'ci.hygon.cn/test-run'
MODE_LABEL = 'ci.hygon.cn/test-mode'


def make_manifest(name, owner, mode, run_id, runner):
    if mode not in MODES or mode == 'recovery':
        raise ValueError('Unknown bounded probe mode')
    m = pilot.manifest(name, owner, 0)
    hold, deadline = {'queue': (25, 120), 'compute-timeout': (90, 15),
                      'github-timeout': (110, 120), 'cancel': (110, 120),
                      'runner-loss': (100, 25)}[mode]
    m['metadata']['labels'].update({RUN_LABEL: run_id, MODE_LABEL: mode})
    m['metadata']['annotations'] = {'ci.hygon.cn/dispatch-runner': runner}
    m['spec']['ttlSecondsAfterFinished'] = 30 if mode == 'runner-loss' else 600
    t = m['spec']['tasks'][0]['template']
    t['metadata']['labels'].update({RUN_LABEL: run_id, MODE_LABEL: mode})
    t['spec']['activeDeadlineSeconds'] = deadline
    c = t['spec']['containers'][0]
    if mode == 'queue':
        c['resources']['requests']['cpu'] = '500m'
    c['command'] = ['python3', '-c',
                    "import time,hashlib; print('CPU_PROBE_STARTED',flush=True); "
                    "print(hashlib.sha256(b'bounded-cpu').hexdigest(),flush=True); "
                    "time.sleep(%d); print('CPU_PROBE_FINISHED',flush=True)" % hold]
    return m


def sample(record):
    job = json.loads(pilot.kube('get', pilot.RESOURCE, record['name'], '-o', 'json').stdout)
    if not pilot.is_owned(job, record['name'], record['owner'], record['uid']):
        raise RuntimeError('Job identity changed')
    pods = json.loads(pilot.kube('get', 'pods', '-l', pilot.LABEL + '=' + record['owner'], '-o', 'json').stdout)['items']
    if len(pods) > 1:
        raise RuntimeError('Unexpected Pod retries')
    item = {'name': record['name'], 'phase': job.get('status', {}).get('state', {}).get('phase'),
            'running': False, 'pod_phase': None, 'terminal': None}
    if pods:
        p = pods[0]
        if not any(x.get('uid') == record['uid'] for x in p['metadata'].get('ownerReferences', [])):
            raise RuntimeError('Pod ownership mismatch')
        item.update(pod=p['metadata']['name'], pod_phase=p['status'].get('phase'),
                    reason=p['status'].get('reason'), node=p['spec'].get('nodeName'))
        statuses = p['status'].get('containerStatuses', [])
        for c in statuses:
            if c['name'] == 'probe':
                item['running'] = 'running' in c.get('state', {})
                item['terminal'] = c.get('state', {}).get('terminated')
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=MODES)
    mode = parser.parse_args().mode
    run_id = os.environ['GITHUB_RUN_ID']
    if not run_id.isdigit():
        raise ValueError('Invalid GitHub Run ID')
    runner = os.environ['RUNNER_NAME']
    out = Path(os.environ['RUNNER_TEMP']) / 'arc-reliability-evidence'
    out.mkdir(exist_ok=True)
    if mode == 'recovery':
        result = [pilot.probe(0, out), pilot.probe(17, out)]
        (out / 'summary.json').write_text(json.dumps(result, indent=2))
        print('VOLCANO_POST_FAULT_RECOVERY_PASS', flush=True)
        return

    records, snapshots = [], []
    summary = {'run_id': run_id, 'runner': runner, 'mode': mode, 'passed': False}
    (out / 'summary.json').write_text(json.dumps(summary))
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        for _ in range(3 if mode == 'queue' else 1):
            owner = uuid.uuid4().hex
            record = {'name': 'arc-rel-' + owner[:16], 'owner': owner, 'uid': None}
            records.append(record)
            obj = json.loads(pilot.kube('create', '-f', '-', '-o', 'json',
                data=make_manifest(record['name'], owner, mode, run_id, runner)).stdout)
            record['uid'] = obj['metadata']['uid']
            (out / 'ownership.json').write_text(json.dumps(records, indent=2))
            print('CREATED ' + json.dumps(record), flush=True)
        queued_seen = False
        peak = 0
        until = time.monotonic() + 160
        while time.monotonic() < until:
            state = [sample(r) for r in records]
            running = sum(bool(s['running']) for s in state)
            peak = max(peak, running)
            if running == 2 and any(s['terminal'] is None and not s['running'] for s in state):
                queued_seen = True
            point = {'elapsed_sample': len(snapshots), 'states': state, 'running': running}
            snapshots.append(point)
            (out / 'observations.json').write_text(json.dumps(snapshots, indent=2))
            print('OBSERVED ' + json.dumps(point), flush=True)
            if mode == 'queue' and running > 2:
                raise RuntimeError('Pilot queue exceeded 1 CPU at 500m per task')
            terminal = all(s['terminal'] is not None and s['phase'] in ('Completed', 'Terminated', 'Failed', 'Aborted') for s in state)
            if terminal:
                if mode == 'queue':
                    if not queued_seen or peak != 2 or not all(s['terminal']['exitCode'] == 0 and s['phase'] == 'Completed' for s in state):
                        raise RuntimeError('Queue/backfill evidence incomplete')
                    summary.update(passed=True, queue_observed=True, peak_running=peak)
                    print('VOLCANO_CPU_QUEUE_AND_RELEASE_PASS', flush=True)
                elif mode == 'compute-timeout':
                    if state[0]['terminal']['exitCode'] == 0 or state[0]['reason'] != 'DeadlineExceeded':
                        raise RuntimeError('Compute deadline did not produce expected failure')
                    summary.update(passed=True, reason='DeadlineExceeded')
                    print('VOLCANO_COMPUTE_DEADLINE_PASS', flush=True)
                else:
                    raise RuntimeError('External fault was not injected before compute terminated')
                break
            time.sleep(2)
        else:
            raise RuntimeError('Probe observation timeout')
    except BaseException as exc:
        summary['exception'] = type(exc).__name__
        raise
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        errors = []
        for record in records:
            try:
                pods = json.loads(pilot.kube('get', 'pods', '-l', pilot.LABEL + '=' + record['owner'], '-o', 'json').stdout)['items']
                for p in pods:
                    if record['uid'] and not any(x.get('uid') == record['uid'] for x in p['metadata'].get('ownerReferences', [])):
                        raise RuntimeError('Refusing unrelated logs')
                    logs = pilot.kube('logs', p['metadata']['name'], '-c', 'probe', check=False)
                    (out / (record['name'] + '.log')).write_text(logs.stdout, encoding='utf-8')
            except Exception as exc:
                errors.append('logs: ' + str(exc))
            try:
                pilot.cleanup(record['name'], record['owner'], record['uid'])
            except Exception as exc:
                errors.append('cleanup: ' + str(exc))
        summary['cleanup_errors'] = errors
        summary['cleanup_verified'] = not errors
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
        print('CLEANUP ' + json.dumps(summary), flush=True)
        if errors:
            raise RuntimeError('Cleanup/evidence incomplete: ' + '; '.join(errors))


if __name__ == '__main__':
    main()
