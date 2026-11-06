"""Real build and correctness fixture; no network, credentials or host mounts."""
import base64,ctypes,glob,hashlib,json,os,subprocess,sys,time,traceback,unittest,concurrent.futures
from pathlib import Path
from xml.etree import ElementTree as ET

case=sys.argv[1];cards={'cpu':0,'cpu-build':0,'hcu1':1,'hcu2':2,'hcu4':4,'hcu8':8,'failure':1,'cancel':1,'timeout':0,
    'cpu-failure':0,'cpu-cancel':0,'cpu-timeout':0,'cpu-orphan':0}[case]
out=Path('out');out.mkdir(exist_ok=True)
report={'case':case,'cards':cards,'started_at':time.time(),'passed':False}
suite=ET.Element('testsuite',name='arc-e2e-'+case);errors=[];checks=0
def check(name,fn):
    global checks
    checks+=1;t=ET.SubElement(suite,'testcase',name=name);start=time.monotonic()
    try:fn()
    except Exception as e:
        errors.append(name+': '+str(e));ET.SubElement(t,'failure',message=str(e)).text=traceback.format_exc()
        print('CHECK_FAILED',name,traceback.format_exc(),flush=True)
    finally:t.set('time',str(time.monotonic()-start))
def require(value,message):
    if not value:raise AssertionError(message)
def compile_cpp():
    p=subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC','tests/fixtures/arc_e2e/axpy.cpp','-o',str(out/'libaxpy.so')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    (out/'build.txt').write_text(p.stdout);require(p.returncode==0,p.stdout)
def cpu_correctness():
    lib=ctypes.CDLL(str((out/'libaxpy.so').resolve()));lib.axpy.argtypes=[ctypes.c_size_t,ctypes.c_double]+[ctypes.POINTER(ctypes.c_double)]*3
    lib.axpy.restype=None
    n=4096;arr=ctypes.c_double*n;x=arr(*[i/16 for i in range(n)]);y=arr(*[-i/32 for i in range(n)]);z=arr()
    for alpha in [0.,-2.5,3.]:
        lib.axpy(n,alpha,x,y,z)
        require(all(abs(z[i]-(alpha*x[i]+y[i]))<1e-9 for i in range(n)),'compiled axpy mismatch')
def repo_tests():
    logs=[]
    for pattern in ['test_arc_volcano_pilot.py','test_arc_volcano_reliability.py','test_arc_nmz3_hcu_validation.py']:
        p=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=40)
        logs.append(p.stdout);print(p.stdout,flush=True)
        require(p.returncode==0,'repository unittest failed: '+pattern)
    (out/'repository-tests.txt').write_text('\n'.join(logs))
def device_compute():
    if not cards:
        require(not glob.glob('/dev/dri/*') and not Path('/dev/kfd').exists(),'CPU container sees HCU devices')
        report['visible_cards']=0;return
    import torch
    torch.set_num_threads(2)
    require(torch.cuda.device_count()==cards,'wrong visible card count')
    report.update(visible_cards=cards,torch=torch.__version__,devices=glob.glob('/dev/dri/*'))
    torch.manual_seed(123);x=torch.randn(4096);y=torch.randn(4096);reference=2.5*x+y
    for d in range(cards):
        result=(2.5*x.to('cuda:'+str(d))+y.to('cuda:'+str(d))).cpu()
        torch.testing.assert_close(result,reference)
        a=torch.randn(128,128);b=torch.randn(128,128)
        torch.testing.assert_close((a.to('cuda:'+str(d))@b.to('cuda:'+str(d))).cpu(),a@b,atol=.005,rtol=.005)
    start=time.monotonic();iterations=0
    tensors=[(torch.randn(1024,1024,device='cuda:'+str(d)),torch.randn(1024,1024,device='cuda:'+str(d))) for d in range(cards)]
    while time.monotonic()-start<35:
        for d,(a,b) in enumerate(tensors):
            z=a@b
            require(torch.isfinite(z).all().item(),'non-finite HCU result')
        iterations+=1
    report.update(compute_seconds=time.monotonic()-start,iterations=iterations)
    print('HCU_COMPUTE_READY '+json.dumps({'cards':cards,'time':time.time()}),flush=True)

def compile_load():
    source=out/'load.cpp'
    source.write_text('#include <cmath>\n'+'\n'.join('double f%d(double x){for(int i=0;i<128;i++)x=sin(x*1.0001+i)+cos(x);return x;}'%i for i in range(256)))
    start=time.monotonic();deadline=start+35
    def worker(i):
        n=0
        while time.monotonic()<deadline:
            p=subprocess.run(['g++','-O2','-c',str(source),'-o',str(out/('load-%d.o'%i))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
            require(p.returncode==0,p.stdout);n+=1
        return n
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:counts=list(pool.map(worker,range(32)))
    report.update(compile_workers=32,objects=sum(counts),compile_seconds=time.monotonic()-start)
    for p in out.glob('load*'):p.unlink()
print('CI_FIXTURE_STARTED '+json.dumps({'case':case,'time':time.time()}),flush=True)
check('no_service_account_token',lambda:require(not Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists(),'credential present'))
check('cpp_build',compile_cpp);check('compiled_cpu_correctness',cpu_correctness)
check('repository_unit_tests',repo_tests);check('device_allocation_and_compute',device_compute)
if case=='cpu-build':check('bounded_parallel_compilation',compile_load)
if case in ['timeout','cpu-timeout']:
    print('TIMEOUT_WINDOW_READY',flush=True);time.sleep(240)
if case in ['failure','cpu-failure']:check('intentional_failure',lambda:require(False,'intentional e2e assertion failure'))
if case in ['cancel','cpu-cancel','cpu-orphan'] and not errors:
    print('CANCEL_WINDOW_READY',flush=True);time.sleep(100)
report.update(passed=not errors,errors=errors,finished_at=time.time(),checks=checks)
suite.set('tests',str(checks));suite.set('failures',str(len(errors)))
ET.ElementTree(suite).write(out/'junit.xml',encoding='utf-8',xml_declaration=True)
(out/'report.json').write_text(json.dumps(report,indent=2))
for p in sorted(out.iterdir()):
    b=p.read_bytes();require(len(b)<200000,'artifact too large')
    print('ARC_ARTIFACT '+json.dumps({'name':p.name,'sha256':hashlib.sha256(b).hexdigest(),'base64':base64.b64encode(b).decode()}),flush=True)
print('CI_FIXTURE_RESULT '+json.dumps(report),flush=True)
sys.exit(1 if errors else 0)
