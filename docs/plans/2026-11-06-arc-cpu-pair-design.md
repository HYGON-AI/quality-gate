# Two-node CPU gang and TCP validation implementation plan

> Execute within the already authorized five-hour plan using available executing-plans; no subagents.

**Goal:** Verify one Volcano gang with two CPU replicas placed on two different allowed nodes, actual bidirectional correctness-checked TCP exchange, artifacts, GitHub conclusion and owned cleanup. This is NOT Gloo/RCCL/RDMA validation.

**Architecture:** Add an isolated restricted namespace github-ci-arc-pair and queue arc-pair, one active Job maximum. One task has2replicas and minAvailable2; required pod anti-affinity prevents same-node placement, required node affinity selects exactly one of the3approved node pairs. A fixed operator-created headless Service selects task-index0. Compute gets no API token/credentials/host mounts; ARC gets only Job CRUD and Pod/log read, never Service/RBAC/Secret writes.

**Tech Stack:** Existing cached image/digest, Python sockets/hashlib, actual C++ build/repository unit-test fixture, ARC/Volcano, Kubernetes headless Service and selected NetworkPolicies.

## Options considered

- Recommended: a separate CPU pair namespace with two replicas, fixed Service and narrow TCP/DNS policies; no edits to existing deny-network CPU namespaces.
- Rejected for this test: enabling broad svc/ssh plugins or host networking (unnecessary access), pretending two independent single-node jobs prove a distributed collective, or granting CI create-Service rights for dynamic rendezvous.
- PyTorch Gloo/RCCL deferred: CPU-only image currently fails torch import without injected driver libraries, and HCU non-root issue remains under approval; do not invent a pass.

## Steps

1. Add tests/test_arc_pair.py for exact pairs, minAvailable2/replicas2, anti-affinity, no HCU/token/privilege, fixed digest/deadline/quota; ensure tests fail before implementation.
2. Implement scripts/arc-pair.py manifest and dispatch helpers. Reuse explicit bundle, hash-checked per-pod artifact parser and UID-correlated cleanup from arc-ci-e2e. Reject unknown pairs. Verify2pods/2ranks/2different actual nodes, both exit0 and both report passed before success.
3. Implement tests/fixtures/arc_e2e/run_pair.py: run actual C++/CPU/repository tests first, then20rounds of64KiB challenge/hash/partial-sum TCP exchange. Derive rank from downward task-index label. Fixed port29500, bounded60s connection, positive/negative assertions and JSON/JUnit. Never print environment/credentials.
4. Implement deploy/arc-pair/resources.py deriving isolated boundary; quota1Job/2Pods/8CPU/32Gi/4Gi ephemeral/HCU0. Retain deny-all, add only pair-to-pair TCP29500 and pair-to-CoreDNS TCP/UDP53; fixed headless Service is operator-created. No submitter Service permissions. Fail-closed admission verifies fixed profiles,2replicas, safe affinity/security/deadline/image and no plugins/mounts. Positive3pairs and negative wrong nodes/affinity/token/HCU/privilege dry-runs before binding SA.
5. Pin tested source in new reusable workflow; pin workflow in runner-group allowlist and test-branch caller. No main/stable or production changes. Trigger exactly one pair, save runID, verify artifacts+actual placement/overlap and cleanup, then test remaining two pairs sequentially. Only1Job allowed, so don't parallelize pair workflows.
6. Recheck network enforcement: successful allowed traffic alone does not prove forbidden egress denied. Record policy configuration separately until an explicit denied-traffic probe is observed. Clean owned Jobs only; retain test platform resources until final teardown decision.

## Acceptance and evidence

- Both replicas execute real compile/18repository unit tests, no HCU devices visible, one node each from selected pair, paired TCP checksums/partial sum agree for20rounds.
- GitHub cannot pass if either pod/report/exit/node verification fails. Logs/JUnit/build binaries uploaded for both ranks. Cancellation and deadlines apply to entire gang; no blind namespace delete.
- Reference: https://kubernetes.io/docs/concepts/services-networking/network-policies/ and https://volcano.sh/docs/v1.13.0/userguide/user_guide_how_to_use_job_policy/ (installed CRD/server dry-run remains authoritative for1.12.2).
- Continue CPU soak batches only when prior batch finished; preserve any external pools added by another operator. Stop submissions14:45Z, cleanup by15:00Z.

## Step6 concrete denied-port check

Keep all policies unchanged. Rank0 additionally listens on29501 and proves its local loopback client can connect; while this listener remains live, rank1 must time out connecting to the master's actual PodIP29501, then complete the allowed29500TCP protocol. Connection-refused is NOT accepted as proof (could be absent listener); a successful forbidden connection fails the test. Validate the pure bounded probe with timeout/refused/success unit cases before updating pinned source and workflow. This proves only the specific inter-Pod forbidden port, not all egress isolation.
