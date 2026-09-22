# HYGON Quality Gate

HYGON Quality Gate is a reusable GitHub Actions workflow for incremental pull
request quality, security, and open-source compliance checks. It evaluates only
the commits, files, and changed lines introduced by a pull request.

[中文文档](README.md)

This document describes `v2.0.7`. Release tags remain fixed; `stable` is the rolling upgrade entry point.

v2.0.7 renames the three check groups while preserving the aggregate check and internal job IDs.
PR scans remove Lizard, YAML formatting, ShellCheck style diagnostics and CRLF advisories.
Semgrep scans only Python/JS/TS; C/C++ is explicitly out of scope. Unknown parsing errors,
tool failures and missing reports from retained scanners still fail the gate.

## Quick start

1. Copy [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
   to `.github/workflows/quality-gate.yml` in the target repository.
2. Update `pull_request.branches` for the target repository.
3. Replace `QUALITY_GATE_REF` with a reviewed release tag or full Commit SHA.

The following example uses the current stable release
[`v2.0.7`](https://github.com/HYGON-AI/quality-gate/releases/tag/v2.0.7):

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@v2.0.7
    permissions:
      contents: read
```

A full Commit SHA provides stronger immutability and is suitable for
repositories that require strict version pinning. A reviewed release tag may
be used when centralized upgrades are preferred.

Existing `@stable` consumers need no caller change. The runner group's selected
workflows must allow the chosen reference, such as
`HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@refs/tags/stable`.

Configure the following Required Check in the target repository's branch
protection settings or Ruleset:

```text
Checks / All required checks
```

## Checks

Gitleaks findings are advisory and redacted; they do not block merging.

| Job | Checks |
| --- | --- |
| Code compliance | <ol><li>Commit author, committer, email, and message fields</li><li>LICENSE/NOTICE/COPYING files, original copyright notices, and SPDX identifiers</li><li><code>THIRD_PARTY_NOTICES.md</code> changes</li><li>Organization and platform wording in newly added content</li></ol> |
| Code quality | <ol><li>Unsafe symbolic links, abnormal paths, Git blobs, and large files</li><li>UTF-8 and abnormal characters</li><li>Python/YAML syntax and Workflow references</li><li>Ruff high-confidence rules</li><li>ShellCheck non-style diagnostics</li><li>actionlint Workflow validity</li><li>yamllint syntax and duplicate keys</li></ol> |
| Code security | <ol><li>Gitleaks secret detection, redacted and advisory only</li><li>Semgrep Python/JS/TS findings remain advisory; C/C++ is not scanned</li></ol> |
| All required checks | <ol><li>Aggregation of the preceding results</li><li>A single branch-protection check and Job Summary</li></ol> |

Action and reusable workflow references in the target repository that are not
pinned to full Commit SHAs are reported as advisories and do not block merging.

Each check group writes its complete report to the Job log and GitHub Job
Summary. Blockers and advisories are also emitted as escaped file/line
annotations so developers can locate findings directly on the Actions page.

## Scope

This repository contains only:

- the reusable PR workflow;
- one universal, centrally reviewed incremental gate policy;
- the minimum Python implementation required by the workflow;
- native and scanner-output tests.

Any public or private repository can call the same reviewed version without a
repository-specific profile. The PR gate blocks only high-confidence
incremental problems, including forbidden identity fields,
definite syntax errors, legal-file or original-header damage, unsupported SPDX
additions. Lexical DCU/AMD/XGMI matches are advisory;
do not mechanically rename upstream copyrights, vendor backends or API/ABI contracts.

Whole-repository open-source compliance audit skills, quality and security
audit skills, history-rewrite skills, remediation reports, target repository
source, credentials, caches, and runner data are intentionally excluded.

Repository mode, upstream provenance, third-party registration, complete
license obligations, whole-tree file headers, historical metadata, and full
quality/security coverage remain part of periodic whole-repository audits.
Precise exceptions for protected external contracts must be centrally reviewed
in the universal policy and must not be supplied by an untrusted caller.

Ordinary YAML accepts multiple documents and custom tags without constructing objects.
Malformed documents and duplicate keys still block; Actions must be a single mapping.
Recognized Helm templates require rendered validation, not a claimed syntax pass.
Existing syntax debt is advisory only for conservative comment-only changes, not a
complete semantic baseline comparison. Unsupported language versions still need review.
Scanner failures or missing reports remain invalid scans.

Known follow-ups, not fixed by this release: repository Ruff configuration can
suppress diagnostics, and Git attributes can hide line diffs used by incremental
filtering. v2.0.7 does not claim to close these false-negative paths.

### Header preservation

Whitespace, line wrapping and common comment wrappers do not change a notice.
Removing or replacing original copyright/SPDX declarations still blocks.
Complete standard MIT/BSD-3-Clause bodies and the Apache-2.0 boilerplate notice
are recognized without SPDX. Removing their original terms or disclaimers
blocks even if SPDX remains. Names alone, partial bodies and unknown variants
do not establish license approval. Unknown-origin new files with missing
headers remain advisory; a new HYGON notice lacking both SPDX and a recognized
complete license remains blocking. No source is automatically rewritten and
H1/H2/H3/originality is not inferred. Recognition is bounded by the configured
header line limit and is not a proof of legal applicability.

Internal job IDs and `Checks / All required checks` remain stable. The three
display names are updated as listed above. Summaries show the decision,
counts, actual version and SHA first; details are folded and scanners with no
applicable files say so. Passing the gate does not grant permission to merge.

## Version consistency

The reusable workflow checks out its engine from `job.workflow_repository` at
`job.workflow_sha`. The workflow, policies, and engine therefore always come
from the same Commit selected by the caller; there is no second embedded engine
SHA to maintain.

## Runner requirements

The default runner labels are:

```json
["self-hosted", "linux", "x64", "quality"]
```

The runner must provide:

- Git, Docker, Python 3.9+, and PyYAML;
- the scanner images pinned in
  [`policies/quality-security/hygon-quality-security-v1.1.yaml`](policies/quality-security/hygon-quality-security-v1.1.yaml);
- an isolated, disposable, or equivalently hardened execution environment.

The action reuses existing Python and PyYAML. If PyYAML is missing, it creates
an isolated venv in `RUNNER_TEMP` and installs `PyYAML==6.0.3`. This requires
venv/ensurepip and PyPI connectivity. Python itself is never downloaded;
preinstalled PyYAML avoids network bootstrap.

All scanner images, including Gitleaks, must be preloaded during runner provisioning. The PR
workflow never pulls images from the network. If an image is missing or its
digest does not match the policy, the affected check returns `Invalid Scan`
instead of silently passing. After provisioning or cleanup, validate each
reference in the policy's `images` map with `docker image inspect`.

Before allowing untrusted pull requests in a public repository to use
self-hosted runners, review GitHub's Fork Workflow approval settings.

## Local development and validation

The following commands target a Linux environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python tests/runner_bootstrap_integration.py -v
python3 -m compileall -q src tests
```

After preinstalling the four policy-pinned Docker images, run:

```bash
PYTHONPATH=src .venv/bin/python tests/gitleaks_integration.py
PYTHONPATH=src .venv/bin/python tests/real_tools_integration.py --output /tmp/quality-gate-integration
```

These commands are verification requirements, not a claim that all tests have passed.
Release acceptance requires Linux, bootstrap and real-scanner integration results.
PR advisories are deduplicated with at most ten UI hints; full advisory details
remain collapsed in the Summary.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) for
development and security guidance.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE)
and [NOTICE](NOTICE).
