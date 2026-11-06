#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Fixed CPU-only ARC/Volcano probe. No caller-provided code or manifests."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

NS = "github-ci-arc-pilot"
QUEUE = "arc-cpu-pilot"
RESOURCE = "jobs.batch.volcano.sh"
IMAGE = "ghcr.io/actions/actions-runner@sha256:e275409999c37162649aa050ca573f03eab2eabcb3a1e7fcc47548de6b4f9690"
LABEL = "ci.hygon.cn/pilot-owner"


def kube(*args, data=None, check=True):
    env = os.environ.copy()
    env.pop("KUBECONFIG", None)
    p = subprocess.run(
        ["kubectl", "--kubeconfig=/opt/hygon/kube-incluster.yaml", "--request-timeout=15s", "-n", NS] + list(args),
        input=None if data is None else json.dumps(data),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=25, env=env,
    )
    if check and p.returncode:
        raise RuntimeError("kubectl failed: " + p.stderr[:1500])
    return p


def manifest(name, owner, exit_code):
    if exit_code not in (0, 17):
        raise ValueError("Only fixed success/failure probes are permitted")
    code = (
        "import hashlib,pathlib,sys; "
        "p=pathlib.Path('/tmp/pilot'); p.mkdir(); "
        "b=b'arc-volcano-cpu-probe'*4096; (p/'data').write_bytes(b); "
        "assert (p/'data').read_bytes()==b; "
        "print('CPU_RW_SHA256='+hashlib.sha256(b).hexdigest(),flush=True); "
        "print('PILOT_EXIT=%d',flush=True); sys.exit(%d)" % (exit_code, exit_code)
    )
    return {
        "apiVersion": "batch.volcano.sh/v1alpha1", "kind": "Job",
        "metadata": {"name": name, "namespace": NS, "labels": {LABEL: owner}},
        "spec": {
            "queue": QUEUE, "schedulerName": "volcano", "minAvailable": 1,
            "maxRetry": 0, "ttlSecondsAfterFinished": 600,
            "policies": [
                {"event": "TaskCompleted", "action": "CompleteJob"},
                {"event": "PodFailed", "action": "TerminateJob"},
            ],
            "tasks": [{"name": "main", "replicas": 1, "template": {
                "metadata": {"labels": {LABEL: owner}},
                "spec": {
                    "restartPolicy": "Never", "activeDeadlineSeconds": 120,
                    "serviceAccountName": "arc-pilot-compute",
                    "automountServiceAccountToken": False,
                    "nodeSelector": {"kubernetes.io/hostname": "github-nmz3"},
                    "securityContext": {"runAsNonRoot": True, "runAsUser": 1001,
                                        "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{
                        "name": "probe", "image": IMAGE, "imagePullPolicy": "IfNotPresent",
                        "command": ["python3", "-c", code],
                        "resources": {"requests": {"cpu": "100m", "memory": "64Mi"},
                                      "limits": {"cpu": "1", "memory": "128Mi"}},
                        "securityContext": {"allowPrivilegeEscalation": False,
                                            "capabilities": {"drop": ["ALL"]}},
                    }],
                },
            }}],
        },
    }


def is_owned(obj, name, owner, uid=None):
    m = obj.get("metadata", {})
    return (m.get("name") == name and m.get("namespace") == NS
            and m.get("labels", {}).get(LABEL) == owner
            and (uid is None or m.get("uid") == uid))


def cleanup(name, owner, uid):
    raw = kube("get", RESOURCE, name, "--ignore-not-found", "-o", "json").stdout
    if not raw.strip():
        return
    obj = json.loads(raw)
    if not is_owned(obj, name, owner, uid):
        raise RuntimeError("Cleanup refused: owner or UID mismatch")
    kube("delete", "--raw", "/apis/batch.volcano.sh/v1alpha1/namespaces/" + NS + "/jobs/" + name,
         "-f", "-", data={"apiVersion": "v1", "kind": "DeleteOptions",
                          "preconditions": {"uid": obj["metadata"]["uid"]},
                          "propagationPolicy": "Foreground"})
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        pods = json.loads(kube("get", "pods", "-l", LABEL + "=" + owner, "-o", "json").stdout)
        job = kube("get", RESOURCE, name, "--ignore-not-found", "-o", "name").stdout
        if not pods["items"] and not job.strip():
            return
        time.sleep(2)
    raise RuntimeError("Cleanup incomplete; inspect owned job " + name)


