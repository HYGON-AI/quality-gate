# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Bounded nmz3-only CI experiment. No production gate integration."""
import argparse
import datetime
import json
import os
import pathlib
import re
import signal
import subprocess
import time
import uuid

NS = "github-ci"
NODE = "github-nmz3"
RESOURCE = "jobs.batch.volcano.sh"
LABEL = "ci.hygon.com/validation"
IMAGE = "42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d"
MODES = ("success", "failure", "runtime-timeout", "cancel", "concurrent", "queue", "github-timeout")
TERMINAL = ("Completed", "Failed", "Aborted", "Terminated")


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sanitize(text):
    text = re.sub(r"(?i)(bearer\s+)[\w.=-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[REDACTED]", text)
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", text)


def kube(*args, data=None):
    result = subprocess.run(
        ["kubectl", "--request-timeout=8s", "-n", NS] + list(args),
        input=json.dumps(data) if data is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        timeout=12, start_new_session=(os.name != "nt"))
    if result.returncode:
        raise RuntimeError("kubectl failed: " + sanitize(result.stderr[:1500]))
    return result.stdout


def read(kind, name=None, selector=None):
    args = ["get", kind]
    if name:
        args += [name, "--ignore-not-found=true"]
    if selector:
        args += ["-l", selector]
    out = kube(*(args + ["-o", "json"]))
    return json.loads(out) if out.strip() else None


def owned(obj, record, token):
    m = obj.get("metadata", {})
    return (m.get("name") == record["name"] and m.get("namespace") == NS
            and m.get("labels", {}).get(LABEL) == token
            and (not record.get("uid") or m.get("uid") == record["uid"]))


def delete_owned(record, token):
    obj = read(RESOURCE, record["name"])
    if obj is None:
        return
    if not owned(obj, record, token):
        raise RuntimeError("Refusing deletion: ownership/UID mismatch")
    # A server-side UID precondition closes the GET/DELETE race.
    path = "/apis/batch.volcano.sh/v1alpha1/namespaces/{}/jobs/{}".format(NS, record["name"])
    kube("delete", "--raw", path, "-f", "-", data={
        "apiVersion": "v1", "kind": "DeleteOptions",
        "preconditions": {"uid": obj["metadata"]["uid"]},
        "propagationPolicy": "Foreground"})


def manifest(name, token, cards, mode, hold=0):
    if cards not in (1, 2, 8) or mode not in MODES or not 0 <= hold <= 180:
        raise ValueError("Invalid bounded test parameters")
    source = '''import json, time, sys, torch
count = torch.cuda.device_count()
assert count == CARDS, (count, CARDS)
devices = []
for i in range(count):
    props = torch.cuda.get_device_properties(i)
    value = torch.ones(1024, device="cuda:" + str(i))
    assert value.sum().item() == 1024
    torch.cuda.synchronize(i)
    ident = str(props.uuid)
    assert ident and ident != "None"
    devices.append({"index": i, "uuid": ident, "name": props.name})
assert len(set(d["uuid"] for d in devices)) == count
print("DEVICE_REPORT=" + json.dumps({"count": count, "devices": devices}), flush=True)
print("READY_FOR_CANCEL" if MODE == "cancel" else "COMPUTE_READY", flush=True)
time.sleep(HOLD)
if MODE == "failure":
    print("EXPECTED_EXIT_17", flush=True)
    sys.exit(17)
print("COMPUTE_PASSED", flush=True)
'''.replace("CARDS", str(cards)).replace("MODE", repr(mode)).replace("HOLD", str(hold))
    labels = {LABEL: token}
    return {
        "apiVersion": "batch.volcano.sh/v1alpha1", "kind": "Job",
        "metadata": {"name": name, "namespace": NS, "labels": labels},
        "spec": {"schedulerName": "volcano", "queue": "default", "minAvailable": 1,
                 "maxRetry": 0, "ttlSecondsAfterFinished": 600,
                 "policies": [{"event": "TaskCompleted", "action": "CompleteJob"},
                              {"event": "PodFailed", "action": "AbortJob"}],
                 "tasks": [{"name": "main", "replicas": 1, "template": {
                     "metadata": {"labels": labels}, "spec": {
                         "nodeSelector": {"kubernetes.io/hostname": NODE},
                         "automountServiceAccountToken": False, "restartPolicy": "Never",
                         "activeDeadlineSeconds": 45 if mode == "runtime-timeout" else 300,
                         "terminationGracePeriodSeconds": 5,
                         "containers": [{"name": "compute", "image": IMAGE,
                                         "imagePullPolicy": "IfNotPresent",
                                         "command": ["python", "-u", "-c", source],
                                         "resources": {"requests": {"cpu": "2", "memory": "16Gi", "hygon.com/hcu": cards},
                                                       "limits": {"cpu": "4", "memory": "16Gi", "hygon.com/hcu": cards}}}]}}}]}}


