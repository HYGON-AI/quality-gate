import copy
import importlib.util
import unittest
import tempfile,types,json
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).parents[1]

def load():
    s = importlib.util.spec_from_file_location('profiles', ROOT/'scripts/arc-card-profiles.py')
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

class CardProfilesTests(unittest.TestCase):
    def test_card_contract_and_rejections(self):
        m = load()
        for cards in [0,1,2,4,8,16]:
            p = m.profile(str(cards),'bw1100','pytorch-dtk26.04','ci/arc-profile.sh')
            self.assertEqual(p['replicas'] * p['local_cards'], cards)
            self.assertEqual(p['replicas'], 2 if cards == 16 else 1)
        for args in [('3','bw1100','pytorch-dtk26.04','ci/arc-profile.sh'),('16','bw1000','pytorch-dtk26.04','ci/arc-profile.sh'),('1','bw1100','latest','ci/arc-profile.sh'),('1','bw1100','pytorch-dtk26.04','../../secret'),('1;id','bw1100','pytorch-dtk26.04','ci/arc-profile.sh')]:
            with self.assertRaises(ValueError):m.profile(*args)

    def test_manifest_all_six_profiles(self):
        m=load()
        for cards in [0,1,2,4,8,16]:
            j=m.manifest('arc-e2e-'+'a'*16,'a'*32,str(cards),'123','runner','payload','success')
            t=j['spec']['tasks'][0];p=t['template']['spec'];c=p['containers'][0]
            self.assertEqual(j['spec']['minAvailable'],2 if cards==16 else 1)
            self.assertEqual(t['replicas'],2 if cards==16 else 1)
            self.assertEqual(int(c['resources']['limits'].get('hygon.com/hcu',0)),min(cards,8))
            self.assertEqual(c['resources']['limits'],c['resources']['requests'])
            self.assertFalse(p['automountServiceAccountToken']);self.assertNotIn('hostNetwork',p)
            self.assertEqual(p['securityContext']['runAsUser'],1001)
            self.assertEqual(p['volumes'],[{'name':'shm','emptyDir':{'medium':'Memory','sizeLimit':'1Gi'}}])
            self.assertEqual(c['volumeMounts'],[{'name':'shm','mountPath':'/dev/shm'}])
            if cards==16:self.assertIn('podAntiAffinity',p['affinity'])
            compile(c['command'][-1],'bootstrap','exec')

    def test_fixture_proof_rejects_missing_or_duplicate_global_ranks(self):
        m=load()
        ids=[{'rank':i,'local_rank':i%8,'node_rank':i//8,'node':'github-nmz'+str(3+i//8),'ip':'10.2.0.'+str(1+i//8)} for i in range(16)]
        ranks={str(i):{'passed':True,'node_rank':i,'node':ids[i*8]['node'],'visible_cards':8,'world_size':16,'identities':ids,'rounds':10,'all_reduce':True,'all_gather':True,'transport':'socket','build_passed':True} for i in range(2)}
        logs={str(i):'NET/Socket' for i in range(2)}
        m.validate_results('16',ranks,logs)
        for broken in [dict(ranks,**{'1':None}),copy.deepcopy(ranks),copy.deepcopy(ranks)]:
            if broken.get('1') is not None:
                if broken['1']['world_size']==16:broken['1']['identities'][15]['rank']=0
            with self.assertRaises((AssertionError,TypeError)):m.validate_results('16',broken,logs)
        with self.assertRaises(AssertionError):m.validate_results('16',ranks,{'0':'','1':''})

    def test_submission_window_is_bounded(self):
        m=load();cut=1794043800
        m.ensure_window(cut-1)
        with self.assertRaises(RuntimeError):m.ensure_window(cut)

    def test_new_scope_keeps_limits_and_no_secret_access(self):
        s=importlib.util.spec_from_file_location('profile_resources',ROOT/'deploy/arc-profiles/resources.py')
        r=importlib.util.module_from_spec(s);s.loader.exec_module(r);objs=r.resources(ROOT)
        quota=next(x for x in objs if x['kind']=='ResourceQuota')['spec']['hard']
        self.assertEqual(quota['requests.hygon.com/hcu'],'16');self.assertEqual(quota['count/jobs.batch.volcano.sh'],'1')
        role=next(x for x in objs if x['kind']=='Role')
        self.assertFalse(any(k in rule['resources'] for rule in role['rules'] for k in ['secrets','services','pods/exec','*']))
        policy=next(x for x in objs if x['kind']=='ValidatingAdmissionPolicy')
        self.assertEqual(policy['spec']['failurePolicy'],'Fail')
        for cards in ['0','1','2','4','8','16']:
            self.assertIn("profile-cards'] == '"+cards+"'",policy['spec']['validations'][7]['expression'])
        self.assertIn("size(c.volumeMounts) == 1",policy['spec']['validations'][6]['expression'])

    def test_payload_and_worker_syntax(self):
        for file in ['tests/fixtures/arc_e2e/run_profile.py','tests/fixtures/arc_e2e/profile_worker.py']:
            compile((ROOT/file).read_text(),file,'exec')

    def test_independent_cleanup_records_fallback_not_false_main_success(self):
        m=load()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'summary.json').write_text(json.dumps({'run_id':'123','passed':False,'cleanup_verified':False,'error':'KeyboardInterrupt'}))
            m.record_independent_cleanup(out,'123');s=json.loads((out/'summary.json').read_text())
            self.assertFalse(s['passed']);self.assertFalse(s['main_cleanup_verified']);self.assertTrue(s['cleanup_verified'])
            self.assertEqual(s['cleanup_path'],'independent_fallback');self.assertEqual(s['error'],'KeyboardInterrupt')
            with self.assertRaises(AssertionError):m.record_independent_cleanup(out,'999')

    def test_fault_hold_runs_every_allocated_device_before_ready_and_in_loop(self):
        s=importlib.util.spec_from_file_location('profile_hold',ROOT/'tests/fixtures/arc_e2e/profile_hold.py')
        h=importlib.util.module_from_spec(s);s.loader.exec_module(h);calls=[]
        class Tensor:
            def __matmul__(self,other):calls.append('kernel');return self
            def all(self):return self
            def item(self):return True
        fake=types.SimpleNamespace(cuda=types.SimpleNamespace(device_count=lambda:2,synchronize=lambda i:calls.append(i)),set_num_threads=lambda n:None,randn=lambda *a,**kw:Tensor(),isfinite=lambda x:x)
        with patch.dict('sys.modules',{'torch':fake}),patch.object(h.time,'monotonic',side_effect=[0,0,421]),patch('builtins.print') as output:
            h.run(2,0)
        self.assertEqual(calls.count('kernel'),4);self.assertEqual(calls.count(0),2);self.assertEqual(calls.count(1),2)
        self.assertIn('"active_gpu_hold": true',output.call_args.args[0])

    def test_bootstrap_matches_real_bundle(self):
        import ast,base64,gzip,json
        m=load();payload,_=m.bundle(ROOT)
        j=m.manifest('arc-e2e-'+'a'*16,'a'*32,'16','123','runner',payload,'success')
        code=j['spec']['tasks'][0]['template']['spec']['containers'][0]['command'][-1]
        tree=ast.parse(code);allowed=ast.literal_eval(tree.body[2].value)
        self.assertEqual(set(json.loads(gzip.decompress(base64.b64decode(payload)))),set(allowed))

if __name__=='__main__':unittest.main()
