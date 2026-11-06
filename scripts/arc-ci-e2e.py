#!/usr/bin/env python3
"""Trusted ARC dispatcher for fixed build/test fixtures in a bounded namespace."""
import argparse,base64,gzip,hashlib,importlib.util,json,os,re,signal,subprocess,time,uuid
from pathlib import Path

NS='github-ci-arc-e2e';QUEUE='arc-e2e';RESOURCE='jobs.batch.volcano.sh'
LABEL='ci.hygon.cn/e2e-owner';RUN='ci.hygon.cn/e2e-run'
IMAGE='42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d'
FILES=('tests/fixtures/arc_e2e/axpy.cpp','tests/fixtures/arc_e2e/run_ci.py','tests/fixtures/arc_e2e/run_pair.py','tests/fixtures/arc_e2e/pair_protocol.py',
       'scripts/arc-volcano-pilot.py','scripts/arc-volcano-reliability.py','scripts/arc-nmz3-hcu-validation.py',
       'tests/test_arc_volcano_pilot.py','tests/test_arc_volcano_reliability.py','tests/test_arc_nmz3_hcu_validation.py')
CASES={'cpu':0,'cpu-build':0,'hcu1':1,'hcu2':2,'hcu4':4,'hcu8':8,'failure':1,'cancel':1,'timeout':0,
       'cpu-failure':0,'cpu-cancel':0,'cpu-timeout':0,'cpu-orphan':0}

def bundle(root):
    data={p:(root/p).read_text(encoding='utf-8') for p in FILES}
    hashes={p:hashlib.sha256(v.encode()).hexdigest() for p,v in data.items()}
    return base64.b64encode(gzip.compress(json.dumps(data).encode(),mtime=0)).decode(),hashes

def artifact_name(name):
    if name not in ('report.json','junit.xml','libaxpy.so','build.txt','repository-tests.txt'):raise ValueError('unexpected artifact name')
    return name

