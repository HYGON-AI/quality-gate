#!/usr/bin/env python3
"""Bounded non-root account-image validation; nmz3 only, no privilege change."""
import calendar,importlib.util,json,os,sys,time
from pathlib import Path

s=importlib.util.spec_from_file_location('account_base',Path(__file__).with_name('arc-ci-e2e.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
NS='github-ci-arc-account';QUEUE='arc-account'
IMAGE='quality-gate-hcu-test:nonroot-20261106-v1'
IMAGE_ID='sha256:a290bf32261fecc6420b52c9b7ba44d3e8dc41ab78f19a5c597a82b3725c1826'
ORIGINAL_MANIFEST=base.manifest
ORIGINAL_STORE_LOGS=base.store_logs

def build_manifest(name,owner,case,run_id,runner,payload):
    if case not in ('cpu','hcu1','hcu2'):raise ValueError('unsupported account-image case')
    j=ORIGINAL_MANIFEST(name,owner,case,run_id,runner,payload)
    j['metadata']['namespace']=NS;j['spec']['queue']=QUEUE
    p=j['spec']['tasks'][0]['template']['spec'];p['serviceAccountName']='arc-account-compute'
    p['containers'][0]['image']=IMAGE
    return j

def verify_image(pod,required=False):
    image=next((c.get('imageID') for c in pod.get('status',{}).get('containerStatuses',[]) if c.get('name')=='compute'),None)
    if not image and not required:return
    if image not in (IMAGE_ID,'docker://'+IMAGE_ID):raise RuntimeError('account-image immutable local ID mismatch: '+str(image))

def store_logs(out,pod):
    verify_image(json.loads((out/'pod.json').read_text()))
    return ORIGINAL_STORE_LOGS(out,pod)

def main():
    case=sys.argv[1:] or []
    if len(case)!=1 or case[0] not in ('cpu','hcu1','hcu2','cleanup-only'):raise ValueError('unsupported account-image case')
    if case[0]!='cleanup-only' and time.time()>=calendar.timegm((2026,11,6,14,45,0)):raise RuntimeError('submission window closed')
    base.NS=NS;base.QUEUE=QUEUE;base.manifest=build_manifest;base.store_logs=store_logs
    base.main()
    if case[0]!='cleanup-only':
        out=Path(os.environ['RUNNER_TEMP'])/'arc-ci-e2e'
        verify_image(json.loads((out/'pod.json').read_text()),True)
        (out/'image-identity.json').write_text(json.dumps({'verified':True,'image_id':IMAGE_ID,'node':'github-nmz3'}))
        print('NONROOT_IMAGE_IDENTITY_VERIFIED '+IMAGE_ID,flush=True)

if __name__=='__main__':main()
