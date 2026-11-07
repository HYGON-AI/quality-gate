# Card-count CI interface validation plan

**Goal:** Validate a test-only reusable 0/1/2/4/8/16-card entry point, including actual two-node 16-process collective correctness, without changing production CI.

**Architecture:** One ARC dispatch Job submits one Volcano Job to a NEW isolated `github-ci-arc-profiles` scope. Cards 0/1/2/4/8 use one Pod; 16 uses two Pods x 8 cards, gang minimum two, distinct approved nodes. Fixed allowlisted repository fixture script executes ONLY in nonroot, uncredentialed compute. This first validation is not a production arbitrary-source/script delivery service.

**Window:** 2026-11-07: stop submissions 09:30 UTC /17:30 China; cleanup by09:45 UTC/17:45. No renewed five-hour soak or recurring automation. ARC min1/max4 unchanged.

**Budgets:** One active profile Job/two Pods in the new scope; per Pod <=16 CPU/64Gi memory/2Gi ephemeral storage/8HCU, total<=32CPU/128Gi/16HCU. Fixed `/dev/shm` memory emptyDir capped1Gi is charged to memory, never host IPC. Preserve old admission policies, pools, manual containers and quality runners. New scope only model bw1100 because only those nodes are in this cluster. Reject unsupported model/image/script/cards; production CPU/RAM defaults are NOT calibrated by this fixture.

1. Check live API, selected node host readiness, old CI listeners, KFD users, image IDs, root>25Gi/freeRAM>64Gi and no resource pressure. Recheck before HCU submissions; preserve foreign workloads and avoid conflicting nodes.
2. Test-first profile resolution, manifests, actual bootstrap allowlist, all16 identity/result verification and negative inputs; local full ARC regression. Build fixed-script caller interface; no PR code executes on credentialed dispatcher, no secrets inherited.
3. Operator creates owned new scope, network/RBAC/quota/admission. Server dry-run all6 positives and negative privilege/volume/resource/placement/image probes BEFORE granting namespace submitter RoleBinding. No administrator credentials in tasks. Record resource UIDs.
4. Pin source SHA, reusable workflow SHA, narrowly replace one inactive OWN old workflow group reference (preserve foreign refs/repository restrictions), then test caller. Run0/1/2/4/8 sequentially; validate C++build/unit reports, exact image identity and compute correctness before16.
5. Sixteen-card proof: two distinct nodes x8 HCU, 16 global ranks, actual per-rank device identity, Gloo/RCCL all_reduce/all_gather correctness and Socket transport proof. Do not count 2ranks x1card as16; do not claim RDMA.
6. Exercise intentional failure and HCU deadline/cancel, verify report preservation and own UID cleanup followed by successful recovery. Runner-loss external watchdog acceptance remains a distinct required test; do not count ordinary cancellation/TTL as GitHub recovery.
7. Save run IDs/artifacts/evidence, final own empty scope and ARCmin1 readiness; leave unverified items explicit. No changes to main/stable, driver/plugin/clock/base services or production repositories; no disk/image cleanup. User-owned untracked nmz6 plan untouched.

**Checkpoints:** Stop the affected profile on repeated failures or unsafe readiness; diagnose before retry. If time expires, close out safely with partial results, never mark incomplete validation complete.
