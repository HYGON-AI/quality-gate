"""Separate bounded image/profile boundary; preserve all older CPU policies."""
import importlib.util,json
BASE='42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d'
IMAGE='quality-gate-hcu-test:nonroot-20261106-v1'
def resources(root):
    s=importlib.util.spec_from_file_location('prior_soak_resources',root/'deploy/arc-soak/resources.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    objs=json.loads(json.dumps(m.resources(root)).replace('arc-soak','arc-hcu-soak').replace(BASE,IMAGE))
    for x in objs:
        if x['kind']=='ValidatingAdmissionPolicy':
            for v in x['spec']['validations']:
                v['expression']=v['expression'].replace("in ['8Gi','16Gi']","in ['8Gi','16Gi','32Gi']")
            x['spec']['validations'].append({'expression':"object.spec.tasks.all(t, t.template.spec.containers.all(c, !('hygon.com/hcu' in c.resources.limits) || (c.resources.limits['hygon.com/hcu'] != '4' || c.resources.limits['memory'] == '16Gi') && (c.resources.limits['hygon.com/hcu'] != '8' || c.resources.limits['memory'] == '32Gi')))", 'message':'Four/eight-card tests require fixed 16/32Gi host-memory profiles'})
    return objs
