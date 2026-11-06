import importlib.util
from pathlib import Path
import unittest

S=importlib.util.spec_from_file_location('e2e',Path(__file__).parents[1]/'scripts/arc-ci-e2e.py')
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)

class E2ETests(unittest.TestCase):
    def test_profiles(self):
        for case,cards in [('cpu',0),('hcu1',1),('hcu2',2),('failure',1),('cancel',1)]:
            j=m.manifest('e2e-test','a'*32,case,'123','runner','payload')
            p=j['spec']['tasks'][0]['template']['spec'];r=p['containers'][0]['resources']
            self.assertEqual(int(r['limits'].get('hygon.com/hcu',0)),cards)
            self.assertEqual(r['requests'],r['limits'])
            self.assertFalse(p['automountServiceAccountToken'])
            self.assertEqual(p['nodeSelector'],{'kubernetes.io/hostname':'github-nmz3'})
            self.assertNotIn('volumes',p)
            self.assertEqual(p['securityContext']['runAsUser'],1001)
    def test_invalid_case(self):
        with self.assertRaises(ValueError):m.manifest('x','x','arbitrary','1','r','x')
    def test_bundle_only_allowlisted_files(self):
        payload,info=m.bundle(Path(__file__).parents[1])
        self.assertEqual(set(info),set(m.FILES))
        self.assertLess(len(payload),200000)
    def test_invalid_artifact_path(self):
        for p in ['../secret','/tmp/x','foo/bar']:
            with self.assertRaises(ValueError):m.artifact_name(p)
    def test_cleanup_record(self):
        m.validate_record({'owner':'a'*32,'name':'arc-e2e-'+'a'*16,'uid':None})
        with self.assertRaises(ValueError):m.validate_record({'owner':'a'*32,'name':'production','uid':None})

if __name__=='__main__':unittest.main()
