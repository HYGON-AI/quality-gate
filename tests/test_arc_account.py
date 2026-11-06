import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class AccountTests(unittest.TestCase):
    def test_manifest_is_narrow_nonroot(self):
        m=load('account_test','scripts/arc-account.py')
        j=m.build_manifest('arc-e2e-'+'a'*16,'a'*32,'hcu2','123','runner','dummy')
        self.assertEqual(j['metadata']['namespace'],'github-ci-arc-account')
        p=j['spec']['tasks'][0]['template']['spec'];c=p['containers'][0]
        self.assertEqual(p['securityContext']['runAsUser'],1001)
        self.assertEqual(p['nodeSelector'],{'kubernetes.io/hostname':'github-nmz3'})
        self.assertFalse(p['automountServiceAccountToken'])
        self.assertEqual(c['image'],m.IMAGE)
        self.assertEqual(c['imagePullPolicy'],'Never')
        self.assertEqual(c['resources']['limits']['hygon.com/hcu'],'2')
        with self.assertRaises(ValueError):m.build_manifest('x','a'*32,'hcu4','123','runner','dummy')

    def test_image_identity_fails_closed(self):
        m=load('account_image','scripts/arc-account.py')
        m.verify_image({'status':{'containerStatuses':[{'name':'compute','imageID':'docker://'+m.IMAGE_ID}]}},True)
        for pod in [{},{'status':{'containerStatuses':[{'name':'compute','imageID':'docker://sha256:'+'0'*64}]}}]:
            with self.assertRaises(RuntimeError):m.verify_image(pod,True)

    def test_new_boundary_keeps_old_policies(self):
        m=load('account_resources','deploy/arc-account/resources.py')
        objs=m.resources(ROOT)
        policy=next(x for x in objs if x['kind']=='ValidatingAdmissionPolicy')
        text=str(policy)
        self.assertIn('quality-gate-hcu-test:nonroot-20261106-v1',text)
        self.assertIn('runAsUser == 1001',text)
        self.assertIn("in ['1','2']",text)
        self.assertIn("== 'github-nmz3'",text)
        role=next(x for x in objs if x['kind']=='Role')
        self.assertNotIn('secrets',str(role));self.assertNotIn('pods/exec',str(role))
        self.assertNotIn('github-ci-arc-account',(ROOT/'deploy/arc-e2e/resources.yaml').read_text())

if __name__=='__main__':unittest.main()