def verdict(phase, pods, logs):
    """Success needs terminal controller AND all required containers AND marker."""
    exits = [c.get("state", {}).get("terminated", {}).get("exitCode")
             for p in pods for c in p.get("status", {}).get("containerStatuses", [])]
    return (phase == "Completed" and len(pods) == 1 and len(exits) == 1
            and exits == [0] and "COMPUTE_PASSED" in logs)


def device_ids(logs, expected):
    lines = [line.split("=", 1)[1] for line in logs.splitlines() if line.startswith("DEVICE_REPORT=")]
    if len(lines) != 1:
        raise RuntimeError("Missing or ambiguous device report")
    report = json.loads(lines[0])
    ids = [device["uuid"] for device in report["devices"]]
    if report["count"] != expected or len(ids) != expected or len(set(ids)) != expected:
        raise RuntimeError("Device count/identity mismatch")
    return ids


def isolated_pair(results):
    if len(results) != 2 or any(phase != "Running" or len(pods) != 1
                                or pods[0].get("status", {}).get("phase") != "Running"
                                or "COMPUTE_READY" not in logs for phase, pods, logs in results):
        return False
    return device_ids(results[0][2], 1)[0] != device_ids(results[1][2], 1)[0]


def resource_wait_evidence(events):
    return any(e.get("reason", "") in ("FailedScheduling", "Unschedulable", "NotEnoughResources")
               and any(word in e.get("message", "").lower() for word in ("resource", "hcu", "insufficient", "unschedulable"))
               for e in events)


