#!/usr/bin/env python3
"""Five-hour test dispatcher: fixed profiles/nodes, same UID cleanup/report engine."""
import importlib.util,os,sys,time,calendar
from pathlib import Path

s=importlib.util.spec_from_file_location('e2e_base',Path(__file__).with_name('arc-ci-e2e.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
ORIGINAL_MANIFEST=base.manifest
NODES=('github-nmz3','github-nmz4','github-nmz6')

def build_manifest(name,owner,case,run_id,runner,payload,node):
 if node not in NODES:raise ValueError('unapproved test node')
 j=ORIGINAL_MANIFEST(name,owner,case,run_id,runner,payload)
 j['metadata']['namespace']='github-ci-arc-soak';j['spec']['queue']='arc-soak'
 p=j['spec']['tasks'][0]['template']['spec'];p['nodeSelector']={'kubernetes.io/hostname':node}
 p['serviceAccountName']='arc-soak-compute'
 if case=='cpu-build':
  for r in ['requests','limits']:p['containers'][0]['resources'][r].update(cpu='32',memory='16Gi')
 return j

def main():
 if sys.argv[1:]!=['cleanup-only'] and time.time()>=calendar.timegm((2026,11,6,14,45,0)):
  raise RuntimeError('five-hour test submission window has closed')
 node=os.environ['CI_NODE']
 if node not in NODES:raise ValueError('unapproved test node')
 base.NS='github-ci-arc-soak';base.QUEUE='arc-soak'
 base.manifest=lambda *a:build_manifest(*a,node=node)
 base.main()

if __name__=='__main__':main()
