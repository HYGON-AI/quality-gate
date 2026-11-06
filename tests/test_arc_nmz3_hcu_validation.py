import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('nmz3', Path(__file__).parents[1] / 'scripts/arc-nmz3-hcu-validation.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManifestTests(unittest.TestCase):
    def pod(self, cards=1, **kw):
        return m.manifest('unit-test', 'unit-owner', cards, **kw)['spec']['tasks'][0]['template']['spec']

    def test_node_fixed(self):
        self.assertEqual(self.pod()['nodeSelector'], {'kubernetes.io/hostname': 'github-nmz3'})

    def test_no_credentials_or_host_privileges(self):
        p = self.pod()
        self.assertFalse(p['automountServiceAccountToken'])
        self.assertNotIn('volumes', p)
        c = p['containers'][0]
        self.assertFalse(c['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(c['securityContext']['capabilities']['drop'], ['ALL'])
        self.assertNotIn('volumeMounts', c)

    def test_resources_equal_and_bounded(self):
        p = self.pod(2)
        r = p['containers'][0]['resources']
        self.assertEqual(r['requests'], r['limits'])
        self.assertEqual(r['limits']['hygon.com/hcu'], 2)
        self.assertEqual(p['activeDeadlineSeconds'], 240)
        self.assertEqual(p['terminationGracePeriodSeconds'], 10)

    def test_cpu_has_no_gpu_request(self):
        r = self.pod(0, code=m.COMPILE_CODE, cpus='32', memory='32Gi')['containers'][0]['resources']
        self.assertNotIn('hygon.com/hcu', r['requests'])
        self.assertNotIn('hygon.com/hcu', r['limits'])
        self.assertEqual(r['limits']['cpu'], '32')

    def test_image_immutable_no_pull(self):
        c = self.pod()['containers'][0]
        self.assertIn('@sha256:', c['image'])
        self.assertEqual(c['imagePullPolicy'], 'Never')

    def test_no_restarts_and_owned(self):
        j = m.manifest('unit-test', 'unit-owner')
        self.assertEqual(j['spec']['maxRetry'], 0)
        self.assertEqual(j['metadata']['labels'][m.LABEL], 'unit-owner')
        self.assertEqual(self.pod()['restartPolicy'], 'Never')

    def test_workload_syntax(self):
        for code in [m.GPU_CODE, m.COMPILE_CODE, m.mixed_code(), m.hold_code()]:
            compile(code, 'workload', 'exec')

    def test_log_parser_ignores_runtime_warning(self):
        self.assertEqual(m.events('warning\n{"event":"ok"}\n'), [{'event': 'ok'}])


if __name__ == '__main__':
    unittest.main()
