# nmz3 bounded HCU validation

User authorized switching the test node from occupied nmz6 to nmz3 and stopping only idle ci-nmz3. ci-nmz3 is verified offline; two manual containers contain only sleep, and the user was asked to coordinate no manual GPU submissions during the window.

- Recheck no legacy Runner/Worker, no GPU processes, healthy node and 8 allocatable HCU before each test batch.
- Use cached immutable PyTorch image, Volcano jobs in existing github-ci namespace, pinned to nmz3. Operator submits from host; no administrator config or service-account token in compute containers.
- Do not modify ARC CPU-only admission/RBAC or production workflows. This phase is compute-layer validation, not an end-to-end ARC migration claim.
- Start with 1 card, 4 CPU, 8GiB RAM, 2GiB ephemeral storage, 240s deadline. Validate device count, small matmul against CPU reference, three timing samples, report read/write and cleanup.
- Next two simultaneous single-card jobs: verify distinct physical assigned devices and overlapping execution. Follow with a two-card correctness test.
- Finally compare single-card baseline / overlap with bounded fixed-source CPU compilation / baseline again. Compilation is capped at 32 CPUs, 32GiB RAM and 180s; do not claim full-node saturation or representative repository build performance.
- Every job has a unique ownership label and UID-guarded cleanup; capture pod, runtime device mapping, logs, completion and cleanup evidence.
- After mixed tests, reserve all 8 nmz3 cards for a short correctness probe and 40s hold, then submit one 1-card job pinned to the same node. Observe unscheduled Pending at least 12s and verify compute begins only after the 8-card pod releases resources. No changes to shared queue capacity.
- Stop at failed isolation, unrelated workload, pressure or execution failure; preserve diagnostics. Never stop coworkers' containers or modify device-plugin configuration.

## Executed results (2026-11-06)

- Single-card compute/correctness/report read-write: passed. Two single-card jobs overlapped 14.95s on distinct physical devices. Two-card request exposed exactly two devices; per-device arithmetic passed (not collective communication).
- Eight-card request exposed exactly eight devices and passed small arithmetic on each; a subsequent one-card request remained Pending with `Insufficient hygon.com/hcu`, and started 3s after the eight-card container finished.
- First mixed attempt: CPU container failed before compilation because importing torch required unavailable `librocm_smi64.so.2`. GPU runtime received `/opt/hyhal` through device-plugin injection; CPU runtime did not. Removed the unnecessary torch import from the CPU compiler test, retained direct device-absence validation. This is not a fix to the runtime image.
- Retest: compiler ran 75.51s, generated 4049 object files, consumed 2394.22 CPU-seconds (~31.71 cores average); a sampled Docker reading was 3184.88% CPU and 915.8MiB RAM. CPU container had no HCU device nodes.
- Same GPU pod/renderD132: median per 2048x2048 FP32 matmul baseline 0.441142ms, mixed 0.443011ms (+0.424%), afterward 0.440752ms (-0.089%). Three 5s samples each; mixed samples fully within measured compilation interval. Not representative of all model/build workloads, memory bandwidth saturation, or whole-node overload.
- renderD134 repeatedly measured ~1.18ms versus ~0.44ms on renderD132/renderD133, including a later single-job run. Cause remains unconfirmed; do not attribute this to K8s or compiler contention without additional profiling.
- All 10 test Jobs/Pods were removed with owner/UID guards (8 completed successfully; one early CPU failure and its waiting GPU companion were cleaned). Final node Ready, no pressure, no GPU processes, old ci-nmz3 still stopped, ARC runner still Running, shared queue unchanged. Logs include a nonfatal `/var/log/hylog` warning.
- Evidence: local `outputs/arc-20261106/nmz3-hcu/`; remote `/home/github/lvj/nmz3-validation-20261106/` under per-run UUID directories. No production branch/stable or permission changes, no work on nmz6.
- Still untested in this phase: ARC-to-HCU end-to-end restricted submission, collectives/RDMA/multi-node, HCU cancellation/runner-loss recovery, real repository builds and long-duration load.
