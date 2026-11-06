"""Dedicated test image boundary: old CPU/e2e policies remain unmodified."""
import yaml

BASE='42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d'
IMAGE='quality-gate-hcu-test:nonroot-20261106-v1'

def resources(root):
    text=(root/'deploy/arc-e2e/resources.yaml').read_text(encoding='utf-8')
    return list(yaml.safe_load_all(text.replace('arc-e2e','arc-account').replace(BASE,IMAGE)))
