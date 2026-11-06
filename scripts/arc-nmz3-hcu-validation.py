#!/usr/bin/env python3
"""Bounded operator-run Volcano tests; credentials stay on the submitting host.

No production workflow, ARC RBAC, queue, or node configuration is modified.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

NS = 'github-ci'
NODE = 'github-nmz3'
LABEL = 'ci.hygon.cn/nmz3-validation'
IMAGE = '42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d'
RESOURCE = 'jobs.batch.volcano.sh'
GPU_CODE = r'''
import torch,time,json,os,glob,hashlib,pathlib
torch.set_num_threads(2)
expected=int(os.environ['EXPECTED_CARDS'])
actual=torch.cuda.device_count()
print(json.dumps({'event':'device_check','expected':expected,'actual':actual,'torch':torch.__version__,'hip':torch.version.hip,'devices':glob.glob('/dev/dri/*'),'visibility':{k:os.environ.get(k) for k in ['HIP_VISIBLE_DEVICES','ROCR_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES']},'time':time.time()}),flush=True)
assert actual==expected,(actual,expected)
assert not pathlib.Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists()
p=pathlib.Path('/tmp/nmz3-report');p.mkdir()
p.joinpath('rw').write_bytes(b'bounded-hcu-test');assert p.joinpath('rw').read_bytes()==b'bounded-hcu-test'
results=[]
for dev in range(actual):
 torch.cuda.set_device(dev);torch.manual_seed(17)
 a=torch.randn(128,128);b=torch.randn(128,128)
 cpu=a@b;gpu=(a.cuda()@b.cuda()).cpu()
 torch.testing.assert_close(gpu,cpu,atol=0.005,rtol=0.005)
 a=torch.randn(2048,2048,device='cuda');b=torch.randn(2048,2048,device='cuda');c=torch.empty_like(a)
 for _ in range(10):torch.mm(a,b,out=c)
 torch.cuda.synchronize()
 samples=[]
 for rep in range(3):
  start=time.monotonic();wall=time.time();loops=0
  while time.monotonic()-start<5:
   for _ in range(10):torch.mm(a,b,out=c)
   torch.cuda.synchronize();loops+=10
  elapsed=time.monotonic()-start
  sample={'device':dev,'rep':rep,'start':wall,'end':time.time(),'iterations':loops,'seconds':elapsed,'ms_per_mm':elapsed*1000/loops}
  samples.append(sample);print(json.dumps({'event':'sample',**sample}),flush=True)
 assert torch.isfinite(c).all().item()
 results.append({'device':dev,'name':torch.cuda.get_device_name(dev),'samples':samples,'allocated_bytes':torch.cuda.max_memory_allocated(dev)})
report={'event':'gpu_pass','correctness':True,'rw':True,'results':results,'time':time.time()}
p.joinpath('report.json').write_text(json.dumps(report));assert json.loads(p.joinpath('report.json').read_text())['correctness']
print(json.dumps(report),flush=True)
'''

COMPILE_CODE = r'''
import concurrent.futures,subprocess,tempfile,pathlib,time,json,shutil,hashlib,resource
import glob
devices=glob.glob('/dev/dri/*')
assert not devices and not pathlib.Path('/dev/kfd').exists() and not pathlib.Path('/dev/mkfd').exists(),'CPU job unexpectedly has HCU devices'
print(json.dumps({'event':'cpu_isolation','devices':devices,'kfd':False,'mkfd':False}),flush=True)
cc=shutil.which('g++');assert cc,'g++ missing'
source='#include <cmath>\n'+'\n'.join('double f%d(double x){for(int i=0;i<128;i++)x=sin(x*1.0001+i)+cos(x);return x;}'%i for i in range(256))
root=pathlib.Path(tempfile.mkdtemp(prefix='nmz3-compile-'));src=root/'fixed.cpp';src.write_text(source)
print(json.dumps({'event':'compile_started','time':time.time(),'workers':32,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'compiler':subprocess.check_output([cc,'--version']).decode().splitlines()[0]}),flush=True)
start=time.monotonic();deadline=start+75
def worker(i):
 count=0
 while time.monotonic()<deadline:
  subprocess.run([cc,'-O2','-c',str(src),'-o',str(root/('%d.o'%i))],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=35)
  count+=1
 return count
with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:counts=list(pool.map(worker,range(32)))
r=resource.getrusage(resource.RUSAGE_CHILDREN)
print(json.dumps({'event':'compile_pass','time':time.time(),'seconds':time.monotonic()-start,'objects':sum(counts),'cpu_seconds':r.ru_utime+r.ru_stime,'child_maxrss_kib':r.ru_maxrss}),flush=True)
'''

def mixed_code():
    # Keep one pod/device for all three stages. Host opens barriers only after
    # compiler start and completion have been observed; no credentials in pod.
    init=GPU_CODE.split('results=[]')[0]
    body=GPU_CODE.split('results=[]')[1].split("report={'event':'gpu_pass'")[0]
    body='results=[]'+body
    return init+'''\nfor stage in ['baseline','mixed','after']:
 if stage!='baseline':
  until=time.monotonic()+150
  while not pathlib.Path('/tmp/allow-'+stage).exists():
   assert time.monotonic()<until,'phase barrier timeout'
   time.sleep(1)
 print(json.dumps({'event':'stage_start','stage':stage,'time':time.time()}),flush=True)
'''+''.join(' '+line+'\n' for line in body.splitlines())+''' print(json.dumps({'event':'stage_done','stage':stage,'results':results,'time':time.time()}),flush=True)
print(json.dumps({'event':'gpu_pass','time':time.time()}),flush=True)
'''

def hold_code():
    return GPU_CODE.split('results=[]')[0]+'''
for dev in range(actual):
 torch.cuda.set_device(dev)
 a=torch.ones(128,128,device='cuda');b=a@a
 assert torch.all(b==128).item()
print(json.dumps({'event':'eight_cards_ready','time':time.time(),'cards':actual}),flush=True)
time.sleep(40)
print(json.dumps({'event':'gpu_pass','time':time.time(),'cards':actual}),flush=True)
'''

def events(log):
    out=[]
    for line in log.splitlines():
        try:out.append(json.loads(line))
        except ValueError:pass
    return out

def command(args, data=None, check=True, timeout=30):
    p = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(p.stderr[:2000])
    return p

def kube(*args, **kw):
    return command(['kubectl','--kubeconfig=/home/github/.kube-ci/config',
                    '--request-timeout=15s','-n',NS]+list(args), **kw)

def obj(*args):
    return json.loads(kube(*args,'-o','json').stdout)

def manifest(name, owner, cards=1, code=GPU_CODE, cpus='4', memory='8Gi'):
    resources={'cpu':cpus,'memory':memory,'ephemeral-storage':'2Gi'}
    if cards:resources['hygon.com/hcu']=cards
    return {'apiVersion':'batch.volcano.sh/v1alpha1','kind':'Job',
        'metadata':{'name':name,'namespace':NS,'labels':{LABEL:owner}},
        'spec':{'queue':'default','schedulerName':'volcano','minAvailable':1,'maxRetry':0,
          'ttlSecondsAfterFinished':600,
          'policies':[{'event':'TaskCompleted','action':'CompleteJob'},
                      {'event':'PodFailed','action':'TerminateJob'}],
          'tasks':[{'name':'main','replicas':1,'template':{
            'metadata':{'labels':{LABEL:owner}},'spec':{
              'restartPolicy':'Never','activeDeadlineSeconds':240,'terminationGracePeriodSeconds':10,
              'automountServiceAccountToken':False,'nodeSelector':{'kubernetes.io/hostname':NODE},
              'securityContext':{'seccompProfile':{'type':'RuntimeDefault'}},
              'containers':[{'name':'probe','image':IMAGE,'imagePullPolicy':'Never',
                'command':['python3','-u','-c',code],
                'env':[{'name':'EXPECTED_CARDS','value':str(cards)},{'name':'OMP_NUM_THREADS','value':'2'}],
                'resources':{'requests':resources.copy(),'limits':resources.copy()},
                'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}}]}}}]}}

class Suite:
    def __init__(self):
        self.owner=uuid.uuid4().hex
        self.root=Path('/home/github/lvj/nmz3-validation-20261106')/self.owner
        self.root.mkdir(parents=True,mode=0o700)
        self.jobs={};self.results={}
        print('EVIDENCE_REMOTE',str(self.root),flush=True)
    def save(self,name,value):
        (self.root/name).write_text(json.dumps(value,indent=2))
    def create(self,role,cards=1,**kw):
        name='nmz3-'+role+'-'+self.owner[:10]
        m=manifest(name,self.owner,cards,**kw);self.save(name+'-manifest.json',m)
        kube('create','--dry-run=server','-f','-',data=json.dumps(m))
        self.jobs[name]=None
        created=json.loads(kube('create','-f','-','-o','json',data=json.dumps(m)).stdout)
        self.jobs[name]=created['metadata']['uid']
        print('CREATED',name,flush=True);return name
    def pods(self,name):
        return [p for p in obj('get','pods','-l',LABEL+'='+self.owner)['items']
                if any(r.get('uid')==self.jobs[name] for r in p['metadata'].get('ownerReferences',[]))]
    def capture(self,name,p):
        pn=p['metadata']['name']
        log=kube('logs',pn,'-c','probe',check=False)
        (self.root/(name+'.log')).write_text(log.stdout)
        self.save(name+'-pod.json',p)
        self.save(name+'-events.json',obj('get','events','--field-selector','involvedObject.name='+pn))
        cs=p['status'].get('containerStatuses',[])
        for c in cs:
            cid=c.get('containerID','')
            if cid.startswith('docker://'):
                r=command(['docker','inspect',cid.split('://')[1]],check=False)
                if r.returncode==0:
                    x=json.loads(r.stdout)[0]
                    self.save(name+'-runtime.json',{'id':x['Id'],'image':x['Image'],
                        'devices':x['HostConfig'].get('Devices'),'privileged':x['HostConfig']['Privileged'],
                        'mounts':[{'type':v['Type'],'source':v['Source'],'destination':v['Destination']} for v in x['Mounts']]})
        return log.stdout
    def wait(self,names,timeout=220):
        pending=set(names);end=time.monotonic()+timeout
        while pending and time.monotonic()<end:
            self.health()
            for name in list(pending):
                pods=self.pods(name)
                if len(pods)>1:raise RuntimeError('unexpected replica/retry')
                if not pods:continue
                p=pods[0]
                if p['spec'].get('nodeName') not in (None,NODE):raise RuntimeError('wrong node')
                self.capture(name,p)
                terms=[c['state'].get('terminated') for c in p['status'].get('containerStatuses',[]) if c['name']=='probe']
                phase=obj('get',RESOURCE,name).get('status',{}).get('state',{}).get('phase')
                if terms and terms[0] and phase in ['Completed','Terminated','Failed','Aborted']:
                    log=self.capture(name,p);term=terms[0]
                    self.results[name]={'phase':phase,'exit':term['exitCode'],'node':p['spec'].get('nodeName'),'logs':log}
                    self.save('results.json',self.results)
                    print('FINISHED',name,phase,term['exitCode'],log,flush=True)
                    if term['exitCode']!=0 or phase!='Completed':raise RuntimeError('test failed '+name)
                    pending.remove(name)
            if pending:time.sleep(3)
        if pending:raise RuntimeError('bounded wait timeout '+str(pending))
    def health(self):
        n=obj('get','node',NODE)
        if any(c['status']=='True' for c in n['status']['conditions'] if c['type'].endswith('Pressure')):
            raise RuntimeError('node pressure; stop owned tests')
        if any(c['status']!='True' for c in n['status']['conditions'] if c['type']=='Ready'):
            raise RuntimeError('node not ready')
    def wait_event(self,name,event,stage=None,timeout=100):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            self.health()
            pods=self.pods(name)
            if pods:
                p=pods[0];log=self.capture(name,p)
                found=[x for x in events(log) if x.get('event')==event and (stage is None or x.get('stage')==stage)]
                if found:return found[-1],p
                if p['status'].get('phase') in ['Failed','Succeeded']:raise RuntimeError('ended without required event '+name+' '+event)
            time.sleep(2)
        raise RuntimeError('event timeout '+name+' '+event)
    def barrier(self,name,stage):
        assert stage in ['mixed','after']
        p=self.pods(name)[0]
        assert p['spec']['nodeName']==NODE
        kube('exec',p['metadata']['name'],'-c','probe','--','python3','-c',
             "from pathlib import Path;Path('/tmp/allow-%s').touch()"%stage)
    def cleanup(self):
        for name,uid in self.jobs.items():
            raw=kube('get',RESOURCE,name,'--ignore-not-found','-o','json').stdout
            if not raw.strip():continue
            x=json.loads(raw);m=x['metadata']
            assert m.get('labels',{}).get(LABEL)==self.owner and (uid is None or m['uid']==uid)
            kube('delete','--raw','/apis/batch.volcano.sh/v1alpha1/namespaces/'+NS+'/jobs/'+name,
                 '-f','-',data=json.dumps({'apiVersion':'v1','kind':'DeleteOptions',
                  'preconditions':{'uid':m['uid']},'propagationPolicy':'Foreground'}))
        end=time.monotonic()+60
        while time.monotonic()<end:
            if not obj('get','pods','-l',LABEL+'='+self.owner)['items'] and not obj('get',RESOURCE,'-l',LABEL+'='+self.owner)['items']:
                self.save('cleanup.json',{'verified':True});print('CLEANUP_VERIFIED',flush=True);return
            time.sleep(2)
        raise RuntimeError('test resources remain')

def readiness():
    for p in Path('/proc').glob('[0-9]*/comm'):
        try:
            if p.read_text().strip() in ['Runner.Listener','Runner.Worker'] and str((p.parent/'cwd').resolve()).startswith('/home/github/actions-runner-ci-nmz3'):
                raise RuntimeError('legacy runner active')
        except OSError:pass
    n=obj('get','node',NODE)
    assert int(n['status']['allocatable'].get('hygon.com/hcu',0))==8
    assert all(c['status']=='False' for c in n['status']['conditions'] if c['type'].endswith('Pressure'))
    smi=command([shutil.which('rocm-smi') or shutil.which('hy-smi'),'--showpids']).stdout
    assert 'No KFD PIDs' in smi,'GPU already occupied'
    assert not obj('get',RESOURCE)['items'],'existing github-ci jobs; do not interfere'
    command(['docker','image','inspect',IMAGE])
    print('READINESS_PASS',flush=True)

def main():
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    readiness();s=Suite()
    try:
        mode=sys.argv[1] if len(sys.argv)>1 else 'probe'
        if mode=='probe':s.wait([s.create('single')])
        elif mode=='isolation':
            pair=[s.create('pair-a'),s.create('pair-b')];s.wait(pair)
            ev=[events(s.results[n]['logs']) for n in pair]
            devices=[set(x['devices']) for es in ev for x in es if x.get('event')=='device_check']
            assert len(devices)==2 and not devices[0]&devices[1], 'device overlap'
            windows=[(min(x['start'] for x in es if x.get('event')=='sample'),max(x['end'] for x in es if x.get('event')=='sample')) for es in ev]
            overlap=min(w[1] for w in windows)-max(w[0] for w in windows)
            assert overlap>5,'did not meaningfully overlap'
            s.save('isolation.json',{'distinct_devices':[sorted(d) for d in devices],'overlap_seconds':overlap})
            print('ISOLATION_PASS',overlap,flush=True)
            s.wait([s.create('dual',cards=2)])
        elif mode=='mixed':
            gpu=s.create('mixed-gpu',code=mixed_code())
            s.wait_event(gpu,'stage_done','baseline')
            cpu=s.create('compile',cards=0,code=COMPILE_CODE,cpus='32',memory='32Gi')
            s.wait_event(cpu,'compile_started')
            s.barrier(gpu,'mixed');s.wait_event(gpu,'stage_done','mixed')
            s.wait([cpu],timeout=120);s.barrier(gpu,'after');s.wait([gpu],timeout=60)
            ge=events(s.results[gpu]['logs']);ce=events(s.results[cpu]['logs'])
            starts={x['stage']:x['time'] for x in ge if x.get('event')=='stage_start'}
            ends={x['stage']:x for x in ge if x.get('event')=='stage_done'}
            cs=next(x for x in ce if x.get('event')=='compile_started');cf=next(x for x in ce if x.get('event')=='compile_pass')
            assert cs['time']<=starts['mixed']<ends['mixed']['time']<=cf['time']<=starts['after']
            import statistics
            summary={'same_pod':gpu,'compiler':cf,'phases':{}}
            for stage,x in ends.items():
                vals=[v['ms_per_mm'] for v in x['results'][0]['samples']]
                summary['phases'][stage]={'median_ms':statistics.median(vals),'min_ms':min(vals),'max_ms':max(vals)}
            base=summary['phases']['baseline']['median_ms']
            summary['mixed_change_percent']=(summary['phases']['mixed']['median_ms']/base-1)*100
            summary['after_change_percent']=(summary['phases']['after']['median_ms']/base-1)*100
            s.save('mixed-summary.json',summary);print('MIXED_PASS',json.dumps(summary),flush=True)
        elif mode=='queue':
            full=s.create('hold-eight',cards=8,code=hold_code(),memory='32Gi')
            s.wait_event(full,'eight_cards_ready',timeout=90)
            queued=s.create('wait-one')
            observations=[]
            for _ in range(4):
                time.sleep(3);s.health()
                p=s.pods(queued)
                j=obj('get',RESOURCE,queued)
                observations.append({'time':time.time(),'job_phase':j.get('status',{}).get('state',{}).get('phase'),
                    'pods':[{'name':x['metadata']['name'],'phase':x['status']['phase'],'node':x['spec'].get('nodeName'),'conditions':x['status'].get('conditions')} for x in p]})
                assert p and all(x['status']['phase']=='Pending' and not x['spec'].get('nodeName') for x in p),'single-card job did not wait'
                for x in p:s.capture(queued,x)
            s.wait([full,queued],timeout=140)
            pe=[json.loads((s.root/(n+'-pod.json')).read_text()) for n in [full,queued]]
            release=pe[0]['status']['containerStatuses'][0]['state']['terminated']['finishedAt']
            start=pe[1]['status']['containerStatuses'][0]['state']['terminated']['startedAt']
            assert start>=release,'queued compute started before release'
            summary={'observations':observations,'eight_card_finished':release,'single_card_started':start,'passed':True}
            s.save('hcu-queue.json',summary);print('HCU_QUEUE_PASS',json.dumps(summary),flush=True)
        else:raise ValueError('unsupported mode')
    finally:s.cleanup()

if __name__=='__main__':main()
