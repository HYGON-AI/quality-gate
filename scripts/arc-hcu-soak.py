#!/usr/bin/env python3
"""Three-node bounded non-root HCU test using verified per-node local images."""
import calendar,importlib.util,json,os,sys,time
from pathlib import Path
s=importlib.util.spec_from_file_location('hcu_soak_base',Path(__file__).with_name('arc-ci-e2e.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
NS='github-ci-arc-hcu-soak';QUEUE='arc-hcu-soak'
IMAGE='quality-gate-hcu-test:nonroot-20261106-v1'
IMAGE_IDS={
 'github-nmz3':'sha256:a290bf32261fecc6420b52c9b7ba44d3e8dc41ab78f19a5c597a82b3725c1826',
 'github-nmz4':'sha256:95179759ec85d786f772cb20ce073e6068e8fc98b3c02016fabf8a28d853f444',
 'github-nmz6':'sha256:bede1779ae2bd596f475919df00ab647897c972bb1db57c3d67e3dd27e6f10ea'}
CASES=('cpu','cpu-build','hcu1','hcu2','hcu4','hcu8')
ORIGINAL_MANIFEST=base.manifest;ORIGINAL_STORE_LOGS=base.store_logs

def build_manifest(name,owner,case,run_id,runner,payload,node):
    if node not in IMAGE_IDS or case not in CASES:raise ValueError('unsupported fleet node/profile')
    j=ORIGINAL_MANIFEST(name,owner,case,run_id,runner,payload)
    j['metadata']['namespace']=NS;j['spec']['queue']=QUEUE
    p=j['spec']['tasks'][0]['template']['spec']
    p['serviceAccountName']='arc-hcu-soak-compute';p['nodeSelector']={'kubernetes.io/hostname':node}
    p['containers'][0]['image']=IMAGE
    if case=='cpu-build':
        for kind in ('requests','limits'):p['containers'][0]['resources'][kind].update(cpu='32',memory='16Gi')
    if case in ('hcu4','hcu8'):
        for kind in ('requests','limits'):p['containers'][0]['resources'][kind]['memory']='16Gi' if case=='hcu4' else '32Gi'
    return j

def verify_image(pod,node,required=False):
    if node not in IMAGE_IDS:raise ValueError('unapproved image node')
    actual_node=pod.get('spec',{}).get('nodeName')
    if actual_node is not None and actual_node!=node:raise RuntimeError('unexpected image node')
    image=next((c.get('imageID') for c in pod.get('status',{}).get('containerStatuses',[]) if c.get('name')=='compute'),None)
    if not image and not required:return
    if actual_node!=node or image not in (IMAGE_IDS[node],'docker://'+IMAGE_IDS[node]):raise RuntimeError('fleet immutable node/image ID mismatch: '+str(image))

def main():
    case=sys.argv[1:];node=os.environ['CI_NODE']
    if node not in IMAGE_IDS or len(case)!=1 or case[0] not in CASES+('cleanup-only',):raise ValueError('unsupported fleet request')
    if case[0]!='cleanup-only' and time.time()>=calendar.timegm((2026,11,6,14,45,0)):raise RuntimeError('submission window closed')
    base.NS=NS;base.QUEUE=QUEUE;base.manifest=lambda *args:build_manifest(*args,node=node)
    def store_logs(out,pod):
        verify_image(json.loads((out/'pod.json').read_text()),node)
        return ORIGINAL_STORE_LOGS(out,pod)
    base.store_logs=store_logs;base.main()
    if case[0]!='cleanup-only':
        out=Path(os.environ['RUNNER_TEMP'])/'arc-ci-e2e'
        verify_image(json.loads((out/'pod.json').read_text()),node,True)
        (out/'image-identity.json').write_text(json.dumps({'verified':True,'image_id':IMAGE_IDS[node],'node':node}))
        print('FLEET_IMAGE_IDENTITY_VERIFIED '+node+' '+IMAGE_IDS[node],flush=True)

if __name__=='__main__':main()
