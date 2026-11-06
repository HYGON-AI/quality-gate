"""Actual compile/tests plus bounded two-rank TCP correctness; no collective claims."""
import base64,hashlib,json,os,socket,subprocess,sys,time,traceback
from pathlib import Path
from xml.etree import ElementTree as ET
from pair_protocol import probe_denied_port

rank=int(os.environ['RANK']);assert rank in [0,1]
start=time.time();p=subprocess.run([sys.executable,'-u','tests/fixtures/arc_e2e/run_ci.py','cpu'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
print(p.stdout,flush=True);assert p.returncode==0,'local compile/CPU/unit tests failed'
out=Path('out');report=json.loads((out/'report.json').read_text());suite=ET.parse(out/'junit.xml');case=ET.SubElement(suite.getroot(),'testcase',name='two_node_tcp_correctness')
def send(f,x):f.write(json.dumps(x).encode()+b'\n');f.flush()
def receive(f):
 b=f.readline(1000001)
 assert b.endswith(b'\n') and len(b)<1000000,'invalid bounded message'
 return json.loads(b)
partial=sum(i*i for i in range(rank*10000,(rank+1)*10000));expected=sum(i*i for i in range(20000));checksum=None;blocked_listener=None
try:
 print('PAIR_READY '+json.dumps({'rank':rank,'node':os.environ['NODE_NAME'],'time':time.time()}),flush=True)
 if rank==0:
  blocked_listener=socket.socket();blocked_listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);blocked_listener.bind(('0.0.0.0',29501));blocked_listener.listen(4)
  with socket.create_connection(('127.0.0.1',29501),timeout=2):pass
  report['local_listening_control_passed']=True
  listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.settimeout(60);listener.bind(('0.0.0.0',29500));listener.listen(1)
  conn,_=listener.accept();listener.close()
 else:
  until=time.monotonic()+60
  while True:
   try:conn=socket.create_connection(('arc-pair-master.github-ci-arc-pair.svc.cluster.local',29500),timeout=3);break
   except OSError:
    if time.monotonic()>until:raise
    time.sleep(1)
 conn.settimeout(20)
 report.update(peer_address=conn.getpeername(),local_address=conn.getsockname(),transport='TCP')
 with conn,conn.makefile('rwb') as f:
  if rank==0:
   send(f,{'denial_probe_ready':True,'listening_control_passed':True})
   denied=receive(f);assert denied.get('denied_port_test',{}).get('denied')
   report['denied_port_test']=denied['denied_port_test']
  else:
   ready=receive(f);assert ready=={'denial_probe_ready':True,'listening_control_passed':True}
   denied=probe_denied_port(conn.getpeername()[0],29501)
   report['denied_port_test']=denied;send(f,{'denied_port_test':denied})
  for n in range(20):
   data=(('arc-pair-round-%d-'%n)*5000)[:65536];digest=hashlib.sha256(data.encode()).hexdigest()
   if rank==0:
    send(f,{'round':n,'payload':data,'digest':digest,'partial':partial})
    reply=receive(f);assert reply=={'round':n,'digest':digest,'sum':expected},reply
    send(f,{'round':n,'ack':True,'sum':expected})
   else:
    req=receive(f);assert req['round']==n and req['payload']==data and req['digest']==digest
    total=req['partial']+partial;assert total==expected
    send(f,{'round':n,'digest':digest,'sum':total});assert receive(f)=={'round':n,'ack':True,'sum':expected}
   checksum=digest;time.sleep(.25)
 report.update(passed=True,pair_passed=True,rank=rank,rounds=20,checksum=checksum,node=os.environ['NODE_NAME'],pair_started_at=start,pair_finished_at=time.time())
except Exception as e:
 report.update(passed=False,pair_passed=False,rank=rank,error=str(e));ET.SubElement(case,'failure',message=str(e)).text=traceback.format_exc()
 print('PAIR_ERROR '+traceback.format_exc(),flush=True)
finally:
 if blocked_listener is not None:blocked_listener.close()
suite.getroot().set('tests',str(int(suite.getroot().get('tests','0'))+1));suite.getroot().set('failures','0' if report['passed'] else '1')
suite.write(out/'junit.xml',encoding='utf-8',xml_declaration=True);(out/'report.json').write_text(json.dumps(report,indent=2))
for name in ['junit.xml','report.json']:
 b=(out/name).read_bytes();print('ARC_ARTIFACT '+json.dumps({'name':name,'sha256':hashlib.sha256(b).hexdigest(),'base64':base64.b64encode(b).decode()}),flush=True)
print('PAIR_RESULT '+json.dumps(report),flush=True);sys.exit(0 if report['passed'] else 1)
