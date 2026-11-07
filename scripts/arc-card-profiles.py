#!/usr/bin/env python3
"""TEST ONLY: card-count entry point, fixed uncredentialed fixture and UID cleanup."""
import argparse,calendar,importlib.util,json,os,signal,subprocess,time,uuid
from pathlib import Path

def load(name,file):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

base=load('profiles_base','arc-ci-e2e.py');fleet=load('profiles_fleet','arc-hcu-soak.py')
NS='github-ci-arc-profiles';QUEUE='arc-profiles';OUT='arc-card-profiles'
FILES=base.FILES+('ci/arc-profile.sh','tests/fixtures/arc_e2e/run_profile.py','tests/fixtures/arc_e2e/profile_worker.py')
NODES=['github-nmz3','github-nmz4']

def ensure_window(now=None):
    if (time.time() if now is None else now)>=calendar.timegm((2026,11,7,9,30,0)):
        raise RuntimeError('profile submission window closed')

def profile(cards,model,image,script):
    if str(cards) not in ['0','1','2','4','8','16'] or model!='bw1100' or image!='pytorch-dtk26.04' or script!='ci/arc-profile.sh':
        raise ValueError('unsupported test card/model/image/script contract')
    cards=int(cards);local=min(cards,8)
    return {'cards':cards,'local_cards':local,'replicas':2 if cards==16 else 1,
            'cpu':'16' if cards in [0,8,16] else '8','memory':{0:'16Gi',1:'16Gi',2:'16Gi',4:'32Gi',8:'64Gi',16:'64Gi'}[cards]}

def bundle(root):
    previous=base.FILES
    try:base.FILES=FILES;return base.bundle(root)
    finally:base.FILES=previous

def manifest(name,owner,cards,run_id,runner,payload,mode):
    f=profile(cards,'bw1100','pytorch-dtk26.04','ci/arc-profile.sh')
    if mode not in ['success','failure','timeout','cancel','orphan']:raise ValueError('unsupported fault mode')
    j=base.manifest(name,owner,'cpu',run_id,runner,payload);j['metadata']['namespace']=NS
    j['metadata']['labels']['ci.hygon.cn/profile-cards']=str(f['cards'])
    j['spec'].update(queue=QUEUE,minAvailable=f['replicas'])
    # Every replica must finish; TaskCompleted would otherwise stop siblings early.
    j['spec']['policies']=[{'event':'PodFailed','action':'TerminateJob'}]
    t=j['spec']['tasks'][0];t['replicas']=f['replicas'];t['template']['metadata']['labels']['ci.hygon.cn/profiles']='true'
    p=t['template']['spec'];p['serviceAccountName']='arc-profiles-compute'
    p['activeDeadlineSeconds']=120 if mode=='timeout' else 300
    p['volumes']=[{'name':'shm','emptyDir':{'medium':'Memory','sizeLimit':'1Gi'}}]
    if f['replicas']==2:
        del p['nodeSelector']
        p['affinity']={'nodeAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':NODES}]}]}},
            'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[{'topologyKey':'kubernetes.io/hostname','labelSelector':{'matchLabels':{base.LABEL:owner}}}]}}
    c=p['containers'][0];c['image']=fleet.IMAGE;c['volumeMounts']=[{'name':'shm','mountPath':'/dev/shm'}]
    r={'cpu':f['cpu'],'memory':f['memory'],'ephemeral-storage':'2Gi'}
    if f['local_cards']:r['hygon.com/hcu']=str(f['local_cards'])
    c['resources']={'requests':dict(r),'limits':dict(r)}
    c['env'] += [{'name':'CI_CARDS','value':str(f['cards'])},{'name':'CI_LOCAL_CARDS','value':str(f['local_cards'])},
        {'name':'CI_NNODES','value':str(f['replicas'])},{'name':'CI_MODE','value':mode},
        {'name':'CI_NODE_RANK','valueFrom':{'fieldRef':{'fieldPath':"metadata.labels['volcano.sh/task-index']"}}},
        {'name':'NODE_NAME','valueFrom':{'fieldRef':{'fieldPath':'spec.nodeName'}}},
        {'name':'MASTER_ADDR','value':'arc-profiles-master.'+NS+'.svc.cluster.local'},
        {'name':'GLOO_SOCKET_IFNAME','value':'eth0'},{'name':'NCCL_SOCKET_IFNAME','value':'eth0'},
        {'name':'NCCL_IB_DISABLE','value':'1'},{'name':'NCCL_DEBUG','value':'INFO'},
        {'name':'NCCL_DEBUG_SUBSYS','value':'INIT,NET,ENV'}]
    c['command'][-1]="""import base64,gzip,json,pathlib,os,sys
d=json.loads(gzip.decompress(base64.b64decode(%r)));allowed=%r
assert set(d)==set(allowed)
root=pathlib.Path('/tmp/arc-profile-source');root.mkdir()
for name,content in d.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
os.chdir(str(root));os.execv('/bin/bash',['bash','ci/arc-profile.sh'])
"""%(payload,list(FILES))
    return j

