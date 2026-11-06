import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class SoakTests(unittest.TestCase):
 def test_fixed_nodes_and_profiles(self):
  m=load('soak','scripts/arc-soak.py')
  for node in ['github-nmz3','github-nmz4','github-nmz6']:
   for case in ['cpu','cpu-build','hcu1','hcu2','hcu4','hcu8','failure','cancel','timeout']:
    j=m.build_manifest('arc-e2e-'+'a'*16,'a'*32,case,'123','runner','payload',node)
    p=j['spec']['tasks'][0]['template']['spec'];c=p['containers'][0]
    self.assertEqual(j['metadata']['namespace'],'github-ci-arc-soak')
    self.assertEqual(p['nodeSelector'],{'kubernetes.io/hostname':node})
    self.assertFalse(p['automountServiceAccountToken'])
    self.assertEqual(c['resources']['requests'],c['resources']['limits'])
    self.assertNotIn('volumes',p)
  with self.assertRaises(ValueError):m.build_manifest('x','x','cpu','1','r','x','github-nmz1')
 def test_cpu_fault_profiles_never_allocate_hcu(self):
  m=load('soak_fault','scripts/arc-soak.py')
  for case in ['cpu-failure','cpu-cancel','cpu-timeout','cpu-orphan']:
   j=m.build_manifest('arc-e2e-'+'a'*16,'a'*32,case,'123','runner','payload','github-nmz3')
   c=j['spec']['tasks'][0]['template']['spec']['containers'][0]
   self.assertNotIn('hygon.com/hcu',c['resources']['limits'])
 def test_namespace_isolated_and_no_admin_access(self):
  m=load('resources','deploy/arc-soak/resources.py');objs=m.resources(ROOT)
  ns=next(x for x in objs if x['kind']=='Namespace')
  self.assertEqual(ns['metadata']['name'],'github-ci-arc-soak')
  role=next(x for x in objs if x['kind']=='Role')
  self.assertFalse(any('secrets' in r['resources'] or '*' in r['resources'] or 'pods/exec' in r['resources'] for r in role['rules']))
  quota=next(x for x in objs if x['kind']=='ResourceQuota')
  self.assertEqual(quota['spec']['hard']['requests.hygon.com/hcu'],'24')
  policy=next(x for x in objs if x['kind']=='ValidatingAdmissionPolicy')
  self.assertIn('github-nmz6',str(policy))
  self.assertIn('runAsNonRoot == true',str(policy))

if __name__=='__main__':unittest.main()