class Experiment:
    def __init__(self, directory, mode, resume=False):
        self.directory = pathlib.Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / "state.json"
        if resume:
            self.state = json.loads(self.file.read_text())
        else:
            run = os.environ.get("GITHUB_RUN_ID", "local")
            attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
            if not re.fullmatch(r"[0-9a-z]+", run) or not attempt.isdigit():
                raise ValueError("Invalid run identity")
            self.state = {"token": "qgv-{}-{}-{}".format(run, attempt, uuid.uuid4().hex[:8]),
                          "mode": mode, "created": stamp(), "records": [], "timeline": []}
            self.save()

    def save(self):
        temporary = self.file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2))
        temporary.replace(self.file)

    def event(self, message):
        self.state["timeline"].append({"time": stamp(), "message": message})
        self.save()
        print(stamp(), message, flush=True)

    def submit(self, case, cards, mode, hold=0, dry=False):
        name = self.state["token"] + "-" + case
        body = manifest(name, self.state["token"], cards, mode, hold)
        admitted = json.loads(kube("create", "--dry-run=server", "-f", "-", "-o", "json", data=body))
        spec = admitted["spec"]["tasks"][0]["template"]["spec"]
        if (spec["nodeSelector"] != body["spec"]["tasks"][0]["template"]["spec"]["nodeSelector"]
                or spec.get("automountServiceAccountToken") is not False
                or spec.get("hostNetwork") or spec.get("hostPID")
                or any(v.get("hostPath") for v in spec.get("volumes", []))):
            raise RuntimeError("Admission changed isolation contract")
        for container in spec["containers"]:
            if container.get("securityContext", {}).get("privileged"):
                raise RuntimeError("Unexpected privileged container")
        self.event("server dry-run passed: " + name)
        if dry:
            return
        # Persist intended unique name before submission, covering a lost create response.
        record = {"name": name, "uid": None, "cards": cards, "mode": mode}
        self.state["records"].append(record)
        self.save()
        obj = json.loads(kube("create", "-f", "-", "-o", "json", data=body))
        record["uid"] = obj["metadata"]["uid"]
        self.event("submitted: " + name + " uid=" + record["uid"])
        return record

    def snapshot(self, record):
        job = read(RESOURCE, record["name"])
        if not job or not owned(job, record, self.state["token"]):
            raise RuntimeError("Job missing or ownership changed")
        pods = read("pods", selector="volcano.sh/job-name=" + record["name"])["items"]
        if any(p.get("spec", {}).get("nodeName") not in (None, NODE) for p in pods):
            raise RuntimeError("Pod scheduled outside nmz3")
        logs = []
        for pod in pods:
            if pod.get("status", {}).get("containerStatuses"):
                status = pod["status"]["containerStatuses"][0].get("state", {})
                if "running" in status or "terminated" in status:
                    logs.append(kube("logs", pod["metadata"]["name"], "--tail=100"))
        phase = job.get("status", {}).get("state", {}).get("phase", "Pending")
        record.update(phase=phase, pods=[{"name": p["metadata"]["name"], "uid": p["metadata"]["uid"],
                                        "node": p.get("spec", {}).get("nodeName"), "status": p.get("status", {})} for p in pods],
                      logs=sanitize("\n".join(logs)))
        self.save()
        return phase, pods, record["logs"]

    def wait(self, records, timeout=360):
        deadline = time.monotonic() + timeout
        ready = set()
        while time.monotonic() < deadline:
            results = []
            for record in records:
                phase, pods, logs = self.snapshot(record)
                if record["name"] not in ready and ("COMPUTE_READY" in logs or "READY_FOR_CANCEL" in logs):
                    self.event("ready: " + record["name"] + "\n" + logs)
                    ready.add(record["name"])
                results.append((phase, pods, logs))
            if all(result[0] in TERMINAL for result in results):
                return results
            time.sleep(2)
        raise TimeoutError("Controller wait deadline exceeded")

    def wait_ready(self, record, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            phase, pods, logs = self.snapshot(record)
            if phase == "Running" and len(pods) == 1 and "COMPUTE_READY" in logs:
                self.event("ready: " + record["name"] + "\n" + logs)
                return
            if phase in TERMINAL:
                raise RuntimeError("Task ended before ready observation")
            time.sleep(2)
        raise TimeoutError("Ready deadline exceeded")

    def concurrent(self):
        records = [self.submit("parallel-" + str(i), 1, "concurrent", hold=45) for i in range(2)]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            results = [self.snapshot(record) for record in records]
            if isolated_pair(results):
                self.state["overlap"] = {"observed_at": stamp(),
                                         "device_ids": [device_ids(result[2], 1)[0] for result in results]}
                self.event("Concurrent Running observed on distinct single devices")
                break
            if any(result[0] in TERMINAL for result in results):
                raise RuntimeError("No verified concurrent isolation before task completion")
            time.sleep(2)
        else:
            raise TimeoutError("Concurrent observation timed out")
        results = self.wait(records)
        if not all(verdict(*result) for result in results):
            raise RuntimeError("One or more concurrent computations failed")
        # Compare container lifecycle timestamps from this one node only.
        intervals = [result[1][0]["status"]["containerStatuses"][0]["state"]["terminated"] for result in results]
        start = max(datetime.datetime.fromisoformat(t["startedAt"].replace("Z", "+00:00")) for t in intervals)
        end = min(datetime.datetime.fromisoformat(t["finishedAt"].replace("Z", "+00:00")) for t in intervals)
        seconds = (end - start).total_seconds()
        if seconds <= 0:
            raise RuntimeError("Container lifetimes did not overlap")
        self.state["overlap"]["seconds"] = seconds
        self.state["success"] = True
        self.event("Concurrent isolation passed; overlap seconds=" + str(seconds))

    def queue(self):
        first = self.submit("full-node", 8, "queue", hold=75)
        self.wait_ready(first)
        device_ids(first["logs"], 8)
        second = self.submit("waiting", 1, "queue")
        started = time.monotonic()
        evidence = []
        pending_observed = False
        deadline = started + 100
        while time.monotonic() < deadline:
            a = self.snapshot(first)
            b = self.snapshot(second)
            if a[0] != "Running" or "COMPUTE_READY" not in a[2]:
                break
            if b[0] == "Running" or "COMPUTE_READY" in b[2]:
                raise RuntimeError("Single-card job ran while full-node job still occupied 8 cards")
            events = read("events")["items"]
            evidence = [{"reason": e.get("reason"), "message": sanitize(e.get("message", "")),
                         "object": e.get("involvedObject", {}).get("name")}
                        for e in events if second["name"] in e.get("involvedObject", {}).get("name", "")]
            if time.monotonic() - started >= 5 and resource_wait_evidence(evidence):
                pending_observed = True
                self.state["queue_evidence"] = {"time": stamp(), "seconds": time.monotonic() - started,
                                                "waiting_phase": b[0], "events": evidence}
                self.event("Waiting job observed while 8-card task runs; scheduler evidence saved")
                break
            time.sleep(2)
        if not pending_observed:
            raise RuntimeError("No scheduler-backed pending observation")
        results = self.wait([first, second])
        if not all(verdict(*result) for result in results):
            raise RuntimeError("Queue computations did not both finish successfully")
        device_ids(results[1][2], 1)
        intervals = [result[1][0]["status"]["containerStatuses"][0]["state"]["terminated"] for result in results]
        first_end = datetime.datetime.fromisoformat(intervals[0]["finishedAt"].replace("Z", "+00:00"))
        next_start = datetime.datetime.fromisoformat(intervals[1]["startedAt"].replace("Z", "+00:00"))
        gap = (next_start - first_end).total_seconds()
        if gap < 0:
            raise RuntimeError("Queued container started before full-node container ended")
        self.state["queue_evidence"]["start_after_release_seconds"] = gap
        self.state["success"] = True
        self.event("Queue handover passed; second start after first finish seconds=" + str(gap))

    def cleanup(self):
        self.event("cleanup started")
        errors = []
        for record in self.state["records"]:
            try:
                delete_owned(record, self.state["token"])
            except Exception as exc:
                errors.append(sanitize(str(exc)))
        if errors:
            raise RuntimeError("; ".join(errors))
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            remaining = {kind: len(read(kind, selector=LABEL + "=" + self.state["token"])["items"])
                         for kind in (RESOURCE, "pods", "services")}
            if not any(remaining.values()):
                self.state["cleanup"] = {"time": stamp(), "remaining": remaining}
                self.event("cleanup verified: jobs=0 pods=0 services=0")
                return
            time.sleep(1)
        raise RuntimeError("Cleanup deadline exceeded: " + str(remaining))

    def execute(self):
        mode = self.state["mode"]
        if mode == "concurrent":
            return self.concurrent()
        if mode == "queue":
            return self.queue()
        hold = 180 if mode in ("cancel", "runtime-timeout", "github-timeout") else 0
        record = self.submit(mode, 2 if mode == "success" else 1, mode, hold)
        phase, pods, logs = self.wait([record])[0]
        self.event("terminal: " + phase + "\n" + logs)
        self.state["success"] = verdict(phase, pods, logs)
        self.save()
        if mode != "success" or not self.state["success"]:
            raise RuntimeError("Non-success test outcome; inspect phase, exits and markers in state.json")


def interrupted(signum, _frame):
    # Exit promptly; bounded always() cleanup step handles cancellation separately.
    raise KeyboardInterrupt("Runner signal " + str(signum))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "cleanup", "dry-run"))
    parser.add_argument("--mode", choices=MODES, default="success")
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    if args.action == "cleanup" and not (pathlib.Path(args.directory) / "state.json").exists():
        print("No test state; nothing was submitted")
        return 0
    experiment = Experiment(args.directory, args.mode, resume=args.action == "cleanup")
    if args.action == "cleanup":
        experiment.cleanup()
        return 0
    if args.action == "dry-run":
        for mode in MODES:
            experiment.submit(mode, 8 if mode == "queue" else 2, mode, dry=True)
        return 0
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        experiment.execute()
    except KeyboardInterrupt as exc:
        experiment.event(str(exc))
        return 130
    except Exception as exc:
        experiment.event("ERROR: " + sanitize(str(exc)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
