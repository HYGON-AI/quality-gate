import copy,importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class CollectiveTests(unittest.TestCase):
 def test_manifest_bounds(self):
  m=load('collective','scripts/arc-collective.py')
  for pair,nodes in m.pair.PAIRS.items():
   j=m.manifest('arc-e2e-'+'a'*16,'a'*32,pair,'123','runner','dummy');t=j['spec']['tasks'][0];p=t['template']['spec'];c=p['containers'][0]
   self.assertEqual(j['spec']['minAvailable'],2);self.assertEqual(t['replicas'],2)
   self.assertEqual(j['metadata']['namespace'],'github-ci-arc-collective')
   self.assertEqual(c['resources']['limits'],{'cpu':'2','memory':'16Gi','ephemeral-storage':'2Gi','hygon.com/hcu':'1'})
   self.assertFalse(p['automountServiceAccountToken']);self.assertEqual(p['securityContext']['runAsUser'],1001)
   self.assertNotIn('volumes',p);self.assertNotIn('hostNetwork',p)
   self.assertIn('run_collective.py',c['command'][-1]);compile(c['command'][-1],'bootstrap','exec')
   env={v['name']:v.get('value') for v in c['env']};self.assertEqual(env['NCCL_IB_DISABLE'],'1');self.assertEqual(env['NCCL_SOCKET_IFNAME'],'eth0')
 def test_resources_isolated(self):
  objs=load('collective_resources','deploy/arc-collective/resources.py').resources(ROOT)
  quota=next(x for x in objs if x['kind']=='ResourceQuota')['spec']['hard'];self.assertEqual(quota['requests.hygon.com/hcu'],'2');self.assertEqual(quota['count/jobs.batch.volcano.sh'],'1')
  role=next(x for x in objs if x['kind']=='Role');self.assertFalse(any(r in rule['resources'] for rule in role['rules'] for r in ['secrets','services','pods/exec','*']))
  net=next(x for x in objs if x['kind']=='NetworkPolicy' and x['metadata']['name']=='arc-collective-tcp')['spec']
  self.assertEqual(net['egress'][0]['ports'],[{'protocol':'TCP'}]);self.assertNotIn('ipBlock',str(net))
 def test_proof_rejects_false_or_missing_results(self):
  m=load('collective','scripts/arc-collective.py');nodes=['github-nmz3','github-nmz4'];ips={'0':'10.1.0.1','1':'10.1.0.2'}
  identities=[{'rank':i,'node':nodes[i],'ip':ips[str(i)]} for i in range(2)]
  ranks={str(i):{'passed':True,'rank':i,'world_size':2,'node':nodes[i],'visible_cards':1,'backends':{b:{'passed':True,'rounds':20,'all_reduce':True,'all_gather':True,'identities':identities} for b in ['gloo','nccl']},'transport':'socket','ib_disabled':True} for i in range(2)}
  logs={str(i):'NCCL INFO Using network Socket\nNCCL INFO NET/Socket : eth0' for i in range(2)}
  m.validate_results('nmz3-nmz4',ranks,set(nodes),ips,logs)
  for field in ['passed','visible_cards','backends','transport']:
   broken=copy.deepcopy(ranks);broken['1'][field]=None
   with self.assertRaises((AssertionError,KeyError,TypeError)):m.validate_results('nmz3-nmz4',broken,set(nodes),ips,logs)
  with self.assertRaises(AssertionError):m.validate_results('nmz3-nmz4',ranks,set(nodes),ips,{'0':'','1':''})
 def test_fixture_syntax(self):
  compile((ROOT/'tests/fixtures/arc_e2e/run_collective.py').read_text(),'fixture','exec')
