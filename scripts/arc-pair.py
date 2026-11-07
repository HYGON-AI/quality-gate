#!/usr/bin/env python3
"""Fixed two-node CPU gang; no API token or driver devices in compute."""
import argparse,calendar,importlib.util,json,os,signal,subprocess,time,uuid
from pathlib import Path

s=importlib.util.spec_from_file_location('pair_base',Path(__file__).with_name('arc-ci-e2e.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
NS='github-ci-arc-pair';QUEUE='arc-pair'
OUT='arc-pair';MARKER='PAIR_RESULT '
PAIRS={'nmz3-nmz4':('github-nmz3','github-nmz4'),'nmz3-nmz6':('github-nmz3','github-nmz6'),'nmz4-nmz6':('github-nmz4','github-nmz6')}

def ensure_window(now=None):
 if (time.time() if now is None else now)>=calendar.timegm((2026,11,7,6,40,0)):raise RuntimeError('test submission window closed')

def manifest(name,owner,pair,run_id,runner,payload):
 if pair not in PAIRS:raise ValueError('unapproved test pair')
 j=base.manifest(name,owner,'cpu',run_id,runner,payload)
 j['metadata']['namespace']=NS;j['spec']['queue']=QUEUE;j['spec']['minAvailable']=2
 t=j['spec']['tasks'][0];t['replicas']=2;t['template']['metadata']['labels']['ci.hygon.cn/pair']='true'
 p=t['template']['spec'];p.pop('nodeSelector');p['serviceAccountName']='arc-pair-compute'
 p['affinity']={'nodeAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':list(PAIRS[pair])}]}]}},
  'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[{'topologyKey':'kubernetes.io/hostname','labelSelector':{'matchLabels':{base.LABEL:owner}}}]}}
 c=p['containers'][0]
 c['env'] += [{'name':'RANK','valueFrom':{'fieldRef':{'fieldPath':"metadata.labels['volcano.sh/task-index']"}}},
  {'name':'NODE_NAME','valueFrom':{'fieldRef':{'fieldPath':'spec.nodeName'}}}]
 code=c['command'][-1].replace("'tests/fixtures/arc_e2e/run_ci.py','cpu'","'tests/fixtures/arc_e2e/run_pair.py'")
 c['command'][-1]=code
 return j

def validate_results(pair,ranks,actual_nodes,actual_ips,logs):
 assert actual_nodes==set(PAIRS[pair]) and set(ranks)=={'0','1'}
 assert all(v and v['passed'] and v['rank']==int(k) and v['rounds']==20 for k,v in ranks.items())
 assert ranks['0']['checksum']==ranks['1']['checksum']
 assert all(v['peer_address'][0]==actual_ips[str(1-int(k))] for k,v in ranks.items())
 assert ranks['0']['local_listening_control_passed'] and all(v['denied_port_test']['denied'] for v in ranks.values())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('pair',choices=list(PAIRS)+['cleanup-only']);pair=ap.parse_args().pair
 base.NS=NS;run_id=os.environ['GITHUB_RUN_ID'];runner=os.environ['RUNNER_NAME']
 assert run_id.isdigit()
 out=Path(os.environ['RUNNER_TEMP'])/OUT;out.mkdir(exist_ok=True);own=out/'ownership.json'
 if pair=='cleanup-only':
  if own.exists():base.cleanup(json.loads(own.read_text()),run_id,runner)
  (out/'post-cleanup.json').write_text(json.dumps({'verified':True}));print('PAIR_CLEANUP_VERIFIED');return
 ensure_window()
 def interrupt(*_):raise KeyboardInterrupt()
 signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
 owner=uuid.uuid4().hex;r={'name':'arc-e2e-'+owner[:16],'owner':owner,'uid':None};own.write_text(json.dumps(r))
 summary={'pair':pair,'run_id':run_id,'runner':runner,'passed':False,'cleanup_verified':False}
 try:
  for verb,res,want in [('create',base.RESOURCE,'yes'),('get','secrets','no'),('create','services','no'),('create','pods','no'),('create','rolebindings','no')]:
   answer=base.kube('auth','can-i',verb,res,'--namespace='+NS,check=False).stdout.strip()
   if answer!=want:raise RuntimeError('unexpected pair RBAC '+verb+' '+res)
  root=Path(__file__).resolve().parents[1];payload,hashes=base.bundle(root)
  (out/'source.json').write_text(json.dumps({'checkout_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'files':hashes},indent=2))
  j=json.loads(base.kube('create','-f','-','-o','json',data=manifest(r['name'],owner,pair,run_id,runner,payload)).stdout)
  r['uid']=j['metadata']['uid'];own.write_text(json.dumps(r));print('PAIR_CREATED '+json.dumps(r),flush=True)
  until=time.monotonic()+230
  while time.monotonic()<until:
   job=base.get('get',base.RESOURCE,r['name']);pods=base.get('get','pods','-l',base.LABEL+'='+owner)['items']
   if len(pods)>2:raise RuntimeError('unexpected pair pod count')
   ranks={};actual_nodes=set();actual_ips={};exit_codes=[];logs={}
   for p in pods:
    assert any(o['uid']==r['uid'] for o in p['metadata'].get('ownerReferences',[]))
    node=p['spec'].get('nodeName');rank=p['metadata']['labels'].get('volcano.sh/task-index')
    if node is not None and node not in PAIRS[pair]:raise RuntimeError('unapproved actual node')
    if rank not in ['0','1'] or rank in ranks:raise RuntimeError('invalid rank')
    dest=out/('rank-'+rank);dest.mkdir(exist_ok=True);(dest/'pod.json').write_text(json.dumps(p,indent=2))
    log=base.store_logs(dest,p['metadata']['name']);logs[rank]=log;markers=[json.loads(l[len(MARKER):]) for l in log.splitlines() if l.startswith(MARKER)]
    ranks[rank]=markers[-1] if markers else None
    if node:actual_nodes.add(node)
    if p['status'].get('podIP'):actual_ips[rank]=p['status']['podIP']
    term=next((c.get('state',{}).get('terminated') for c in p['status'].get('containerStatuses',[]) if c['name']=='compute'),None)
    if term:exit_codes.append(term['exitCode'])
   phase=job.get('status',{}).get('state',{}).get('phase')
   if phase in ['Failed','Terminated','Aborted']:raise RuntimeError('pair job failed: '+phase)
   if len(exit_codes)==2:
    if any(exit_codes):raise RuntimeError('pair pod failed: '+str(exit_codes))
    if phase=='Completed':
     validate_results(pair,ranks,actual_nodes,actual_ips,logs)
     summary.update(passed=True,nodes=sorted(actual_nodes),ranks=ranks,phase=phase)
     print('PAIR_PASS '+json.dumps(summary),flush=True);return
   time.sleep(2)
  raise RuntimeError('pair wait exceeded bound')
 except BaseException as e:summary['error']=type(e).__name__+': '+str(e);raise
 finally:
  signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
  try:base.cleanup(r,run_id,runner);summary['cleanup_verified']=True
  finally:
   (out/'summary.json').write_text(json.dumps(summary,indent=2));print('PAIR_SUMMARY '+json.dumps(summary),flush=True)

if __name__=='__main__':main()
