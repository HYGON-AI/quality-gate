"""Native Runner executes real repository CI; never submits Kubernetes resources."""
import json,os,subprocess,sys
from pathlib import Path

cards=int(os.environ['CI_CARDS']);mode=os.environ.get('CI_MODE','success')
assert cards in [1,2,4,8] and mode in ['success','orphan']
assert os.getuid()==1001 and os.environ['NODE_NAME']=='github-nmz4'
for forbidden in ['/var/run/secrets/kubernetes.io/serviceaccount/token','/var/run/docker.sock','/home/github/.kube-ci/config']:
    assert not Path(forbidden).exists(),'unexpected privileged task access'
source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
os.environ.update(CI_LOCAL_CARDS=str(cards),CI_NNODES='1',CI_NODE_RANK='0',CI_MODE=mode,
                  GLOO_SOCKET_IFNAME='eth0',NCCL_SOCKET_IFNAME='eth0',NCCL_IB_DISABLE='1',
                  NCCL_DEBUG='INFO',NCCL_DEBUG_SUBSYS='INIT,NET,ENV')
print('NATIVE_ACCEPT_STARTED '+json.dumps({'source':source,'cards':cards,'mode':mode,'node':os.environ['NODE_NAME'],'runner':os.environ['RUNNER_NAME']}),flush=True)
p=subprocess.run([sys.executable,'-u','tests/fixtures/arc_e2e/run_profile.py'],timeout=480)
assert p.returncode==0,'native real CI fixture failed'
report=json.loads(Path('out/report.json').read_text());assert report['passed'] and report['visible_cards']==cards
report.update(native_runner=os.environ['RUNNER_NAME'],source=source,mode=mode)
Path('out/native-accept.json').write_text(json.dumps(report,indent=2))
print('NATIVE_ACCEPT_PASS '+json.dumps({'source':source,'cards':cards,'mode':mode,'node':os.environ['NODE_NAME'],'runner':os.environ['RUNNER_NAME']}),flush=True)
