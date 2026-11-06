# ARC CPU Reliability Implementation Plan

> Execute with the available executing-plans skill in this existing independent test worktree. No subagents or unavailable superpowers tooling required.

**Goal:** Verify Volcano CPU queueing, compute/GitHub timeouts, cancellation, abrupt dispatcher loss, orphan reclamation and subsequent recovery.

**Architecture:** Keep min1/max4 and the existing CPU-only namespace/SA/admission boundary. Pin a new reusable workflow and its checked-out test scripts to immutable commits. Temporarily reduce only the dedicated pilot queue CPU capability from 2 to 1; three 500m CPU requests then exceed queue capacity without exceeding the namespace quota. Restore the queue afterward.

**Tech Stack:** ARC 0.15.1, Volcano 1.12.2, kubectl 1.31.11, Python stdlib, GitHub Actions.

## Scope and choices

- Recommended: a fixed-SHA checkout of trusted test code using the current kubectl-enabled image. No image rebuild or administrator credentials in jobs.
- Rejected: arbitrary caller-provided shell/manifests, changing production queues, CPU saturation tests or touching legacy CI.
- Fault injection is limited to a verified test runner Pod/container matched to Run ID, runner name and Pod UID. No controller/node failure injection.
- For the orphan test only, Pod deadline is 25s and Volcano finished TTL 30s to observe bounded reclamation promptly. This does not validate indefinite Pending-job cleanup or the production 600s TTL elapsed duration.

## Checkpoints

1. Write unit tests for fixed modes, bounds, CPU-only manifests, correlation labels and cleanup ownership. Implement a new script importing existing pilot helpers. Run all pilot unit tests.
2. Fresh inventory confirms no pilot compute work, no busy dispatch runner, group restricted to existing trusted SHA, queue cpu2 and HCU0. Preserve all values; do not change other queues, quotas or permissions.
3. Commit scripts on test/arc-platform-20261106. New reusable workflow checks out that exact SHA, accepts only a bounded mode enum, and is itself pinned in ci-k8s access. Trigger one mode at a time via branch-only push caller.
4. Queue: three single-container jobs, request500m/limit1CPU each, 25s hold. Observe <=2 simultaneously running, a pending third, then third admission after release; all success and clean.
5. Compute deadline: 90s hold with 15s Pod deadline, expect nonzero/DeadlineExceeded, not success, and cleanup.
6. GitHub cancellation: after actual compute Running, cancel only that run. Verify Job/Pod removal and GitHub cancelled. GitHub deadline: 1min job budget vs 110s compute hold; verify non-success and cleanup.
7. Runner loss: after correlated compute Running, abruptly terminate only the verified temporary runner container and delete its Pod with UID guard if needed. Observe compute deadline and TTL without manual compute deletion. Preserve observations independently because runner artifact upload may be lost. Any manual remediation means auto-cleanup did not pass.
8. Recovery: execute known success/failure pilot again, verify logs/artifacts, replacement runner and zero compute leftovers. Restore queue cpu2 with old-value guard. Preserve evidence, expected failures and limitations.

## Rollback and safeguards

- All compute jobs carry run/mode/unique-owner labels, and deletion uses name + owner + UID precondition.
- At most 3 compute Jobs, namespace HCU quota stays0, no additional resource grants.
- Stop on unrecognized state, unexpected production impact or repeated verification failure; do not broaden privileges.
- Group allowlist rollback is optional and must retain original trusted workflow. Never disable restrictions while permissioned runners remain.
- New test workflows remain only on the test branch; no main/stable modification.
