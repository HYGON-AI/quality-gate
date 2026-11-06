# ARC real CI end-to-end implementation plan

> Use the available executing-plans skill for checkpointed implementation; no unavailable superpowers tools or delegated agents.

**Goal:** Exercise GitHub -> ephemeral ARC runner -> Volcano CPU/HCU compute -> reports/artifacts -> GitHub conclusion -> cleanup using real compiled test fixtures in quality-gate's isolated test branch.

**Architecture:** Keep the existing dispatcher pool min=1/max=4 and the existing CPU-only namespace untouched. Add a separate bounded compute namespace, queue, quota and fail-closed admission boundary; grant its job/log-only role to the existing projected-token submitter. Never mount admin kubeconfig or App key in a job. Restrict runner-group access to immutable reviewed reusable workflow SHAs, quality-gate only, and submit only on nmz3. CPU, 1-card and 2-card are workload profiles, not separately registered static runners.

**Tech Stack:** GitHub reusable workflows, ARC 0.15.1, Kubernetes 1.31, Volcano 1.12.2, cached digest-pinned PyTorch 2.7.1, g++ 11.4, Python unittest.

## Task 1 — inspect and prepare boundaries

- Files: `deploy/arc-e2e/resources.yaml`, `tests/test_arc_e2e.py`.
- Verify ci-nmz3 remains stopped, node has no foreign GPU processes, no production work in target namespace, cached image exists.
- Create only new namespace-scoped resources and a namespace-selected admission policy; no existing policy loosening. Role permits VC job create/read/delete and Pod/log/events read, not secrets, exec, direct Pods or RBAC writes.
- Per-job max2 HCU, max4 CPU, 8GiB RAM, deadline180s, one task/replica/container, fixed image/queue/node, no volumes/privileged/host-network/init/plugins. Namespace cap4 HCU,16 CPU,32GiB,4 jobs/pods.
- Dry-run positive cases and negative wrong node/image, excess GPUs, credentials/volumes/plugins/privilege; test SA can-i denials before use.

## Task 2 — actual CI fixtures and submission

- Files: `tests/fixtures/arc_e2e/axpy.cpp`, `tests/fixtures/arc_e2e/run_ci.py`, `scripts/arc-ci-e2e.py`.
- Build C++ shared library, execute ctypes correctness tests, run selected real repository unit tests, generate JUnit+JSON+compiled binary. For HCU profiles additionally validate exact device count and small tensor calculations on every assigned card against CPU reference.
- Bundle only an explicit file allowlist from pinned checkout; hashes logged, no secrets/workspace tar. Embed compressed bundle into Job command (no outbound network needed).
- Return bounded report and binary via structured stdout; dispatcher verifies SHA256 before decoding artifacts. Logs/errors retained on failure.
- UID/owner/run correlated cleanup in finally AND independent always() step. SIGINT/SIGTERM handling, finite job/compute deadline and finished TTL.

## Task 3 — trusted workflow and actual runs

- Files: `.github/workflows/arc-ci-e2e.yml`, `.github/workflows/arc-ci-e2e-trigger.yml`.
- Commit tested code first; reusable workflow pins checkout to that SHA. Commit workflow next; runner-group allowlist adds exactly that workflow SHA preserving old entries. Caller only pushes on the test branch/path. No main/stable edits.
- Run success matrix CPU, HCU1,HCU2 (max3 jobs, total3 cards), verify artifacts and all3 real results and ARC runners.
- Run intentional assertion failure with no continue-on-error: GitHub must fail, logs/JUnit uploaded, compute cleaned.
- Run cancel case: cancel only this run after HCU work starts, verify independent cleanup externally and artifacts where possible.
- Run recovery after fault: fresh job succeeds and uploads artifacts.
- Archive run/job/artifact IDs, timestamps and final cluster/runner state. Do not claim multi-node/RDMA or arbitrary PR security completed.

## Scope authorization

User requested actual full-chain test cases in quality-gate and clarified ARC must support CPU and HCU. Explained bounded test permissions; proceed with the described least-privilege HCU path, not general cluster administration for CI.
