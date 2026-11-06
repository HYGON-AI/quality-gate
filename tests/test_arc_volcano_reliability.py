import importlib.util
from pathlib import Path
import unittest

S = importlib.util.spec_from_file_location('rel', Path(__file__).parents[1] / 'scripts/arc-volcano-reliability.py')
rel = importlib.util.module_from_spec(S)
S.loader.exec_module(rel)


class ReliabilityTest(unittest.TestCase):
    def test_all_modes_are_bounded_cpu_only(self):
        for mode in rel.MODES:
            if mode == 'recovery':
                continue
            m = rel.make_manifest('test', 'owner', mode, '123', 'runner-test')
            p = m['spec']['tasks'][0]['template']['spec']
            self.assertLessEqual(p['activeDeadlineSeconds'], 120)
            self.assertFalse(p['automountServiceAccountToken'])
            self.assertNotIn('volumes', p)
            self.assertEqual(set(p['containers'][0]['resources']['requests']), {'cpu', 'memory'})
            self.assertEqual(m['metadata']['labels'][rel.RUN_LABEL], '123')
            compile(p['containers'][0]['command'][2], 'probe', 'exec')

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            rel.make_manifest('test', 'owner', 'arbitrary', '123', 'runner')

    def test_orphan_bounds(self):
        m = rel.make_manifest('test', 'owner', 'runner-loss', '123', 'runner')
        self.assertEqual(m['spec']['ttlSecondsAfterFinished'], 30)
        self.assertEqual(m['spec']['tasks'][0]['template']['spec']['activeDeadlineSeconds'], 25)

    def test_queue_requests(self):
        m = rel.make_manifest('test', 'owner', 'queue', '123', 'runner')
        self.assertEqual(m['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['requests']['cpu'], '500m')


if __name__ == '__main__':
    unittest.main()