def probe(expected, output):
    owner = uuid.uuid4().hex
    name = "arc-cpu-" + owner[:16]
    uid = None
    result = {"job": name, "expected_exit": expected, "namespace": NS}
    try:
        # An ambiguous create response is still cleaned by name + unguessable owner.
        obj = json.loads(kube("create", "-f", "-", "-o", "json",
                              data=manifest(name, owner, expected)).stdout)
        uid = obj["metadata"]["uid"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            job = json.loads(kube("get", RESOURCE, name, "-o", "json").stdout)
            pods = json.loads(kube("get", "pods", "-l", LABEL + "=" + owner, "-o", "json").stdout)["items"]
            if len(pods) > 1:
                raise RuntimeError("Unexpected retries or duplicate pods")
            if pods:
                pod = pods[0]
                if not any(x.get("uid") == uid for x in pod["metadata"].get("ownerReferences", [])):
                    raise RuntimeError("Pod owner UID mismatch")
                statuses = pod.get("status", {}).get("containerStatuses", [])
                term = next((s.get("state", {}).get("terminated") for s in statuses if s["name"] == "probe"), None)
                phase = job.get("status", {}).get("state", {}).get("phase")
                if term and phase in ("Completed", "Failed", "Terminated", "Aborted"):
                    logs = kube("logs", pod["metadata"]["name"], "-c", "probe").stdout
                    (output / (name + ".log")).write_text(logs, encoding="utf-8")
                    print(logs, flush=True)
                    result.update(actual_exit=term["exitCode"], phase=phase,
                                  node=pod["spec"].get("nodeName"), pod=pod["metadata"]["name"])
                    if term["exitCode"] != expected or "PILOT_EXIT=%d" % expected not in logs or "CPU_RW_SHA256=" not in logs:
                        raise RuntimeError("Exit code or compute evidence mismatch")
                    if expected == 0 and phase != "Completed":
                        raise RuntimeError("Successful pod did not yield Completed Job")
                    if expected != 0 and phase == "Completed":
                        raise RuntimeError("Failed pod incorrectly yielded Completed Job")
                    return result
            time.sleep(2)
        raise RuntimeError("Bounded probe timed out")
    finally:
        cleanup(name, owner, uid)
        result["cleanup"] = "verified"
        (output / (name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    output = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "arc-volcano-evidence"
    output.mkdir(parents=True, exist_ok=True)
    (output / "started.json").write_text(json.dumps({"namespace": NS, "mode": "fixed-cpu-pilot"}), encoding="utf-8")
    for verb, resource, namespace, expected in [
        ("create", RESOURCE, NS, True), ("get", "pods", NS, True),
        ("get", "secrets", NS, False), ("create", "pods", NS, False),
        ("create", "rolebindings", NS, False), ("create", RESOURCE, "github-ci", False),
        ("get", "secrets", "arc-runners", False),
    ]:
        p = kube("auth", "can-i", verb, resource, "--namespace=" + namespace, check=False)
        if p.stdout.strip() != ("yes" if expected else "no"):
            (output / "client-error.txt").write_text(p.stderr[:2000], encoding="utf-8")
            raise RuntimeError("Unexpected RBAC: " + verb + " " + resource + " " + namespace)
    results = [probe(0, output), probe(17, output)]
    (output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("ARC_VOLCANO_CPU_SUCCESS_FAILURE_AND_CLEANUP_PASS", flush=True)


if __name__ == "__main__":
    main()
