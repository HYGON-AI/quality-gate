import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class HcuSoakTests(unittest.TestCase):
    def test_node_and_profiles_bounded(self):
        m=load('fleet_manifest','scripts/arc-hcu-soak.py')
        for node in m.IMAGE_IDS:
            for case,cards in [('cpu',0),('cpu-build',0),('hcu1',1),('hcu2',2),('hcu4',4),('hcu8',8)]:
                j=m.build_manifest('arc-e2e-'+'a'*16,'a'*32,case,'123','runner','dummy',node)
                self.assertEqual(j['metadata']['namespace'],'github-ci-arc-hcu-soak')
                p=j['spec']['tasks'][0]['template']['spec'];c=p['containers'][0]
                self.assertEqual(p['nodeSelector'],{'kubernetes.io/hostname':node})
                self.assertEqual(p['securityContext']['runAsUser'],1001)
                self.assertFalse(p['automountServiceAccountToken'])
                self.assertEqual(c['image'],m.IMAGE)
                self.assertEqual(c['imagePullPolicy'],'Never')
                self.assertEqual(int(c['resources']['limits'].get('hygon.com/hcu','0')),cards)
                self.assertEqual(c['resources']['limits']['cpu'],'32' if case=='cpu-build' else '2')
        for node,case in [('github-nmz1','hcu1'),('github-nmz3','hcu16')]:
            with self.assertRaises(ValueError):m.build_manifest('x','a'*32,case,'123','runner','dummy',node)

    def test_runtime_image_id_is_node_specific(self):
        m=load('fleet_identity','scripts/arc-hcu-soak.py')
        for node,image_id in m.IMAGE_IDS.items():
            pod={'spec':{'nodeName':node},'status':{'containerStatuses':[{'name':'compute','imageID':'docker://'+image_id}]}}
            m.verify_image(pod,node,True)
            other=next(n for n in m.IMAGE_IDS if n!=node)
            with self.assertRaises(RuntimeError):m.verify_image(pod,other,True)
        with self.assertRaises(RuntimeError):m.verify_image({},'github-nmz3',True)

    def test_new_resources_do_not_weaken_old_boundary(self):
        m=load('fleet_resources','deploy/arc-hcu-soak/resources.py')
        objs=m.resources(ROOT)
        self.assertEqual(next(x for x in objs if x['kind']=='Namespace')['metadata']['name'],'github-ci-arc-hcu-soak')
        policy=str(next(x for x in objs if x['kind']=='ValidatingAdmissionPolicy'))
        self.assertIn("in ['github-nmz3','github-nmz4','github-nmz6']",policy)
        self.assertIn("in ['1','2','4','8']",policy)
        self.assertIn('runAsUser == 1001',policy)
        self.assertIn('quality-gate-hcu-test:nonroot-20261106-v1',policy)
        self.assertNotIn('secrets',str(next(x for x in objs if x['kind']=='Role')))
        self.assertNotIn('github-ci-arc-hcu-soak',(ROOT/'deploy/arc-e2e/resources.yaml').read_text())

if __name__=='__main__':unittest.main()
