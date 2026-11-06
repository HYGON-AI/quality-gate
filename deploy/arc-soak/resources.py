"""Create a separate bounded three-node test boundary; do not mutate e2e/CPU pilot."""
import json
import yaml

def resources(root):
 text=(root/'deploy/arc-e2e/resources.yaml').read_text(encoding='utf-8').replace('arc-e2e','arc-soak')
 objs=list(yaml.safe_load_all(text))
 for x in objs:
  if x['kind']=='ResourceQuota':
   x['spec']['hard'].update({'requests.cpu':'128','limits.cpu':'128','requests.memory':'128Gi','limits.memory':'128Gi',
    'requests.ephemeral-storage':'32Gi','limits.ephemeral-storage':'32Gi','requests.hygon.com/hcu':'24','pods':'16','count/jobs.batch.volcano.sh':'16'})
  if x['kind']=='Queue':x['spec']['capability']={'cpu':'64','memory':'128Gi','hygon.com/hcu':'24'}
  if x['kind']=='ValidatingAdmissionPolicy':
   for rule in x['spec']['validations']:
    rule['expression']=rule['expression'].replace("== 'github-nmz3'","in ['github-nmz3','github-nmz4','github-nmz6']")
    rule['expression']=rule['expression'].replace("c.resources.limits['cpu'] == '2'","c.resources.limits['cpu'] in ['2','32']")
    rule['expression']=rule['expression'].replace("c.resources.limits['memory'] == '8Gi'","c.resources.limits['memory'] in ['8Gi','16Gi']")
    rule['expression']=rule['expression'].replace("in ['1','2']","in ['1','2','4','8']")
    rule['message']=rule['message'].replace('pinned to nmz3','restricted to nmz3/4/6').replace('at most 2 HCU','at most 8 HCU')
 return objs
