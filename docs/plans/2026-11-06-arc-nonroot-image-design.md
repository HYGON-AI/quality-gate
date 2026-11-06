# Non-root HCU image correction

Same-pod A/B on nmz3 found that the cached base image has no UID1001/GID1001 account. With unchanged kernel UID/groups/card, a diagnostic NSS mapping made a real torch tensor succeed. This is a causal diagnostic, not a shippable LD_PRELOAD workaround.

## Decision

Build a dedicated derived test image that contains a real locked `ci-runner` account UID1001/GID1001 and owned home. Retain non-root runtime, dropALL, no privilege escalation, no host mounts or credentials. The build uses only the already cached immutable base; no network/package installation. Do not alter or overwrite the original image/tag.

Alternatives: runtime root would broaden the boundary and requires unanswered approval; LD_PRELOAD interception is diagnostic-only and inappropriate as a durable compatibility fix. A normal account in the image is the narrow correction.

## Verification sequence

1. Unit-check the Dockerfile's exact base, locked UID/GID account, final non-root USER, no network install/capability changes.
2. Operator builds only on nmz3 first, using an exclusively test-versioned name and network disabled. Inspect immutable local image ID and account state without GPU.
3. Establish an isolated owned image-test admission boundary (never loosen old CPU/e2e policies), requiring this image, nmz3, UID1001, <=2 HCU and existing resource/deadline/security bounds. Before binding run positive and root/foreign-image/host-mount/oversized negative dry-runs.
4. Execute a bounded one-card real test, then the full GitHub ARC->Volcano->compute->report->cleanup chain. Verify actual pod imageID equals recorded operator-built image ID. Do not call a local Docker command a GitHub end-to-end pass.
5. Only after this succeeds, determine controlled distribution to nmz4/6. No unapproved registry push, large archive or disk cleanup. Until a registry digest/distribution is verified, treat the image as nmz3-only, not fleet-ready.

Stop if disk free <25Gi, image identity mismatch, unexpected foreign HCU use, or unchanged tensor failure. Original image and production workflows remain untouched. Root test namespace is not approved or required by this approach.

## After nmz3 one/two-card pass: controlled test availability

Both full-chain cases passed on nmz3. For this temporary test, build the identical Dockerfile offline on nmz4 and nmz6 using their already cached exact base. No registry push, base-image export or large archive is required. Refuse to overwrite any pre-existing target tag without a recorded owned image ID. Record each node's immutable image ID and Dockerfile hash; node-specific IDs may differ because builds include creation timestamps. A new isolated dispatcher must verify the actual pod image ID against the node-specific recorded ID, not merely accept a common tag. This is test-only distribution, NOT a production immutable-registry release. Retain old boundaries unchanged and perform admission tests before binding new namespace access.
