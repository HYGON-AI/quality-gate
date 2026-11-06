"""Real local build/tests then two-rank Gloo and RCCL collectives over sockets."""
import base64,datetime,hashlib,json,os,socket,subprocess,sys,time,traceback
from pathlib import Path
from xml.etree import ElementTree as ET
rank=int(os.environ['RANK']);assert rank in [0,1]
p=subprocess.run([sys.executable,'-u','tests/fixtures/arc_e2e/run_ci.py','hcu1'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
print(p.stdout,flush=True);assert p.returncode==0,'local build/unit baseline failed'
out=Path('out');report=json.loads((out/'report.json').read_text());suite=ET.parse(out/'junit.xml')
report.update(passed=False,rank=rank,world_size=2,node=os.environ['NODE_NAME'],backends={},transport='socket',ib_disabled=os.environ['NCCL_IB_DISABLE']=='1')
try:
 import torch
 import torch.distributed as dist
 assert os.getuid()==1001 and torch.version.hip and torch.cuda.device_count()==1
 report['visible_cards']=torch.cuda.device_count();torch.cuda.set_device(0)
 identity={'rank':rank,'node':os.environ['NODE_NAME'],'ip':socket.gethostbyname(socket.gethostname())}
 print('COLLECTIVE_READY '+json.dumps(identity),flush=True)
 for backend,port,device in [('gloo',29500,'cpu'),('nccl',29501,'cuda:0')]:
  case=ET.SubElement(suite.getroot(),'testcase',name='two_rank_'+backend)
  started=time.time();print('COLLECTIVE_BACKEND_START '+backend,flush=True)
  dist.init_process_group(backend=backend,init_method='tcp://%s:%d'%(os.environ['MASTER_ADDR'],port),rank=rank,world_size=2,timeout=datetime.timedelta(seconds=60))
  # Rank/node/IP are transported as actual tensors, not local assertions.
  raw=json.dumps(identity,sort_keys=True).encode();assert len(raw)<512
  ident=torch.zeros(512,dtype=torch.uint8,device=device);ident[:len(raw)]=torch.tensor(list(raw),dtype=torch.uint8,device=device)
  got=[torch.empty_like(ident) for _ in range(2)];dist.all_gather(got,ident)
  identities=[json.loads(bytes(x.cpu().tolist()).rstrip(b'\0')) for x in got]
  assert [x['rank'] for x in identities]==[0,1] and len({x['node'] for x in identities})==2 and len({x['ip'] for x in identities})==2
  for n in range(20):
   x=torch.full((16384,),float(rank+n+1),device=device);dist.all_reduce(x);assert torch.equal(x,torch.full_like(x,float(2*n+3)))
   v=torch.tensor([rank,n],device=device);g=[torch.empty_like(v) for _ in range(2)];dist.all_gather(g,v)
   assert [z.cpu().tolist() for z in g]==[[0,n],[1,n]]
  dist.barrier();dist.destroy_process_group()
  report['backends'][backend]={'passed':True,'rounds':20,'all_reduce':True,'all_gather':True,'identities':identities,'started_at':started,'finished_at':time.time()}
  print('COLLECTIVE_BACKEND_PASS '+backend,flush=True)
 report['passed']=True
except BaseException as e:
 report['error']=type(e).__name__+': '+str(e);ET.SubElement(case if 'case' in locals() else suite.getroot(),'failure',message=str(e)).text=traceback.format_exc()
 print('COLLECTIVE_ERROR '+traceback.format_exc(),flush=True)
suite.getroot().set('tests',str(int(suite.getroot().get('tests','0'))+2));suite.getroot().set('failures','0' if report['passed'] else '1')
suite.write(out/'junit.xml',encoding='utf-8',xml_declaration=True);(out/'report.json').write_text(json.dumps(report,indent=2))
for name in ['junit.xml','report.json']:
 b=(out/name).read_bytes();print('ARC_ARTIFACT '+json.dumps({'name':name,'sha256':hashlib.sha256(b).hexdigest(),'base64':base64.b64encode(b).decode()}),flush=True)
print('COLLECTIVE_RESULT '+json.dumps(report),flush=True);sys.exit(0 if report['passed'] else 1)
