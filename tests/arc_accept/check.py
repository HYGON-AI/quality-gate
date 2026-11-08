#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""ARC job-pod acceptance checks. Runs inside the job container and prints one ARC_ACCEPT_RESULT line."""
import ctypes, glob, json, os, socket, subprocess, sys, time, urllib.request

ROLE = os.environ.get('ACCEPT_ROLE', 'card')          # card | build | cpu
EXPECTED = int(os.environ.get('EXPECTED_CARDS', '0'))
RUN = os.environ.get('GITHUB_RUN_ID', 'local') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
JOB = os.environ.get('ACCEPT_NAME', ROLE)
SHARE = f'/ci_public/quality-gate/arc-accept/{RUN}'
res = {'role': ROLE, 'job': JOB, 'expected_cards': EXPECTED, 'node': os.environ.get('NODE_NAME'), 'pod': socket.gethostname(),
       'start': time.time(), 'checks': {}, 'errors': []}


def check(name, fn):
    try:
        res['checks'][name] = fn()
    except Exception as e:  # record every failure, never treat as pass
        res['errors'].append(f'{name}: {type(e).__name__}: {e}')


def read(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def limits():
    cpu = read('/sys/fs/cgroup/cpu.max') or f"{read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us')} {read('/sys/fs/cgroup/cpu/cpu.cfs_period_us')}"
    mem = read('/sys/fs/cgroup/memory.max') or read('/sys/fs/cgroup/memory/memory.limit_in_bytes')
    shm = os.statvfs('/dev/shm')
    return {'cpu_max': cpu, 'mem_max': mem, 'shm_gib': round(shm.f_blocks * shm.f_frsize / 2**30, 1),
            'affinity_cpus': len(os.sched_getaffinity(0)), 'nproc': subprocess.run(['nproc'], capture_output=True, text=True).stdout.strip(),
            'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS'), 'MAX_JOBS': os.environ.get('MAX_JOBS'),
            'HCU_CI_IN_K8S': os.environ.get('HCU_CI_IN_K8S'), 'uid': os.getuid()}


def no_token():
    p = '/var/run/secrets/kubernetes.io/serviceaccount/token'
    assert not os.path.exists(p), 'service account token is mounted in job pod'
    return 'absent'


def devices():
    renders = sorted(os.path.basename(x) for x in glob.glob('/dev/dri/renderD*'))
    out = {'renders': renders, 'kfd': os.path.exists('/dev/kfd'), 'hyhal': os.path.isdir('/opt/hyhal')}
    if EXPECTED == 0:
        assert not renders and not out['kfd'], 'zero-card job can see HCU devices'
        return out
    assert len(renders) == EXPECTED, f'expected {EXPECTED} render nodes, got {renders}'
    assert out['kfd'] and out['hyhal'], 'missing /dev/kfd or /opt/hyhal'
    return out


def compute():
    if EXPECTED == 0:
        return 'skipped'
    import torch
    n = torch.cuda.device_count()
    assert n == EXPECTED, f'torch sees {n} devices, expected {EXPECTED}'
    torch.manual_seed(7)
    a, b = torch.randn(2048, 2048), torch.randn(2048, 2048)
    ref = a @ b
    out = []
    for d in range(n):
        t0 = time.time()
        got = (a.to(f'cuda:{d}') @ b.to(f'cuda:{d}')).cpu()
        torch.cuda.synchronize(d)
        torch.testing.assert_close(got, ref, atol=5e-2, rtol=5e-3)
        out.append({'device': d, 'name': torch.cuda.get_device_name(d), 'ms': round((time.time() - t0) * 1000, 1)})
    return {'torch': torch.__version__, 'devices': out}


def storage():
    os.makedirs(SHARE, exist_ok=True)
    p = f'{SHARE}/{JOB}.ok'
    open(p, 'w').write(res['pod'])
    ro = None
    for target in ('/public', '/public4'):
        try:
            open(f'{target}/.arc-accept-write-test-{RUN}', 'w').close()
            ro = f'{target} is writable'
            os.remove(f'{target}/.arc-accept-write-test-{RUN}')
        except OSError:
            pass
    assert ro is None, ro
    return {'ci_public_write': p, 'public_readonly': True, 'public_listing': len(os.listdir('/public'))}


def network():
    out = {}
    for name, url in (('github', 'https://github.com'), ('registry_10_16_1_152', 'http://10.16.1.152:5000/v2/'),
                      ('pypi', 'https://pypi.org/simple/pip/')):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                out[name] = r.status
        except urllib.error.HTTPError as e:
            out[name] = e.code
        except Exception as e:
            out[name] = 'ERR ' + type(e).__name__
    assert isinstance(out['github'], int), 'github unreachable'
    return out


def build_artifact():
    so = f'{SHARE}/libaxpy.so'
    if ROLE == 'build':
        src = '/tmp/axpy.c'
        open(src, 'w').write('double axpy(double a,double x,double y){return a*x+y;}\n')
        subprocess.run(['gcc', '-O2', '-shared', '-fPIC', '-o', so, src], check=True)
        return {'built': so}
    if os.path.exists(so):
        r = ctypes.CDLL(so)
        r.axpy.restype = ctypes.c_double
        v = r.axpy(ctypes.c_double(2.0), ctypes.c_double(3.0), ctypes.c_double(1.0))
        assert v == 7.0, v
        return {'consumed': so, 'value': v}
    return 'no build artifact'


check('limits', limits)
check('no_sa_token', no_token)
check('devices', devices)
check('compute', compute)
check('storage', storage)
check('network', network)
check('build_artifact', build_artifact)
hold = int(os.environ.get('HOLD_SECONDS', '0'))
if hold:
    import torch
    x = torch.ones(1024, 1024, device='cuda:0') if EXPECTED else None
    print(f'holding {hold}s', flush=True)
    time.sleep(hold)
res['end'] = time.time()
res['passed'] = not res['errors']
os.makedirs('accept-out', exist_ok=True)
json.dump(res, open(f'accept-out/{JOB}.json', 'w'), indent=1)
print('ARC_ACCEPT_RESULT ' + json.dumps(res), flush=True)
if os.environ.get('FORCE_EXIT'):
    sys.exit(int(os.environ['FORCE_EXIT']))
sys.exit(0 if res['passed'] else 1)
