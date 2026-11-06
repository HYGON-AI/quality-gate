"""Isolated two-replica CPU test permissions and narrowly selected communication."""
import yaml

def resources(root):
 objs=list(yaml.safe_load_all((root/'deploy/arc-e2e/resources.yaml').read_text().replace('arc-e2e','arc-pair')))
 for x in objs:
  if x['kind']=='ResourceQuota':
   x['spec']['hard'].update({'requests.cpu':'8','limits.cpu':'8','requests.memory':'32Gi','limits.memory':'32Gi','requests.ephemeral-storage':'4Gi','limits.ephemeral-storage':'4Gi','requests.hygon.com/hcu':'0','pods':'2','count/jobs.batch.volcano.sh':'1'})
  if x['kind']=='Queue':x['spec']['capability']={'cpu':'8','memory':'32Gi','hygon.com/hcu':'0'}
  if x['kind']=='ValidatingAdmissionPolicy':
   rules=x['spec']['validations']
   rules[0]['expression']=rules[0]['expression'].replace('minAvailable == 1','minAvailable == 2')
   rules[1]['expression']=rules[1]['expression'].replace('replicas == 1','replicas == 2')
   p='t.template.spec';a=p+'.affinity';expr=a+'.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0]';anti=a+'.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0]'
   rules[3]['expression']="object.spec.tasks.all(t, !has("+p+".nodeSelector) && !has("+p+".nodeName) && "+p+".activeDeadlineSeconds > 0 && "+p+".activeDeadlineSeconds <= 180 && "+p+".terminationGracePeriodSeconds <= 10 && "+p+".restartPolicy == 'Never' && size("+a+".nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms) == 1 && size("+a+".nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions) == 1 && "+expr+".key == 'kubernetes.io/hostname' && "+expr+".operator == 'In' && size("+expr+".values) == 2 && "+expr+".values[0] != "+expr+".values[1] && "+expr+".values.all(n, n in ['github-nmz3','github-nmz4','github-nmz6']) && size("+a+".podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution) == 1 && "+anti+".topologyKey == 'kubernetes.io/hostname' && "+anti+".labelSelector.matchLabels['ci.hygon.cn/e2e-owner'] == object.metadata.labels['ci.hygon.cn/e2e-owner'] && t.template.metadata.labels['ci.hygon.cn/e2e-owner'] == object.metadata.labels['ci.hygon.cn/e2e-owner'] && t.template.metadata.labels['ci.hygon.cn/pair'] == 'true')"
   rules[3]['message']='Two CPU replicas require two approved distinct nodes and required owner-correlated pod anti-affinity'
   rules[7]['expression']="object.spec.tasks.all(t, t.template.spec.containers.all(c, c.resources.requests == c.resources.limits && size(c.resources.limits) == 3 && c.resources.limits.all(k, k in ['cpu','memory','ephemeral-storage']) && c.resources.limits['cpu'] == '2' && c.resources.limits['memory'] == '8Gi' && c.resources.limits['ephemeral-storage'] == '2Gi'))"
   rules[7]['message']='CPU pair cannot request HCU or unbounded resources'
 peer={'podSelector':{'matchLabels':{'ci.hygon.cn/pair':'true'}}}
 meta=lambda name:{'name':name,'namespace':'github-ci-arc-pair'}
 objs+= [
  {'apiVersion':'v1','kind':'Service','metadata':meta('arc-pair-master'),'spec':{'clusterIP':'None','publishNotReadyAddresses':True,'selector':{'ci.hygon.cn/pair':'true','volcano.sh/task-index':'0'},'ports':[{'name':'pair','port':29500,'targetPort':29500,'protocol':'TCP'}]}},
  {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('arc-pair-tcp'),'spec':{'podSelector':peer['podSelector'],'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer],'ports':[{'port':29500,'protocol':'TCP'}]}],'egress':[{'to':[peer],'ports':[{'port':29500,'protocol':'TCP'}]}]}},
  {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('arc-pair-dns'),'spec':{'podSelector':peer['podSelector'],'policyTypes':['Egress'],'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]}]}}
 ]
 return objs
