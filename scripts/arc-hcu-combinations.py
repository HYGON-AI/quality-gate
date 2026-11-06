#!/usr/bin/env python3
"""Fixed multi-job compute probes with all-child UID cleanup and explicit evidence."""
import calendar,datetime,importlib.util,json,os,signal,subprocess,sys,time,uuid
from pathlib import Path
s=importlib.util.spec_from_file_location('combination_fleet',Path(__file__).with_name('arc-hcu-soak.py'))
fleet=importlib.util.module_from_spec(s);s.loader.exec_module(fleet);base=fleet.base
SCENARIOS=('split4','mixed','gpu-queue','cpu-queue')

def require(value,message):
    if not value:raise AssertionError(message)

def ensure_window(now=None):
    if (time.time() if now is None else now)>=calendar.timegm((2026,11,6,14,45,0)):raise RuntimeError('submission window closed')

def save_ownership(path,records):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(records,indent=2));os.replace(temporary,path)

def plan(scenario,node):
    if scenario not in SCENARIOS or node not in fleet.IMAGE_IDS:raise ValueError('unapproved scenario/node')
    cases={'split4':['hcu4','hcu4'],'mixed':['cpu-build','hcu4'],'gpu-queue':['hcu8','hcu1'],'cpu-queue':['cpu-build']*3}[scenario]
    nodes=list(fleet.IMAGE_IDS) if scenario=='cpu-queue' else [node]*len(cases)
    return [{'slot':str(i),'case':case,'node':nodes[i]} for i,case in enumerate(cases)]

def interval(report,prefix):
    a=report.get(prefix+'_started_at');b=report.get(prefix+'_finished_at')
    require(isinstance(a,(int,float)) and isinstance(b,(int,float)) and b>a,'missing/invalid actual '+prefix+' interval')
    return a,b

def overlap(a,b):return max(0,min(a[1],b[1])-max(a[0],b[0]))

def pending(snapshot):
    return snapshot.get('pod_phase')=='Pending' or (snapshot.get('pod_phase') is None and snapshot.get('phase') in ('Pending','Inqueue','Enqueue'))

def validate_evidence(scenario,children,timeline,events):
    require(scenario in SCENARIOS and len(children)==(3 if scenario=='cpu-queue' else 2),'wrong scenario/child count')
    for r in children:
        require(r.get('report',{}).get('passed') is True,'missing/failed child report')
        require(r['report'].get('visible_cards')==base.CASES[r['case']],'incorrect child visible-card count')
    result={}
    if scenario=='split4':
        seconds=overlap(*[interval(r['report'],'gpu_compute') for r in children])
        sets=[{(d['major'],d['minor']) for d in r['report'].get('device_nodes',[]) if d['path'].startswith('/dev/dri/renderD')} for r in children]
        require(seconds>=1 and all(len(x)==4 for x in sets) and not sets[0]&sets[1],'missing concurrent GPU work or devices overlap')
        result.update(overlap_seconds=seconds,render_devices_disjoint=True,render_devices=[sorted(x) for x in sets])
    elif scenario=='mixed':
        seconds=overlap(interval(children[0]['report'],'compile'),interval(children[1]['report'],'gpu_compute'))
        require(seconds>=1,'compile and HCU compute did not overlap')
        result.update(overlap_seconds=seconds,cpu_visible_cards=children[0]['report']['visible_cards'])
    else:
        witnesses=[]
        for row in timeline:
            jobs={j['slot']:j for j in row['jobs']}
            if len(jobs)!=len(children):continue
            running=[slot for slot,j in jobs.items() if j.get('pod_phase')=='Running']
            waits=[slot for slot,j in jobs.items() if pending(j)]
            if scenario=='gpu-queue' and '0' in running and '1' in waits:witnesses.append(('1',['0']))
            if scenario=='cpu-queue' and len(running)==2 and len(waits)==1:witnesses.append((waits[0],running))
        require(witnesses,'no compute-resource pending witness')
        records={r['slot']:r for r in children};proof=None
        for wait,occupants in witnesses:
            waiter=records[wait]
            if waiter['container_started']<min(records[x]['container_finished'] for x in occupants)-.25:continue
            relevant=[e for e in events if str(e.get('involvedObject',{}).get('name','')).startswith(waiter['name'])]
            messages=[str(e.get('message','')).lower() for e in relevant]
            tokens=('hcu',) if scenario=='gpu-queue' else ('cpu','queue')
            if not any(any(k in message for k in tokens) and any(k in message for k in ['insuff','not enough','resource','capabil','exceed']) for message in messages):continue
            proof={'waiter':wait,'occupants':occupants,'resource_event_observed':True};break
        require(proof is not None,'missing resource-event/backfill proof')
        result.update(proof,backfill_verified=True,pending_observed=True)
    return result

