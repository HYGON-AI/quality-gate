# Bounded two-node collective validation

**Goal:** Actual Gloo/CPU tensor and RCCL/HCU tensor correctness through ARC/Volcano on each approved node pair, not a repeated TCP-only probe.

**Architecture:** Reuse the UID-correlated pair harness with explicit result-validation hooks. Use a NEW owned namespace/queue, two replicas/minAvailable2, required node anti-affinity, one HCU/2CPU/16Gi per rank, 180-second deadline. Operator-created headless rendezvous; default-deny plus same-test peer TCP and CoreDNS only. No task token, credentials, root, host networking, RDMA allocation or production changes. NCCL_IB_DISABLE=1 explicitly tests sockets; preserve real API names. Gloo shares the HCU runtime injection, so this is NOT CPU-only-container Torch coverage.

Alternatives: extending CPU pair permissions would weaken its tested boundary; raw host networking would skip the network isolation under test. Prefer a separate narrow scope despite extra preparation.

## Execution

1. Add failing tests for fixed resource/placement/security/network bounds and strict collective proof (rank, world, identities, rounds, correctness, transport).
2. Implement separate fixture and manifest/resources; minimally generalize pair harness without changing old defaults. Run all ARC unit tests.
3. Create only owned resources; three positive pair dry-runs and negative node/replica/resource/credential/privilege/image probes BEFORE RoleBinding. Verify task cannot create services/pods or read secrets.
4. Pin source commit, then reusable workflow commit. Retire only inactive obsolete positive-only pair workflow 8f6bff03a7c84d500668d33734727e5277bc1d5b; preserve all other group entries and max4.
5. Readiness before GPU work. Run one pair first; inspect real per-rank Gloo/RCCL all_reduce/all_gather results, socket transport logs, immutable node image IDs, artifacts and cleanup. On failure preserve evidence; do not broaden privileges or silently claim success. Repeat other pairs if safe/time permits.
6. GPU multi-child cancellation and subsequent clean recovery; repeat proven bounded probes until14:45UTC. No RDMA claim. Stop/clean by15:00UTC.
