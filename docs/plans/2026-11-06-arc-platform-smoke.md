# ARC platform validation

Scope: isolated test/arc-platform-20261106 branch; no production workflow,
stable tag, node configuration or existing runner changes.

Decision: use a branch-filtered push workflow for six bounded shell-only jobs.
This avoids adding a workflow to main just to enable manual dispatch discovery.
No checkout, credentials, GPU requests, Docker or Kubernetes access is needed.
Each job sleeps for 60 seconds and has a five-minute timeout.

Observe GitHub job timestamps and Kubernetes runner pods independently. Confirm
successful completion, actual concurrent execution, maximum four runner pods
(excluding terminating pods), and eventual return to one idle runner. Record
failures as failures; do not infer success from Helm deployed or Pod Running.

Failure, cancellation and recovery tests follow after the baseline succeeds.
Volcano submission, HCU isolation and business CI migration are out of scope.
