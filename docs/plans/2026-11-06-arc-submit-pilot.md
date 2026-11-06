# ARC Trusted Submitter Pilot Implementation Plan

> Use executing-plans for checkpointed execution; unavailable superpowers tools are not required.

**Goal:** Complete a bounded, trusted ARC-to-Volcano CPU submission path and correct verified resource-name/node-class inconsistencies without migrating production CI.

**Architecture:** Keep the existing ARC dispatch pool (min1/max4, nmz3 placement). Restrict its GitHub group to the immutable test workflow commit before adding a dedicated submitter service account. Separate computation into `github-ci-arc-pilot`, with restricted Pod security, no network access, no credentials and zero HCU quota during this phase. Preserve existing production runners and quality-gate stable.

**Tech Stack:** ARC 0.15.1, Kubernetes 1.31.11, Volcano 1.12.2, GitHub Actions, kubectl 1.31.11, Python stdlib.

## Decision record

- Recommended: namespace-scoped trusted submitter for a CPU-only pilot. Permission to create Volcano Jobs is still workload-creation authority, so RBAC alone is not a security boundary; combine trusted workflow restrictions, isolated namespace, resource quotas and admission controls.
- Rejected: mount administrator kubeconfig or host Docker socket into runners.
- Deferred: a custom job-submission API/broker and broad repository rollout; unnecessary to prove this pilot, but future trust separation may need it.
- Trade-off: a local, versioned runner image on nmz3 is sufficient for this pinned pilot but not a production multi-node distribution strategy. Promote a verified image to a controlled registry before expanding placement.
- No GPU workloads, no node time changes. Non-synchronized time is escalated for coordinated operations follow-up.

## Implementation checkpoints

1. Read-only fresh inventory: group ID5 visibility selected quality-gate; no current Volcano Jobs/PodGroups; all required admin permissions; Helm values backed up with explicit kubeconfig; identify cached base image digest and installed kubectl.
2. Prepare a reusable-only trusted workflow and Python bounded submit/log/verdict/ownership cleanup script. Push only independent test branch; initial push must not execute compute. Record immutable commit. A separate test-branch push caller will reference this exact SHA; new workflow_dispatch workflows need default-branch registration, so do not modify main merely for dispatch.
3. Restrict group5 to this workflow at that commit and verify; refuse mutation while unrelated ARC jobs are busy. Preserve group settings for rollback. Do not touch ci-quality or ci-general.
4. Build versioned pilot runner image using cached pinned runner image and matching installed kubectl. No system package installation or publishing to public registry. Verify kubectl and image identity. Preserve image locally.
5. Create isolated pilot namespace, limited compute SA, dispatch SA, namespace Role/RoleBinding (VC Jobs create/get/list/watch/delete; Pods/logs/events read only), restricted Pod security, ResourceQuota/LimitRange, deny-all compute NetworkPolicy, and pilot queue CPU/memory/HCU0 limits. Validate negative cases before enabling runner access.
6. Correct default queue dcu->hcu only if no Jobs/PodGroups exist, using resourceVersion/test guards; snapshot pre-state. Add operator-owned BW1100 label only to nmz3/4/6 after verifying no existing conflicting values. Do not alter plugin raw BW1101 value or claim seven nodes joined.
7. Helm upgrade existing dispatch scale set with preserved values plus pilot image and dedicated SA. Keep limits/placement/min/max; only when idle. Readiness and `can-i` must show allowed submission only to pilot namespace, denied Secrets/RBAC/other namespaces.
8. Trigger the trusted CPU-only test with a separately committed push caller pinned to the reviewed reusable-workflow SHA: bounded two small jobs with explicit success/failure exits, collect logs, verify terminal states and exit codes, delete only UID+label-owned Jobs, verify no probe Pods remain. No HCU devices requested. Test cleanup and negative authorization; preserve artifacts without credentials.
9. Report what changed, evidence, rollback procedures and deferred HCU/time/production-hardening tasks. No claim of GPU or multi-node readiness.

## Rollback

- If submission/policy validation fails, do not grant broader permissions. Remove/disable only the new pilot binding after jobs are cleaned; restore prior Helm revision and group allowlist if necessary.
- Do not delete shared namespaces or CRDs. New namespace deletion is not automatic: inspect exact owned resources and archive evidence first.
- Reverse queue/label changes only with fresh comparison against our applied values, never overwrite later operator changes.

## References

- https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/
- https://docs.github.com/en/rest/actions/self-hosted-runner-groups
- https://volcano.sh/docs/concepts/queue/
