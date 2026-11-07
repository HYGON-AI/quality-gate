import importlib.util, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class NativeAcceptTest(unittest.TestCase):
    def setUp(self):
        file=ROOT/'deploy/arc-native/values.py'
        self.assertTrue(file.exists(),'native pool generator missing')
        spec=importlib.util.spec_from_file_location('native_values',file)
        self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)

    def test_fixed_profiles_have_health_model_node_and_no_credentials(self):
        for cards in [1,2,4,8]:
            v=self.mod.values(cards);p=v['template']['spec'];r=p['containers'][0]
            self.assertEqual((v['minRunners'],v['maxRunners']),(0,1))
            self.assertEqual(p['nodeSelector'],{'kubernetes.io/hostname':'github-nmz4','ci.hygon.cn/hcu-model':'bw1100','ci.hygon.cn/hcu-health':'ok'})
            self.assertFalse(p['automountServiceAccountToken'])
            self.assertEqual(r['resources']['requests']['hygon.com/hcu'],cards)
            self.assertEqual(r['resources']['limits']['hygon.com/hcu'],cards)
            self.assertEqual(r['securityContext']['capabilities']['drop'],['ALL'])
            self.assertFalse(r['securityContext']['allowPrivilegeEscalation'])
            self.assertTrue(p['securityContext']['runAsNonRoot'])
            self.assertEqual(v['runnerGroup'],'ci-k8s')
            self.assertEqual(v['githubConfigSecret'],'github-arc-app')
            self.assertEqual(p['schedulerName'],'volcano')
            self.assertEqual(v['template']['metadata']['annotations']['scheduling.volcano.sh/queue-name'],'ci-hcu')
            self.assertEqual(p['volumes'][0]['emptyDir']['medium'],'Memory')
            self.assertNotIn('hostPath',str(p));self.assertNotIn('secret',str(p['volumes']).lower())
            self.assertEqual(r['imagePullPolicy'],'Never')

    def test_invalid_profiles_rejected(self):
        for c in [0,3,16,'1','../../bad']:
            with self.assertRaises(ValueError):self.mod.values(c)

    def test_image_is_offline_nonroot_and_separate_from_credentials(self):
        t=(ROOT/'deploy/arc-native/Dockerfile').read_text()
        self.assertIn('FROM ghcr.io/actions/actions-runner:2.338.1 AS runner',t)
        self.assertIn('FROM quality-gate-hcu-test:nonroot-20261106-v1',t)
        self.assertIn('COPY --from=runner --chown=1001:1001 /home/runner /home/runner',t)
        self.assertIn('USER 1001:1001',t)
        self.assertIn('Runner.Listener --version',t)
        for bad in ['apt-get','curl ','wget ','.kube','.pem','privileged','chmod 777']:
            self.assertNotIn(bad,t)

if __name__=='__main__':unittest.main()
