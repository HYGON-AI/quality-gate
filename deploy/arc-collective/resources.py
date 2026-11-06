"""Dedicated two-rank HCU collective scope; no changes to CPU-pair boundaries."""
import importlib.util,json
def resources(root):
 s=importlib.util.spec_from_file_location('collective_pair_resources',root/'deploy/arc-pair/resources.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 objs=json.loads(json.dumps(m.resources(root)).replace('arc-pair','arc-collective').replace('ci.hygon.cn/pair','ci.hygon.cn/collective'))
 for x in objs:
  if x['kind']=='ResourceQuota':x['spec']['hard'].update({'requests.hygon.com/hcu':'2','requests.memory':'64Gi','limits.memory':'64Gi'})
  if x['kind']=='Queue':x['spec']['capability'].update({'hygon.com/hcu':'2','memory':'64Gi'})
  if x['kind']=='Service':x['spec']['ports'] += [{'name':'rccl','port':29501,'targetPort':29501,'protocol':'TCP'}]
  if x['kind']=='NetworkPolicy' and x['metadata']['name']=='arc-collective-tcp':
   x['spec']['ingress'][0]['ports']=[{'protocol':'TCP'}];x['spec']['egress'][0]['ports']=[{'protocol':'TCP'}]
  if x['kind']=='ValidatingAdmissionPolicy':
   rules=x['spec']['validations'];rules[6]['expression']=rules[6]['expression'].replace('42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d','quality-gate-hcu-test:nonroot-20261106-v1')
   rules[7]['expression']="object.spec.tasks.all(t, t.template.spec.containers.all(c, c.resources.requests == c.resources.limits && size(c.resources.limits) == 4 && c.resources.limits.all(k, k in ['cpu','memory','ephemeral-storage','hygon.com/hcu']) && c.resources.limits['cpu'] == '2' && c.resources.limits['memory'] == '16Gi' && c.resources.limits['ephemeral-storage'] == '2Gi' && c.resources.limits['hygon.com/hcu'] == '1'))"
   rules[7]['message']='Collective fixed per-rank budget: 1 HCU / 2 CPU / 16Gi / 2Gi storage'
 return objs
