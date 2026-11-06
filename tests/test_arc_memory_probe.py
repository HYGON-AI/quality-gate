import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('memory_probe',Path(__file__).parent/'fixtures/arc_e2e/memory_probe.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class MemoryProbeTests(unittest.TestCase):
    def reader(self,values):
        def read(path):
            if path not in values:raise FileNotFoundError(path)
            return values[path]
        return read
    def test_v1_and_proc_status(self):
        d=m.snapshot(self.reader({'/proc/self/status':'Name: python\nVmRSS:\t1024 kB\nVmHWM:\t2048 kB\n','/sys/fs/cgroup/memory/memory.max_usage_in_bytes':'8388608','/sys/fs/cgroup/memory/memory.limit_in_bytes':'8589934592'}))
        self.assertEqual(d['rss_bytes'],1048576)
        self.assertEqual(d['rss_peak_bytes'],2097152)
        self.assertEqual(d['cgroup_v1_peak_bytes'],8388608)
        self.assertEqual(d['cgroup_v1_limit_bytes'],8589934592)
    def test_v2_unlimited_is_not_numeric_budget(self):
        d=m.snapshot(self.reader({'/sys/fs/cgroup/memory.current':'65536','/sys/fs/cgroup/memory.peak':'131072','/sys/fs/cgroup/memory.max':'max'}))
        self.assertEqual(d['cgroup_v2_current_bytes'],65536)
        self.assertEqual(d['cgroup_v2_limit_bytes'],'max')
    def test_missing_counters_are_optional(self):
        self.assertEqual(m.snapshot(self.reader({})),{})

if __name__=='__main__':unittest.main()
