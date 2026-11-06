#!/usr/bin/env python3
"""Bounded Gloo and RCCL socket collectives, preserving CPU pair permissions."""
import importlib.util,json
from pathlib import Path
def load(name,path):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
pair=load('collective_pair','arc-pair.py');fleet=load('collective_fleet','arc-hcu-soak.py')
NS='github-ci-arc-collective';QUEUE='arc-collective';ORIGINAL=pair.manifest
def manifest(name,owner,which,run_id,runner,payload):
 j=ORIGINAL(name,owner,which,run_id,runner,payload);j['metadata']['namespace']=NS;j['spec']['queue']=QUEUE
 t=j['spec']['tasks'][0];t['template']['metadata']['labels'].pop('ci.hygon.cn/pair');t['template']['metadata']['labels']['ci.hygon.cn/collective']='true'
 p=t['template']['spec'];p['serviceAccountName']='arc-collective-compute';c=p['containers'][0]
 c['image']=fleet.IMAGE
 for kind in ['requests','limits']:c['resources'][kind].update(memory='16Gi',**{'hygon.com/hcu':'1'})
 c['command'][-1]=c['command'][-1].replace('run_pair.py','run_collective.py')
 c['env'] += [{'name':k,'value':v} for k,v in {'GLOO_SOCKET_IFNAME':'eth0','NCCL_SOCKET_IFNAME':'eth0','NCCL_IB_DISABLE':'1','NCCL_DEBUG':'INFO','NCCL_DEBUG_SUBSYS':'INIT,NET,ENV','MASTER_ADDR':'arc-collective-master.github-ci-arc-collective.svc.cluster.local'}.items()]
 return j
def validate_results(which,ranks,nodes,ips,logs):
 assert nodes==set(pair.PAIRS[which]) and set(ranks)=={'0','1'}
 identities=[{'rank':i,'node':ranks[str(i)]['node'],'ip':ips[str(i)]} for i in range(2)]
 for k,v in ranks.items():
  assert v and v['passed'] and v['rank']==int(k) and v['world_size']==2 and v['visible_cards']==1
  assert v['transport']=='socket' and v['ib_disabled'] is True
  assert set(v['backends'])=={'gloo','nccl'}
  for result in v['backends'].values():
   assert result['passed'] and result['rounds']==20 and result['all_reduce'] and result['all_gather'] and result['identities']==identities
  assert 'NET/Socket' in logs[k] or 'Using network Socket' in logs[k], 'RCCL socket transport not proved'
def main():
 pair.NS=NS;pair.QUEUE=QUEUE;pair.OUT='arc-collective';pair.MARKER='COLLECTIVE_RESULT '
 pair.manifest=manifest;pair.validate_results=validate_results
 pair.base.FILES=pair.base.FILES+('tests/fixtures/arc_e2e/run_collective.py',)
 original=pair.base.store_logs
 def store_logs(out,pod):
  p=json.loads((out/'pod.json').read_text());node=p['spec'].get('nodeName')
  if node:fleet.verify_image(p,node,any(c.get('state',{}).get('terminated') for c in p.get('status',{}).get('containerStatuses',[])))
  return original(out,pod)
 pair.base.store_logs=store_logs
 pair.main()
if __name__=='__main__':main()
