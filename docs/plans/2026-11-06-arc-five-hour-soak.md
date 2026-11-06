# ARC / Volcano five-hour controlled validation plan

> Execute with the available executing-plans skill. No delegated agents or unavailable tools.

**Goal:** Validate real GitHub ARC dispatch, Volcano CPU/HCU scheduling and bounded failure recovery on github-nmz3/4/6, without changing production gates or other repositories.

**Architecture:** Keep ARC min=1/max=4 and immutable trusted-workflow access. Use explicit owned test namespaces/queues and fixed cached image digests; compute receives no kubeconfig, App key or service-account token. Extend only test admission boundaries after positive/negative server dry-runs. CPU, GPU count and node count are workload profiles, not static runner labels.

**Window:** 2026-11-06T10:00:00Z to 2026-11-06T15:00:00Z (18:00–23:00 Asia/Shanghai). Setup/diagnosis time is part of the window. No new work after 14:45Z; finish/cancel owned tests and verify recovery by deadline. Do not claim five hours of continuous load if preconditions prevent it.

## Scope and safety

- Repository HYGON-AI/quality-gate, branch test/arc-platform-20261106 only. Never main/stable or production repository migration.
- User declares old work stopped and all three nodes available. Verify actual device processes before using each node; don't indiscriminately kill manual containers or foreign jobs.
- Preserve quality-nmz4/6 and all infrastructure. No node reboot/drain/clock/driver/device-plugin changes, no control-plane fault injection, no image/disk cleanup, no new credential privileges.
- ARC runner-loss test deletes ONLY an identified owned ephemeral test runner, never controller/listener or someone else's runner. Record job/pod UID before any deletion.
- Start small: CPU 2/8/32 cores; RAM 8/16/32Gi. HCU 1/2/4/8 per node only after baseline succeeds. Max 24 cards cluster-wide, at most 8/node; max64 CPU/64Gi per node for compute, bounded temporary storage2Gi/pod. Do not exhaust host memory/CPU/disk.
- Stop escalation on node NotReady, Memory/Disk/PIDPressure, available RAM<64Gi, root free<25Gi, foreign HCU process collision, repeated unexplained scanner/driver failures, lost cleanup ownership or credentials in output. Stop affected test scope; report evidence, do not weaken isolation to force success.
- All workloads need deadlines <=10min and bounded TTL. Keep evidence before cleanup; cleanup UID/labels only. Hard-killed dispatchers require external orphan observation/reaper, never assume finally() ran.

## Stages and acceptance

1. **Readiness and regression:** capture nodes, allocatable resources, plugin state, cached digests, old listener/worker absence, manual device use, disk/memory. Diagnose earlier non-root HIP initialization failure; CPU success is not HCU success.
2. **Single-node full chain:** on each healthy node execute C++ compile, repository unittests, CPU correctness, 1/2-card tensor correctness, exact visible devices, reports/hash-checked artifacts and UID cleanup. Then4/8-card cases. Record actual node+device identities.
3. **Mixed concurrency and queues:** repeat CPU-only, HCU-only and CPU+HCU combinations; mix short/long,1/2/4/8-card requests. Distinguish GitHub max4 runner queue from Volcano insufficient-resource queue. Demonstrate running overlap, unschedulable event and start after resources released. Measure dispatch/pod wait/runtime/cleanup, CPU/RAM/HCU occupancy; no throughput claims from screenshots.
4. **Two-node:** first gang start on two different nodes and TCP connectivity, then bounded torch distributed collective correctness (Gloo/CPU and RCCL/HCU where supported). Reserve two nodes atomically with minAvailable; do not call two unrelated jobs distributed training. RDMA requires explicit allocated RDMA resources, transport proof and no host networking/privileged bypass; otherwise mark RDMA untested/blocked.
5. **Robustness:** intentional assertion failure, compute timeout, GitHub cancellation, owned ephemeral runner deletion, orphan detection/recovery, subsequent clean successful job. Never treat intentional failures as infrastructure success without confirming cleanup and subsequent recovery.
6. **Soak and teardown:** repeat proven combinations until14:45Z with checkpoints at most5min apart. Unexpected failures pause the failing profile. At cutoff no submissions, cancel only own running GitHub runs and delete only UID-correlated compute. Verify ARC returns min1, no own GPU processes/pods/jobs, nodes healthy. Save final pass/fail/untested matrix and migration blockers.

## Implementation tasks

1. Extend scripts/arc-ci-e2e.py and fixture only with tested fixed profiles; add unit tests before changes. Preserve old CPU namespace restriction.
2. Add dedicated deploy/arc-soak resources or extend owned e2e resources with reviewed node/CPU/HCU bounds; server dry-run positive/negative requests before RoleBinding.
3. Pin trusted source commit in reusable workflow, then pin reusable workflow commit in trigger and runner-group allowlist. Preserve unrelated selected workflows/repositories.
4. Trigger and verify one complete baseline before scheduling repeated runs. Save run IDs and artifacts in local progress ledger before triggering another, to avoid duplicate work.
5. Two-node communication may need a separate narrowly allowed test NetworkPolicy, services and rendezvous configuration. Do not silently remove existing deny-network policy or grant broad service/RBAC writes.

## Evidence and resumption

- Local progress: E:/Codex工作目录/outputs/arc-20261106/five-hour-progress.md
- Machine-readable run ledger: E:/Codex工作目录/outputs/arc-20261106/five-hour-state.json
- Evidence: E:/Codex工作目录/outputs/arc-20261106/soak-* and GitHub test run artifacts.
- Every continuation reads plan+progress+state, checks recorded GitHub/K8s state before acting. At deadline stop and delete temporary heartbeat.
