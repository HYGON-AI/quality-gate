"""Test-only native ARC profiles. Not a general production pool factory."""
import json,sys
IMAGE='quality-gate-arc-native-test:20261107-v1'
PROFILES={1:('12','24','96Gi','32Gi'),2:('24','48','192Gi','64Gi'),4:('40','80','384Gi','96Gi'),8:('80','160','768Gi','128Gi')}

def values(cards):
    if type(cards) is not int or cards not in PROFILES:raise ValueError('unsupported native acceptance card profile')
    req,limit,memory,shm=PROFILES[cards]
    return {
        'githubConfigUrl':'https://github.com/HYGON-AI',
        'githubConfigSecret':'github-arc-app','runnerGroup':'ci-k8s',
        'runnerScaleSetName':'hygon-native-accept-'+str(cards)+'card','minRunners':0,'maxRunners':1,
        'controllerServiceAccount':{'namespace':'arc-systems','name':'arc-gha-rs-controller'},
        'template':{'metadata':{'labels':{'ci.hygon.cn/native-accept':'20261107'},'annotations':{'scheduling.volcano.sh/queue-name':'ci-hcu'}},'spec':{
            'schedulerName':'volcano','automountServiceAccountToken':False,'activeDeadlineSeconds':600,
            'nodeSelector':{'kubernetes.io/hostname':'github-nmz4','ci.hygon.cn/hcu-model':'bw1100','ci.hygon.cn/hcu-health':'ok'},
            'securityContext':{'runAsNonRoot':True,'runAsUser':1001,'runAsGroup':1001,'fsGroup':1001,'supplementalGroups':[39,998],'seccompProfile':{'type':'RuntimeDefault'}},
            'volumes':[{'name':'shm','emptyDir':{'medium':'Memory','sizeLimit':shm}}],
            'containers':[{'name':'runner','image':IMAGE,'imagePullPolicy':'Never','command':['/home/runner/run.sh'],
                'resources':{'requests':{'cpu':req,'memory':memory,'hygon.com/hcu':cards,'ephemeral-storage':'2Gi'},'limits':{'cpu':limit,'memory':memory,'hygon.com/hcu':cards,'ephemeral-storage':'4Gi'}},
                'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
                'env':[{'name':'CPU_LIMIT','value':limit},{'name':'OMP_NUM_THREADS','value':limit},{'name':'MAX_JOBS','value':limit},{'name':'CMAKE_BUILD_PARALLEL_LEVEL','value':limit},
                       {'name':'NODE_NAME','valueFrom':{'fieldRef':{'fieldPath':'spec.nodeName'}}}],
                'volumeMounts':[{'name':'shm','mountPath':'/dev/shm'}]}]}}}

if __name__=='__main__':print(json.dumps(values(int(sys.argv[1])),indent=2))
