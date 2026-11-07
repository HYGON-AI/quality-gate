"""Repository fixture: real C++ build, CPU tests, HCU compute, local/multi-node collectives."""
import base64,hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
from xml.etree import ElementTree as ET

cards=int(os.environ['CI_LOCAL_CARDS']);nodes=int(os.environ['CI_NNODES']);rank=int(os.environ['CI_NODE_RANK'])
mode=os.environ['CI_MODE'];out=Path('out');out.mkdir(exist_ok=True)
report={'passed':False,'node_rank':rank,'node':os.environ['NODE_NAME'],'visible_cards':cards,'build_passed':False}
suite=ET.Element('testsuite',name='card-profile');case=ET.SubElement(suite,'testcase',name='build-compute-and-collective')
try:
    assert not Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists()
    p=subprocess.run([sys.executable,'-u','tests/fixtures/arc_e2e/run_ci.py','hcu'+str(cards) if cards else 'cpu-build'],timeout=100)
    assert p.returncode==0,'baseline C++/unit/device CI failed'
    baseline=json.loads((out/'report.json').read_text());assert baseline['passed'];report['baseline']=baseline;report['build_passed']=True
    if cards:
        cmd=[sys.executable,'-m','torch.distributed.run','--nproc-per-node='+str(cards),'--nnodes='+str(nodes),'--node-rank='+str(rank)]
        if nodes==1:cmd+=['--standalone']
        else:cmd+=['--master-addr='+os.environ['MASTER_ADDR'],'--master-port=29500']
        cmd+=['tests/fixtures/arc_e2e/profile_worker.py']
        p=subprocess.run(cmd,timeout=150);assert p.returncode==0,'distributed fixture failed'
        reports=[json.loads((out/('worker-'+str(rank*cards+i)+'.json')).read_text()) for i in range(cards)]
        assert all(r['passed'] for r in reports)
        assert all(r['identities']==reports[0]['identities'] for r in reports)
        report.update(world_size=nodes*cards,rounds=10,all_reduce=True,all_gather=True,identities=reports[0]['identities'],transport='socket')
    if mode in ['timeout','cancel','orphan']:
        from profile_hold import run
        run(cards,rank)
    else:print('PROFILE_COMPUTE_READY '+json.dumps({'cards':cards,'node_rank':rank,'active_gpu_hold':False}),flush=True)
    assert mode!='failure','intentional card-profile assertion failure'
    report['passed']=True
except BaseException as e:
    report['error']=type(e).__name__+': '+str(e);ET.SubElement(case,'failure',message=str(e)).text=traceback.format_exc();print(traceback.format_exc(),flush=True)
suite.set('tests','1');suite.set('failures','0' if report['passed'] else '1')
ET.ElementTree(suite).write(out/'junit.xml',encoding='utf-8',xml_declaration=True)
(out/'report.json').write_text(json.dumps(report,indent=2))
for name in ['report.json','junit.xml']:
    b=(out/name).read_bytes();assert len(b)<200000
    print('ARC_ARTIFACT '+json.dumps({'name':name,'sha256':hashlib.sha256(b).hexdigest(),'base64':base64.b64encode(b).decode()}),flush=True)
print('PROFILE_RESULT '+json.dumps(report),flush=True);sys.exit(0 if report['passed'] else 1)
