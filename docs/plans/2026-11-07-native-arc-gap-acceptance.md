# Native ARC gap acceptance implementation plan

> Execution: follow the available executing-plans skill in this session; no delegation or production migration.

**Goal:** Accept the remaining native ARC CI execution gaps before a small repository migration, reusing the colleague's completed acceptance rather than repeating it.

**Architecture:** Native ephemeral Runner Pods execute ordinary single-node CI. Keep existing multi-node Volcano results as prior evidence, not evidence for native pools. Preserve the colleague's pools/configuration; create separately owned test resources only if required. A mixed-container Kubernetes hook variant is a distinct execution mode and must not be silently conflated with direct execution.

**Tech Stack:** Existing ARC0.15.1, K8s1.31.11, Volcano1.12.2, GitHub App, quality-gate test/arc-platform-20261106 only.

## Accepted prior evidence (do not repeat)

The colleague's DEPLOY-7NODES.md sections7 items1-14: E2E assignment, label routing, scale-from-zero,6jobs/max4, cgroup/device/shm/mount/thread checks, exit17, ordinary cancellation, taint, queue boundary, two-node gang/DNS, TCP RCCL. Treat these as supplied evidence for their tested templates only. No destructive taint/plugin/Docker/kubelet/clock/card reset operations in this batch.

## Remaining gates

1. Read-only inventory of actual pools, approved images, hook templates, role boundary and occupied GPUs. Record drift against the report. Exclude nmz3 from HCU/performance while health=degraded; only select free healthy approved nodes4/6 with no legacy CI/KFD conflict.
2. Inspect available native framework runtime. Reuse a validated image if present. If absent, build a separately named test-only Runner+framework image using existing cached sources; do not modify colleague images or use host Docker socket/privileged DinD inside tasks. Record immutable image identity on each selected node. If required environment is unavailable, report blocked instead of green device-only smoke.
3. Add unit-validated test-only fixture/caller and owned pool manifests. New test resources use min0/max1 per card profile, nonroot/noAPI token/nohost privileges, fixed BW1100+health selectors, baseline-or-stronger admission. Do not change existing pools/access breadth; allow only a reviewed immutable test workflow by narrowly replacing an inactive own entry if needed.
4. Native real1/2/4/8card CI: clone actual fixed repository source, C++build and unit tests, all allocated HCU real correctness-checked computation, reports/artifacts and physical device identity. Verify node/model/image/source against actual Pod and GitHub assignment. No import-only or visibility-only acceptance. Keep total <=8HCU on one node and <=16HCU cluster; finite workload <=3min and Job<=8min.
5. Native Runner loss after active real computation: delete ONLY an owned test ephemeral Runner Pod with UID/assignment guards. Verify process/HCU release, ARC replacement and GitHub terminal state within bounded observation. Preserve known failure if GitHub still hangs; close only the owned run and do not grant new API permissions or deploy a production watchdog silently.
6. If the actual native image/selector/workflow differs materially from colleague evidence, run only the corresponding integration delta (e.g. real build artifacts transferred to a card job), not the entire completed base matrix.
7. Release decision: list accepted, failed and untested by exact pool/image/workflow. BW1000 unaccepted while nodes not in cluster; RoCE/performance unaccepted until prerequisites and measurements; no five-hour stability or large-repository throughput claim. Tomorrow migrate only a few approved repositories/specs after review; never automatically modify production CI.

## Boundaries and stop conditions

- Renewed window: stop new submissions2026-11-07T11:00Z, cleanup own active tests by11:15Z; no recurring automation or overnight soak.
- Preserve main/stable, production repositories, other users' pools/tasks and untracked files. No new broad cluster privileges, no admin kubeconfig/App PEM in Runner tasks, no disk/image cleanup or infrastructure restart.
- Root free>25Gi, MemAvailable>64Gi, nodeReady/noPressure, exact image identity, exclusive selected cards; otherwise stop affected test.
- All object writes and fault actions recorded by exact UID; do not delete by shared namespace/name prefix alone. New pools drained/deleted only after own jobs terminal; restore their baseline min0. Do not stop/remove shared ARC components.

## Work items and verification

- Discovery script outputs/arc-native-discovery-remote-20261107.py, whitelisted fields only.
- New native image/fixture/manifests and tests only after discovery; write failing tests before implementation, run full existing ARC regression before push.
- Keep outputs/arc-20261106/native-gap-state.json and native-gap-progress.md with source/ref/runIDs/resourceUIDs/results; no secrets.
- Implementation success is not migration approval: runtime correctness, lifecycle and appropriate isolation must all pass for each published specification.
