"""New test scope only: card profile admission, no expansion of old policies."""
import importlib.util,json

def resources(root):
    s=importlib.util.spec_from_file_location('profiles_old_collective',root/'deploy/arc-collective/resources.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    objs=json.loads(json.dumps(m.resources(root)).replace('arc-collective','arc-profiles').replace('ci.hygon.cn/collective','ci.hygon.cn/profiles'))
    for x in objs:
        if x['kind']=='ResourceQuota':
            x['spec']['hard'].update({'requests.cpu':'32','limits.cpu':'32','requests.memory':'128Gi','limits.memory':'128Gi','requests.hygon.com/hcu':'16'})
        if x['kind']=='Queue':x['spec']['capability'].update(cpu='32',memory='128Gi',**{'hygon.com/hcu':'16'})
        if x['kind']=='ValidatingAdmissionPolicy':
            rules=x['spec']['validations']
            rules[0]['expression']="object.spec.queue == 'arc-profiles' && object.spec.schedulerName == 'volcano' && (!has(object.spec.plugins) || size(object.spec.plugins) == 0) && object.spec.maxRetry == 1 && object.spec.minAvailable == object.spec.tasks[0].replicas && object.spec.ttlSecondsAfterFinished > 0 && object.spec.ttlSecondsAfterFinished <= 600 && size(object.spec.policies) == 1 && object.spec.policies[0].event == 'PodFailed' && object.spec.policies[0].action == 'TerminateJob'"
            rules[1]['expression']="size(object.spec.tasks) == 1 && object.spec.tasks.all(t, t.name == 'main' && t.replicas in [1,2] && (!has(t.policies) || size(t.policies) == 0))"
            rules[2]['expression']="object.spec.tasks.all(t, t.template.spec.serviceAccountName == 'arc-profiles-compute' && t.template.spec.automountServiceAccountToken == false && size(t.template.spec.volumes) == 1 && t.template.spec.volumes[0].name == 'shm' && has(t.template.spec.volumes[0].emptyDir) && t.template.spec.volumes[0].emptyDir.medium == 'Memory' && t.template.spec.volumes[0].emptyDir.sizeLimit == '1Gi' && !has(t.template.spec.volumes[0].hostPath) && !has(t.template.spec.volumes[0].secret) && !has(t.template.spec.volumes[0].projected) && !has(t.template.spec.volumes[0].persistentVolumeClaim))"
            p='t.template.spec';a=p+'.affinity';expr=a+'.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0]';anti=a+'.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0]'
            single="t.replicas == 1 && has("+p+".nodeSelector) && size("+p+".nodeSelector) == 1 && "+p+".nodeSelector['kubernetes.io/hostname'] == 'github-nmz3'"
            pair="t.replicas == 2 && !has("+p+".nodeSelector) && size("+a+".nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms) == 1 && size("+a+".nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions) == 1 && "+expr+".key == 'kubernetes.io/hostname' && "+expr+".operator == 'In' && "+expr+".values == ['github-nmz3','github-nmz4'] && size("+a+".podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution) == 1 && "+anti+".topologyKey == 'kubernetes.io/hostname' && "+anti+".labelSelector.matchLabels['ci.hygon.cn/e2e-owner'] == object.metadata.labels['ci.hygon.cn/e2e-owner']"
            rules[3]['expression']="object.spec.tasks.all(t, !has("+p+".nodeName) && "+p+".activeDeadlineSeconds in [120,300] && "+p+".terminationGracePeriodSeconds <= 10 && "+p+".restartPolicy == 'Never' && (("+single+") || ("+pair+")) && t.template.metadata.labels['ci.hygon.cn/e2e-owner'] == object.metadata.labels['ci.hygon.cn/e2e-owner'] && t.template.metadata.labels['ci.hygon.cn/e2e-run'] == object.metadata.labels['ci.hygon.cn/e2e-run'] && t.template.metadata.labels['ci.hygon.cn/profiles'] == 'true')"
            rules[6]['expression']=rules[6]['expression'].replace("(!has(c.volumeMounts) || size(c.volumeMounts) == 0)","(size(c.volumeMounts) == 1 && c.volumeMounts[0].name == 'shm' && c.volumeMounts[0].mountPath == '/dev/shm' && !has(c.volumeMounts[0].subPath) && !has(c.volumeMounts[0].subPathExpr))")
            profiles=[]
            for total,local,repl,cpu,mem in [('0','0',1,'16','16Gi'),('1','1',1,'8','16Gi'),('2','2',1,'8','16Gi'),('4','4',1,'8','32Gi'),('8','8',1,'16','64Gi'),('16','8',2,'16','64Gi')]:
                gpu="!('hygon.com/hcu' in c.resources.limits) && size(c.resources.limits) == 3" if local=='0' else "c.resources.limits['hygon.com/hcu'] == '"+local+"' && size(c.resources.limits) == 4"
                profiles.append("(object.metadata.labels['ci.hygon.cn/profile-cards'] == '"+total+"' && t.replicas == "+str(repl)+" && c.resources.limits['cpu'] == '"+cpu+"' && c.resources.limits['memory'] == '"+mem+"' && "+gpu+")")
            rules[7]['expression']="object.spec.tasks.all(t, t.template.spec.containers.all(c, c.resources.requests == c.resources.limits && c.resources.limits.all(k, k in ['cpu','memory','ephemeral-storage','hygon.com/hcu']) && c.resources.limits['ephemeral-storage'] == '2Gi' && ("+' || '.join(profiles)+")))"
            for i,r in enumerate(rules):r['message']='Card-profile boundary '+str(i)+': fixed budget, isolation and placement required'
    return objs
