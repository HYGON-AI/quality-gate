"""Separate bounded image/profile boundary; preserve all older CPU policies."""
import importlib.util,json
BASE='42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d'
IMAGE='quality-gate-hcu-test:nonroot-20261106-v1'
def resources(root):
    s=importlib.util.spec_from_file_location('prior_soak_resources',root/'deploy/arc-soak/resources.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return json.loads(json.dumps(m.resources(root)).replace('arc-soak','arc-hcu-soak').replace(BASE,IMAGE))
