# Low-noise gate implementation plan

**Goal:** Fix confirmed multi-document YAML false positives, retain advisory secret detection, and prevent ambiguous wording from blocking valid upstream changes.

**Architecture:** Preserve mandatory integrity checks and explicit scanner failures. Validate YAML streams without executing constructors; validate Actions as a single mapping. Compare existing syntax debt with the merge base. Keep sensitive wording and secrets advisory because lexical matches cannot establish ownership or exploitability. Deduplicate UI annotations without deleting full findings.

**Tech Stack:** Python 3.9+, PyYAML, unittest, pinned Docker scanners, GitHub Actions.

## Tasks

1. Add failing regression tests in `tests/test_low_noise.py`: multi-document YAML, malformed second document, tagged YAML, duplicate keys, single-document Workflow, old syntax debt, advisory redacted secrets, lexical wording, annotations.
2. Implement YAML validation in `src/hygon_pr_gate/yaml_checks.py` and use it in native syntax checks; keep templates explicitly advisory rather than claiming they are validated.
3. Restore Gitleaks parsing and placeholder filtering from v2.0.3, preserving pinned image and offline execution. Findings are advisory; missing reports or scanner failures remain invalid scans.
4. Make ambiguous sensitive-word findings advisory and use token rather than substring matching. Retain findings for manual review, including upstream contracts.
5. Update regression expectations, documentation, and CI to run unit, native and bootstrap tests on Linux. Retain full reports while reducing duplicate annotations.
6. Run local regressions, replay the two incident files read-only, push a branch and open a PR. Verify Linux CI before delivery; report any unavailable real-scanner coverage honestly.

## Acceptance

- Kubernetes Deployment + Service documents parse; malformed later documents still block.
- Unknown YAML tags are never executed; Actions cannot exploit generic YAML handling.
- Existing identical syntax debt is advisory, newly broken files still block.
- Secret material is absent from reports and annotations; secret-only findings do not fail a gate.
- No tag moves, automatic business-repository upgrades or direct protected-main pushes.