def manifest(name,owner,case,run_id,runner,payload):
    if case not in CASES:raise ValueError('unsupported case')
    resources={'cpu':'2','memory':'8Gi','ephemeral-storage':'2Gi'}
    if CASES[case]:resources['hygon.com/hcu']=str(CASES[case])
    code="""import base64,gzip,json,pathlib,os,sys
d=json.loads(gzip.decompress(base64.b64decode(%r)));allowed=%r
assert set(d)==set(allowed)
root=pathlib.Path('/tmp/arc-e2e-source');root.mkdir()
for name,content in d.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
os.chdir(str(root));os.execv(sys.executable,[sys.executable,'-u','tests/fixtures/arc_e2e/run_ci.py',%r])
"""%(payload,list(FILES),case)
    return {'apiVersion':'batch.volcano.sh/v1alpha1','kind':'Job',
      'metadata':{'name':name,'namespace':NS,'labels':{LABEL:owner,RUN:run_id},'annotations':{'ci.hygon.cn/dispatch-runner':runner}},
      'spec':{'queue':QUEUE,'schedulerName':'volcano','minAvailable':1,'maxRetry':1,'ttlSecondsAfterFinished':300,
        'policies':[{'event':'TaskCompleted','action':'CompleteJob'},{'event':'PodFailed','action':'TerminateJob'}],
        'tasks':[{'name':'main','replicas':1,'template':{'metadata':{'labels':{LABEL:owner,RUN:run_id}},'spec':{
          'restartPolicy':'Never','activeDeadlineSeconds':180,'terminationGracePeriodSeconds':10,
          'serviceAccountName':'arc-e2e-compute','automountServiceAccountToken':False,
          'nodeSelector':{'kubernetes.io/hostname':'github-nmz3'},
          'securityContext':{'runAsNonRoot':True,'runAsUser':1001,'runAsGroup':1001,'supplementalGroups':[39,998],'seccompProfile':{'type':'RuntimeDefault'}},
          'containers':[{'name':'compute','image':IMAGE,'imagePullPolicy':'Never','command':['python3','-u','-c',code],
           'env':[{'name':'OMP_NUM_THREADS','value':'2'},{'name':'HOME','value':'/tmp'}],
           'resources':{'requests':resources.copy(),'limits':resources.copy()},
           'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}}]}}}]}}

def kube(*args,data=None,check=True):
    p=subprocess.run(['kubectl','--kubeconfig=/opt/hygon/kube-incluster.yaml','--request-timeout=15s','-n',NS]+list(args),
        input=None if data is None else json.dumps(data),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=25)
    if check and p.returncode:raise RuntimeError('kubectl: '+p.stderr[:2000])
    return p
def get(*a):return json.loads(kube(*a,'-o','json').stdout)
def validate_record(r):
    if not re.fullmatch('[a-f0-9]{32}',r.get('owner','')) or r.get('name')!='arc-e2e-'+r['owner'][:16]:raise ValueError('invalid ownership')
    if r.get('uid') is not None:uuid.UUID(r['uid'])
def cleanup(r,run_id,runner):
    validate_record(r)
    raw=kube('get',RESOURCE,r['name'],'--ignore-not-found','-o','json').stdout
    if raw.strip():
        meta=json.loads(raw)['metadata']
        if meta.get('labels',{}).get(LABEL)!=r['owner'] or meta.get('labels',{}).get(RUN)!=run_id or meta.get('annotations',{}).get('ci.hygon.cn/dispatch-runner')!=runner or (r.get('uid') is not None and meta['uid']!=r['uid']):raise RuntimeError('cleanup identity mismatch')
        kube('delete','--raw','/apis/batch.volcano.sh/v1alpha1/namespaces/'+NS+'/jobs/'+r['name'],'-f','-',data={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':meta['uid']},'propagationPolicy':'Foreground'})
    until=time.monotonic()+50
    while time.monotonic()<until:
        if not get('get','pods','-l',LABEL+'='+r['owner'])['items'] and not kube('get',RESOURCE,r['name'],'--ignore-not-found','-o','name').stdout.strip():return
        time.sleep(2)
    raise RuntimeError('compute cleanup incomplete')
def store_logs(out,pod):
    log=kube('logs',pod,'-c','compute',check=False).stdout
    (out/'compute.log').write_text(log,encoding='utf-8')
    for line in log.splitlines():
        if line.startswith('ARC_ARTIFACT '):
            item=json.loads(line[len('ARC_ARTIFACT '):]);name=artifact_name(item['name'])
            data=base64.b64decode(item['base64'],validate=True)
            if len(data)>200000 or hashlib.sha256(data).hexdigest()!=item['sha256']:raise RuntimeError('artifact hash/size mismatch')
            (out/name).write_bytes(data)
    return log
def main():
    ap=argparse.ArgumentParser();ap.add_argument('case',choices=list(CASES)+['cleanup-only']);case=ap.parse_args().case
    run_id=os.environ['GITHUB_RUN_ID'];runner=os.environ['RUNNER_NAME']
    if not run_id.isdigit():raise ValueError('invalid run id')
    out=Path(os.environ['RUNNER_TEMP'])/'arc-ci-e2e';out.mkdir(exist_ok=True)
    own=out/'ownership.json'
    if case=='cleanup-only':
        if own.exists():cleanup(json.loads(own.read_text()),run_id,runner)
        (out/'post-cleanup.json').write_text(json.dumps({'verified':True,'run_id':run_id}))
        print('INDEPENDENT_CLEANUP_VERIFIED');return
    def interrupt(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    owner=uuid.uuid4().hex;r={'name':'arc-e2e-'+owner[:16],'owner':owner,'uid':None};own.write_text(json.dumps(r))
    summary={'case':case,'run_id':run_id,'runner':runner,'passed':False,'cleanup_verified':False}
    try:
        for verb,res,ns,want in [('create',RESOURCE,NS,'yes'),('get','secrets',NS,'no'),('create','pods',NS,'no'),('create','rolebindings',NS,'no'),('create',RESOURCE,'github-ci','no')]:
            p=kube('auth','can-i',verb,res,'--namespace='+ns,check=False)
            if p.stdout.strip()!=want:raise RuntimeError('unexpected RBAC '+verb+' '+res+' '+ns)
        root=Path(__file__).resolve().parents[1];payload,hashes=bundle(root)
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=root).strip()
        (out/'source.json').write_text(json.dumps({'checkout_sha':source_sha,'files':hashes},indent=2))
        created=json.loads(kube('create','-f','-','-o','json',data=manifest(r['name'],owner,case,run_id,runner,payload)).stdout)
        r['uid']=created['metadata']['uid'];own.write_text(json.dumps(r))
        print('COMPUTE_CREATED '+json.dumps(r),flush=True);end=time.monotonic()+230;last=''
        while time.monotonic()<end:
            job=get('get',RESOURCE,r['name']);pods=get('get','pods','-l',LABEL+'='+owner)['items']
            if len(pods)>1:raise RuntimeError('unexpected pod count')
            if pods:
                p=pods[0]
                if not any(x.get('uid')==r['uid'] for x in p['metadata'].get('ownerReferences',[])):raise RuntimeError('pod ownership mismatch')
                if p['spec'].get('nodeName') not in (None,os.environ.get('CI_NODE','github-nmz3')):raise RuntimeError('wrong compute node')
                (out/'pod.json').write_text(json.dumps(p,indent=2))
                log=store_logs(out,p['metadata']['name'])
                if log!=last:
                    for line in log[len(last):].splitlines():
                        if not line.startswith('ARC_ARTIFACT '):print(line,flush=True)
                    last=log
                term=next((x['state'].get('terminated') for x in p['status'].get('containerStatuses',[]) if x['name']=='compute'),None)
                phase=job.get('status',{}).get('state',{}).get('phase')
                if term and phase in ['Completed','Failed','Terminated','Aborted']:
                    summary.update(exit_code=term['exitCode'],phase=phase,node=p['spec'].get('nodeName'),pod=p['metadata']['name'])
                    if term['exitCode'] or phase!='Completed':raise RuntimeError('compute CI failed: exit '+str(term['exitCode']))
                    report=json.loads((out/'report.json').read_text())
                    if not report['passed'] or not (out/'junit.xml').exists() or not (out/'libaxpy.so').exists():raise RuntimeError('missing or failed CI reports')
                    summary['passed']=True;print('E2E_CI_PASS',case,flush=True);return
            time.sleep(2)
        raise RuntimeError('bounded CI wait timeout')
    except BaseException as e:
        summary['error']=type(e).__name__+': '+str(e);raise
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
        try:
            for p in get('get','pods','-l',LABEL+'='+owner)['items']:
                if r['uid'] and any(x.get('uid')==r['uid'] for x in p['metadata'].get('ownerReferences',[])):store_logs(out,p['metadata']['name'])
        finally:
            try:cleanup(r,run_id,runner);summary['cleanup_verified']=True
            finally:
                (out/'summary.json').write_text(json.dumps(summary,indent=2))
                print('E2E_SUMMARY '+json.dumps(summary),flush=True)
                if os.environ.get('GITHUB_STEP_SUMMARY'):
                    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('### ARC CI '+case+'\n\n```json\n'+json.dumps(summary,indent=2)+'\n```\n')

if __name__=='__main__':main()
