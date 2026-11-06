import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class PairTests(unittest.TestCase):
 def test_gang_is_cpu_only_two_distinct_approved_nodes(self):
  m=load('pair','scripts/arc-pair.py')
  for pair,nodes in m.PAIRS.items():
   j=m.manifest('arc-e2e-'+'a'*16,'a'*32,pair,'123','runner','payload')
   self.assertEqual(j['metadata']['namespace'],'github-ci-arc-pair')
   self.assertEqual(j['spec']['minAvailable'],2)
   t=j['spec']['tasks'][0];self.assertEqual(t['replicas'],2)
   p=t['template']['spec'];self.assertFalse(p['automountServiceAccountToken'])
   self.assertEqual(p['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'],list(nodes))
   anti=p['affinity']['podAntiAffinity']['requiredDuringSchedulingIgnoredDuringExecution'][0]
   self.assertEqual(anti['topologyKey'],'kubernetes.io/hostname')
   self.assertEqual(anti['labelSelector']['matchLabels'],{'ci.hygon.cn/e2e-owner':'a'*32})
   self.assertNotIn('hygon.com/hcu',p['containers'][0]['resources']['limits'])
   self.assertEqual(p['securityContext']['runAsUser'],1001)
   self.assertNotIn('volumes',p)
   self.assertIn('tests/fixtures/arc_e2e/run_pair.py',p['containers'][0]['command'][-1])
   compile(p['containers'][0]['command'][-1],'pair_bootstrap','exec')
   self.assertTrue(any(e['name']=='RANK' and 'valueFrom' in e for e in p['containers'][0]['env']))
  with self.assertRaises(ValueError):m.manifest('x','x','nmz1-nmz2','1','r','x')
 def test_pair_resources_do_not_grant_services_or_secrets(self):
  m=load('pair_resources','deploy/arc-pair/resources.py');objs=m.resources(ROOT)
  role=next(x for x in objs if x['kind']=='Role')
  self.assertFalse(any(any(r in rule['resources'] for r in ['secrets','services','pods/exec','*']) for rule in role['rules']))
  q=next(x for x in objs if x['kind']=='ResourceQuota')['spec']['hard']
  self.assertEqual(q['count/jobs.batch.volcano.sh'],'1');self.assertEqual(q['requests.hygon.com/hcu'],'0')
  svc=next(x for x in objs if x['kind']=='Service');self.assertEqual(svc['spec']['clusterIP'],'None')
  self.assertEqual(svc['spec']['selector']['volcano.sh/task-index'],'0')
  policies=[x for x in objs if x['kind']=='NetworkPolicy']
  self.assertEqual(len(policies),3)
  self.assertTrue(any(x['spec'].get('ingress') for x in policies))
 def test_pair_fixture_syntax(self):
  compile((ROOT/'tests/fixtures/arc_e2e/run_pair.py').read_text(),'pair_fixture','exec')

if __name__=='__main__':unittest.main()