def validate_results(cards,ranks,logs):
    f=profile(cards,'bw1100','pytorch-dtk26.04','ci/arc-profile.sh');world=max(1,f['cards'])
    assert set(ranks)=={str(i) for i in range(f['replicas'])}
    nodes=set()
    for k,v in ranks.items():
        assert v and v['passed'] and v['node_rank']==int(k) and v['visible_cards']==f['local_cards'] and v['build_passed']
        nodes.add(v['node']);assert v['node'] in (NODES if f['replicas']==2 else ['github-nmz3'])
        if f['cards']:
            assert v['world_size']==world and v['rounds']==10 and v['all_reduce'] and v['all_gather'] and v['transport']=='socket'
            ids=v['identities'];assert len(ids)==world and [a['rank'] for a in ids]==list(range(world))
            for a in ids:
                assert a['node_rank']==a['rank']//f['local_cards'] and a['local_rank']==a['rank']%f['local_cards']
                assert a['node']==ranks[str(a['node_rank'])]['node']
            assert len({a['ip'] for a in ids})==f['replicas']
            assert 'NET/Socket' in logs[k] or f['replicas']==1,'socket transport not proved'
    assert len(nodes)==f['replicas']
    if f['replicas']==2:assert ranks['0']['identities']==ranks['1']['identities']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('cards',choices=['0','1','2','4','8','16','cleanup-only'])
    ap.add_argument('--mode',choices=['success','failure','timeout','cancel','orphan'],default='success')
    a=ap.parse_args();run_id=os.environ['GITHUB_RUN_ID'];runner=os.environ['RUNNER_NAME']
    assert run_id.isdigit() and runner
    base.NS=NS;out=Path(os.environ['RUNNER_TEMP'])/OUT;out.mkdir(exist_ok=True);own=out/'ownership.json';sp=out/'summary.json'
    if a.cards=='cleanup-only':
        if own.exists():base.cleanup(json.loads(own.read_text()),run_id,runner)
        (out/'post-cleanup.json').write_text(json.dumps({'verified':True,'run_id':run_id}));return
    ensure_window();profile(a.cards,os.environ['CI_MODEL'],os.environ['CI_IMAGE'],os.environ['CI_SCRIPT'])
    assert not own.exists(),'ownership ledger already exists'
    r={'owner':uuid.uuid4().hex,'uid':None};r['name']='arc-e2e-'+r['owner'][:16];own.write_text(json.dumps(r))
    summary={'cards':int(a.cards),'mode':a.mode,'run_id':run_id,'runner':runner,'passed':False,'cleanup_verified':False}
    sp.write_text(json.dumps(summary))
    def interrupt(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    try:
        assert not base.get('get',base.RESOURCE)['items'] and not base.get('get','pods')['items'],'scope not empty'
        for verb,res,want in [('create',base.RESOURCE,'yes'),('get','secrets','no'),('create','pods','no'),('create','rolebindings','no')]:
            assert base.kube('auth','can-i',verb,res,check=False).stdout.strip()==want,'RBAC boundary mismatch'
        root=Path(__file__).resolve().parents[1];payload,hashes=bundle(root)
        (out/'source.json').write_text(json.dumps({'sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'files':hashes}))
        created=json.loads(base.kube('create','-f','-','-o','json',data=manifest(r['name'],r['owner'],a.cards,run_id,runner,payload,a.mode)).stdout)
        r['uid']=created['metadata']['uid'];own.write_text(json.dumps(r));print('PROFILE_CREATED '+json.dumps(r),flush=True)
        until=time.monotonic()+370;expected=2 if a.cards=='16' else 1
        while time.monotonic()<until:
            job=base.get('get',base.RESOURCE,r['name']);assert job['metadata']['uid']==r['uid']
            pods=base.get('get','pods','-l',base.LABEL+'='+r['owner'])['items'];assert len(pods)<=expected
            ranks={};logs={};terms=[]
            for p in pods:
                assert any(o['uid']==r['uid'] for o in p['metadata'].get('ownerReferences',[]))
                rank=p['metadata']['labels'].get('volcano.sh/task-index');assert rank in ['0','1'] and rank not in ranks
                dest=out/('rank-'+rank);dest.mkdir(exist_ok=True);(dest/'pod.json').write_text(json.dumps(p))
                node=p['spec'].get('nodeName')
                if node:fleet.verify_image(p,node)
                log=base.store_logs(dest,p['metadata']['name']);logs[rank]=log
                markers=[json.loads(l[len('PROFILE_RESULT '):]) for l in log.splitlines() if l.startswith('PROFILE_RESULT ')]
                ranks[rank]=markers[-1] if markers else None
                if markers:
                    assert markers[-1]['node']==node and markers[-1]['node_rank']==int(rank),'reported node/rank does not match actual Pod'
                    assert json.loads((dest/'report.json').read_text())==markers[-1],'report/log mismatch'
                    assert all((dest/f).exists() for f in ['junit.xml','libaxpy.so','build.txt','repository-tests.txt']),'missing CI artifacts'
                term=next((c['state'].get('terminated') for c in p['status'].get('containerStatuses',[]) if c['name']=='compute'),None)
                if term:terms.append(term)
            phase=job.get('status',{}).get('state',{}).get('phase');summary.update(phase=phase,ranks=ranks)
            sp.write_text(json.dumps(summary,indent=2))
            print('PROFILE_STATE '+json.dumps({'phase':phase,'pods':[p['status']['phase'] for p in pods]}),flush=True)
            if phase in ['Failed','Terminated','Aborted'] or (len(terms)==expected and any(t['exitCode'] for t in terms)):
                summary['terminations']=terms;raise RuntimeError('profile compute failed '+json.dumps(terms))
            if phase=='Completed' and len(terms)==expected:
                validate_results(a.cards,ranks,logs)
                for p in pods:fleet.verify_image(p,p['spec']['nodeName'],True)
                summary['passed']=True;print('PROFILE_PASS',a.cards,flush=True);return
            time.sleep(3)
        raise RuntimeError('profile wait exceeded bound')
    except BaseException as e:summary['error']=type(e).__name__+': '+str(e);raise
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
        # Preserve failure/cancel state BEFORE possibly interrupted cleanup.
        sp.write_text(json.dumps(summary,indent=2))
        try:base.cleanup(r,run_id,runner);summary['cleanup_verified']=True
        finally:sp.write_text(json.dumps(summary,indent=2))

if __name__=='__main__':main()
