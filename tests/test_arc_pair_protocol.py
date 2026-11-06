import importlib.util,unittest
from pathlib import Path
S=importlib.util.spec_from_file_location('pair_protocol',Path(__file__).parents[1]/'tests/fixtures/arc_e2e/pair_protocol.py')
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)
class ProtocolTests(unittest.TestCase):
 def test_only_timeout_proves_denied_port(self):
  def connect(*a,**kw):raise TimeoutError('bounded denial')
  self.assertTrue(m.probe_denied_port('10.244.1.2',29501,connect)['denied'])
 def test_refused_is_not_isolation_proof(self):
  def connect(*a,**kw):raise ConnectionRefusedError('no listener')
  with self.assertRaises(ConnectionRefusedError):m.probe_denied_port('10.244.1.2',29501,connect)
 def test_reachable_forbidden_port_fails(self):
  class Conn:
   def close(self):pass
  with self.assertRaises(AssertionError):m.probe_denied_port('10.244.1.2',29501,lambda *a,**kw:Conn())

if __name__=='__main__':unittest.main()
