# Bounded combination/queue probes

Continue the approved five-hour plan in the existing `github-ci-arc-hcu-soak` boundary, retaining exact image/node/UID/resource policies. One ARC dispatcher orchestrates 2–3 separately owned Volcano Jobs; this tests actual compute concurrency/queueing, not GitHub runner count. Alternative independent GitHub matrix jobs can arrive too far apart to prove queueing; operator-only manual submissions would not exercise the GitHub chain.

## Fixed scenarios

- `split4`: two 4-card/16Gi/2CPU jobs on one approved node. Require both correct computations, overlapping GPU compute intervals, and disjoint physical render-device major/minor sets.
- `mixed`: CPU32/16Gi compilation and 4-card/16Gi/2CPU compute on one node. Require real compile/GPU phase overlap, CPU pod sees no devices, both correctness/artifacts/cleanup pass. Record measured timings without claiming universal absence of interference.
- `gpu-queue`: start an 8-card/32Gi job, wait for its actual running Pod, then submit a 1-card/8Gi waiter on the same 8-card node. Require Pending while the first occupies all devices, resource scheduling evidence and automatic start after release; never allocate more than eight cards. Requested-but-pending total9 is intentional.
- `cpu-queue`: three CPU32/16Gi builds, one per approved node, in the queue with CPU capability64. Require two running/third pending, queue/resource events and backfill after a prior completion. Host CPU capacity alone is not the queue limit.

Each job retains activeDeadline180s/TTL300s; whole dispatcher bounded230s plus UID-correlated cleanup. All per-node compute CPU<=64/memory<=64Gi, allocated HCU<=8; total HCU<=24. Before submission perform the existing external no-collision/health/image readiness guard and require the owned namespace empty. No new privileges or network/credential access are needed.

## Evidence and ownership

Persist every UUID/name/UID before the next submission, then each Pod UID/node/image, reports, logs, events and bounded state timeline. Require actual image ID and successful exit/report, not merely Completed. Cleanup every recorded child in finally and independently afterward; a failed cleanup must not skip the remaining children. Reject mismatched run/runner/UID metadata. Record intentional pending states separately from failures. Lost-runner GitHub recovery remains a known watchdog gap, even with compute deadlines/TTL.

Pure unit tests first: resource envelopes, illegal requests, overlap/disjointness, queue backfill evidence and fail-closed missing evidence. Pin source/workflow SHA and update only the known test workflow access entry. Retire only the known obsolete inactive test reference if the10-entry limit is reached, preserve every unrelated entry. Start with split4, then mixed and both resource queues; pause failing scenarios and inspect evidence before retry. Stop submissions14:45Z.
