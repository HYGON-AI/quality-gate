import copy,importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('combinations',Path(__file__).parents[1]/'scripts/arc-hcu-combinations.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def child(slot,case,cards,start=10,end=45,minors=None):
    return {'slot':str(slot),'case':case,'node':'github-nmz3','name':'job'+str(slot),
      'container_started':start-2,'container_finished':end+2,
      'report':{'passed':True,'visible_cards':cards,'gpu_compute_started_at':start,'gpu_compute_finished_at':end,
        'compile_started_at':start,'compile_finished_at':end,
        'device_nodes':[{'path':'/dev/dri/renderD'+str(x),'major':226,'minor':x} for x in (minors or [])]}}

class CombinationTests(unittest.TestCase):
    def test_submission_cutoff(self):
        m.ensure_window(0)
        with self.assertRaises(RuntimeError):m.ensure_window(m.calendar.timegm((2026,11,6,14,45,0)))

    def test_fixed_plans_fit_budgets(self):
        for scenario,count in [('split4',2),('mixed',2),('gpu-queue',2),('cpu-queue',3)]:
            jobs=m.plan(scenario,'github-nmz3');self.assertEqual(len(jobs),count)
            for node in m.fleet.IMAGE_IDS:
                specs=[m.fleet.build_manifest('x','a'*32,j['case'],'123','runner','dummy',j['node'])['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits'] for j in jobs if j['node']==node]
                self.assertLessEqual(sum(int(x['cpu']) for x in specs),64)
                self.assertLessEqual(sum(int(x['memory'][:-2]) for x in specs),64)
        for scenario,node in [('arbitrary','github-nmz3'),('mixed','github-nmz1')]:
            with self.assertRaises(ValueError):m.plan(scenario,node)

    def test_split_requires_overlap_and_disjoint_devices(self):
        a=child(0,'hcu4',4,minors=[128,129,130,131]);b=child(1,'hcu4',4,start=20,end=55,minors=[132,133,134,135])
        self.assertGreater(m.validate_evidence('split4',[a,b],[],[])['overlap_seconds'],0)
        bad=copy.deepcopy(b);bad['report']['device_nodes']=a['report']['device_nodes']
        with self.assertRaises(AssertionError):m.validate_evidence('split4',[a,bad],[],[])
        late=child(1,'hcu4',4,start=60,end=95,minors=[132,133,134,135])
        with self.assertRaises(AssertionError):m.validate_evidence('split4',[a,late],[],[])

    def test_mixed_needs_real_phase_overlap(self):
        a=child(0,'cpu-build',0);b=child(1,'hcu4',4,start=20,end=55,minors=[128,129,130,131])
        self.assertGreater(m.validate_evidence('mixed',[a,b],[],[])['overlap_seconds'],0)
        del a['report']['compile_started_at']
        with self.assertRaises(AssertionError):m.validate_evidence('mixed',[a,b],[],[])

    def test_gpu_queue_requires_pending_event_and_backfill(self):
        a=child(0,'hcu8',8,minors=list(range(128,136)));b=child(1,'hcu1',1,start=50,end=85,minors=[128])
        timeline=[{'jobs':[{'slot':'0','pod_phase':'Running','phase':'Running'},{'slot':'1','pod_phase':'Pending','phase':'Pending'}]}]
        events=[{'involvedObject':{'name':'job1'},'reason':'FailedScheduling','message':'Insufficient hygon.com/hcu resource'}]
        self.assertTrue(m.validate_evidence('gpu-queue',[a,b],timeline,events)['backfill_verified'])
        with self.assertRaises(AssertionError):m.validate_evidence('gpu-queue',[a,b],[],events)
        with self.assertRaises(AssertionError):m.validate_evidence('gpu-queue',[a,b],timeline,[])
        b['container_started']=20
        with self.assertRaises(AssertionError):m.validate_evidence('gpu-queue',[a,b],timeline,events)

    def test_cpu_queue_any_one_waiter(self):
        jobs=[child(0,'cpu-build',0),child(1,'cpu-build',0),child(2,'cpu-build',0,start=50,end=85)]
        timeline=[{'jobs':[{'slot':str(i),'pod_phase':'Running' if i<2 else 'Pending','phase':'Running' if i<2 else 'Pending'} for i in range(3)]}]
        events=[{'involvedObject':{'name':'job2'},'message':'queue CPU capability insufficient resource'}]
        self.assertTrue(m.validate_evidence('cpu-queue',jobs,timeline,events)['backfill_verified'])

    def test_cleanup_attempts_every_owned_uid_and_rejects_bad_owner(self):
        records=[{'owner':'a'*32,'name':'arc-e2e-'+'a'*16,'uid':None},{'owner':'b'*32,'name':'arc-e2e-'+'b'*16,'uid':None}]
        calls=[]
        def delete(r,*_):
            calls.append(r['name'])
            if r is records[0]:raise RuntimeError('controlled cleanup error')
        self.assertEqual(len(m.cleanup_all(records,'123','runner',delete)),1)
        self.assertEqual(len(calls),2)
        calls.clear();bad={'owner':'invalid','name':'foreign','uid':None}
        self.assertEqual(len(m.cleanup_all([bad],'123','runner',delete)),1)
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
