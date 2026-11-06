# Three-node non-root HCU validation

Continue the authorized five-hour plan after nmz3 one/two-card full-chain success. No production migration or runtime root is needed.

## Bounded test boundary

Create a separate owned `github-ci-arc-hcu-soak` namespace and `arc-hcu-soak` Volcano queue, derived from the existing soak boundary. Keep old CPU/e2e/account policies unchanged. Retain UID/GID1001, supplemental groups39/998, RuntimeDefault, dropALL, no escalation, no host mounts, no service-account token and deny-network. Fixed nodes nmz3/4/6, fixed test image with Never pull, exact node-specific runtime image IDs. Standard compute2CPU/8Gi, compile32CPU/16Gi; each pod2Gi ephemeral, activeDeadline180s/TTL300s. Queue CPU64/RAM128Gi/HCU24; namespace quota CPU128/RAM128Gi/HCU24, max16pods/jobs. At most64CPU/64Gi and8HCU per node from this plan.

Offline-built per-node IDs from the identical Dockerfile/base are test-only. Record and validate each immutable local ID, never infer image equivalence from the shared tag. Existing base image is unchanged; no registry upload or large export. Before RoleBinding: positive dry-runs for each node/profile, negative foreign node/image, root, token, host volumes, privileges, oversized requests; RBAC deny Secrets, direct Pods/exec, Services, RBAC writes and other production namespaces.

## Sequence / actual acceptance

1. Check current node readiness, free disk/memory, no foreign KFD processes or active GPU reservation before HCU submissions. Preserve quality and foreign ARC pools.
2. First run hcu1 on all three nodes; then hcu2. Each case must pass real C++ compile, repository unit tests, exact visible-device count, torch reference calculations and35s bounded compute, hash-verified artifacts, actual immutable image ID, and UID-correlated cleanup. Stop failing node/profile before escalation.
3. Run hcu4 and hcu8 only after lower-card counts pass on that node. These are independent per-device calculations, NOT an RCCL collective.
4. Mixed overlap: two4-card jobs on one node must have disjoint render-device allocations; CPU32 compilation plus HCU compute must overlap with bounded requests. Compare observed timings; do not claim no interference without measurements.
5. Explicit resource queue: submit enough owned jobs simultaneously to exceed only this test queue/card availability; observe Pending/resource reason, recorded active allocations, and automatic start after prior completion. GitHub runner queue is not equivalent. Use at most four ARC dispatchers and no resources outside the approved three nodes.
6. Two-node TCP proof already exists. Gloo/RCCL and RDMA need separate constrained rendezvous/network/resource validation; no hostNetwork/privileged bypass. Mark untested if not established within the window.

## Reliable result/teardown

Pin trusted source and workflow SHA, allow only exact immutable workflow entry in existing selected quality-gate group. Save run/attempt/owned UID before further submission. Failure/cancel/timeout must produce a non-success and verified cleanup. Lost-runner GitHub recovery still needs external watchdog/manual cancellation; TTL alone is not a complete solution. Stop new submissions14:45Z, cleanup by15:00Z, verify our ARC pool min1/max4 and no own compute leaks.