def cleanup_all(records,run_id,runner,delete=None):
    if delete is None:delete=base.cleanup
    errors=[]
    for r in records:
        try:base.validate_record(r);delete(r,run_id,runner)
        except Exception as e:errors.append({'name':r.get('name'),'error':type(e).__name__+': '+str(e)[:1000]})
    return errors

def epoch(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def inspect_child(r,out,run_id,runner):
    job=base.get('get',base.RESOURCE,r['name']);meta=job['metadata']
    require(meta['uid']==r['uid'] and meta['labels'].get(base.LABEL)==r['owner'] and meta['labels'].get(base.RUN)==run_id and meta.get('annotations',{}).get('ci.hygon.cn/dispatch-runner')==runner,'job identity changed')
    pods=base.get('get','pods','-l',base.LABEL+'='+r['owner'])['items'];require(len(pods)<=1,'unexpected child Pod count')
    phase=job.get('status',{}).get('state',{}).get('phase');view={'slot':r['slot'],'phase':phase,'pod_phase':None}
    if not pods:return view
    p=pods[0];require(any(x.get('uid')==r['uid'] for x in p['metadata'].get('ownerReferences',[])),'child Pod identity changed')
    fleet.verify_image(p,r['node']);out.mkdir(exist_ok=True)
    (out/'pod.json').write_text(json.dumps(p,indent=2));base.store_logs(out,p['metadata']['name'])
    view.update(pod_phase=p['status']['phase'],pod_uid=p['metadata']['uid'])
    term=next((c['state'].get('terminated') for c in p['status'].get('containerStatuses',[]) if c['name']=='compute'),None)
    if term and phase in ('Completed','Terminated','Failed','Aborted'):
        require(term['exitCode']==0 and phase=='Completed','child failed '+r['case']+' '+str(term.get('reason'))+' exit'+str(term['exitCode']))
        fleet.verify_image(p,r['node'],True)
        report=json.loads((out/'report.json').read_text())
        require(report.get('passed') is True and report.get('case')==r['case'] and (out/'junit.xml').exists() and (out/'libaxpy.so').exists(),'missing or failed child build/reports')
        r.update(report=report,done=True,pod_uid=p['metadata']['uid'],container_started=epoch(term['startedAt']),container_finished=epoch(term['finishedAt']),image_id=fleet.IMAGE_IDS[r['node']],image_id_verified=True)
        (out/'result.json').write_text(json.dumps(r,indent=2))
    return view

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in SCENARIOS+('cleanup-only',):raise ValueError('unapproved request')
    scenario=sys.argv[1];run_id=os.environ['GITHUB_RUN_ID'];runner=os.environ['RUNNER_NAME']
    if not run_id.isdigit() or not runner:raise ValueError('invalid run/runner')
    base.NS=fleet.NS;base.QUEUE=fleet.QUEUE
    out=Path(os.environ['RUNNER_TEMP'])/'arc-hcu-combinations';out.mkdir(exist_ok=True);own=out/'ownership.json'
    if scenario=='cleanup-only':
        errors=cleanup_all(json.loads(own.read_text()) if own.exists() else [],run_id,runner)
        (out/'post-cleanup.json').write_text(json.dumps({'verified':not errors,'errors':errors}))
        if errors:raise RuntimeError('independent child cleanup failed')
        print('ALL_CHILDREN_INDEPENDENTLY_CLEANED');return
    ensure_window()
    specs=plan(scenario,os.environ['CI_NODE'])
    require(not own.exists(),'refusing to overwrite existing ownership ledger')
    records=[];timeline=[];events_by_uid={};summary={'scenario':scenario,'run_id':run_id,'runner':runner,'passed':False,'cleanup_verified':False}
    def interrupt(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    try:
        require(not base.get('get',base.RESOURCE)['items'] and not base.get('get','pods')['items'],'fleet namespace not empty; refusing collision')
        for verb,res,want in [('create',base.RESOURCE,'yes'),('get','secrets','no'),('create','pods','no'),('create','rolebindings','no')]:
            require(base.kube('auth','can-i',verb,res,check=False).stdout.strip()==want,'unexpected combination RBAC')
        root=Path(__file__).resolve().parents[1];payload,hashes=base.bundle(root)
        (out/'source.json').write_text(json.dumps({'checkout_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'files':hashes},indent=2))
        until=time.monotonic()+230
        for spec in specs:
            ensure_window()
            r=dict(spec,owner=uuid.uuid4().hex,uid=None);r['name']='arc-e2e-'+r['owner'][:16]
            records.append(r);save_ownership(own,records)
            created=json.loads(base.kube('create','-f','-','-o','json',data=fleet.build_manifest(r['name'],r['owner'],r['case'],run_id,runner,payload,r['node'])).stdout)
            r['uid']=created['metadata']['uid'];save_ownership(own,records)
            print('CHILD_CREATED '+json.dumps(r),flush=True)
            if scenario=='gpu-queue' and r['slot']=='0':
                ready_until=min(until,time.monotonic()+60)
                while time.monotonic()<ready_until:
                    view=inspect_child(r,out/r['slot'],run_id,runner)
                    if view.get('pod_phase')=='Running':break
                    time.sleep(2)
                else:raise RuntimeError('primary GPU occupant did not run in bound')
        while time.monotonic()<until:
            views=[]
            for r in records:
                if r.get('done'):view={'slot':r['slot'],'phase':'Completed','pod_phase':'Succeeded'}
                else:view=inspect_child(r,out/r['slot'],run_id,runner)
                views.append(view)
            timeline.append({'time':time.time(),'jobs':views})
            names=[r['name'] for r in records]
            for e in base.get('get','events')['items']:
                if any(str(e.get('involvedObject',{}).get('name','')).startswith(name) for name in names):events_by_uid[e['metadata']['uid']]=e
            (out/'timeline.json').write_text(json.dumps(timeline,indent=2))
            (out/'events.json').write_text(json.dumps(list(events_by_uid.values()),indent=2))
            print('COMBINATION_STATE '+json.dumps(views),flush=True)
            if all(r.get('done') for r in records):
                summary['evidence']=validate_evidence(scenario,records,timeline,list(events_by_uid.values()))
                summary.update(passed=True,children=records);print('COMBINATION_PROOF '+json.dumps(summary['evidence']),flush=True);return
            time.sleep(2)
        raise RuntimeError('bounded combination wait exceeded')
    except BaseException as e:
        summary['error']=type(e).__name__+': '+str(e);raise
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
        cleanup_errors=cleanup_all(records,run_id,runner);summary.update(cleanup_verified=not cleanup_errors,cleanup_errors=cleanup_errors,children=records)
        (out/'summary.json').write_text(json.dumps(summary,indent=2));print('COMBINATION_SUMMARY '+json.dumps({'scenario':scenario,'passed':summary['passed'],'cleanup_verified':summary['cleanup_verified'],'error':summary.get('error')}),flush=True)
        if cleanup_errors:raise RuntimeError('one or more owned children could not be cleaned')

if __name__=='__main__':main()
