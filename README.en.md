# HYGON Quality Gate

HYGON Quality Gate is a reusable GitHub Actions workflow for incremental pull
request quality, security, and open-source compliance checks. It evaluates only
the commits, files, and changed lines introduced by a pull request.

[中文文档](README.md)

## Quick start

1. Copy [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
   to `.github/workflows/quality-gate.yml` in the target repository.
2. Update `pull_request.branches` for the target repository.
3. Replace `QUALITY_GATE_REF` with a reviewed release tag or full Commit SHA.

The following example uses the current stable release
[`v2.0.2`](https://github.com/HYGON-AI/quality-gate/releases/tag/v2.0.2):

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@v2.0.2
    permissions:
      contents: read
```

A full Commit SHA provides stronger immutability and is suitable for
repositories that require strict version pinning. A reviewed release tag may
be used when centralized upgrades are preferred.

Configure the following Required Check in the target repository's branch
protection settings or Ruleset:

```text
Checks / All required checks
```

## Checks

| Job | Purpose |
| --- | --- |
| Identity, license & wording | Checks Commit identity fields, LICENSE/NOTICE/COPYING files, original copyright notices, `THIRD_PARTY_NOTICES.md` changes, and organization or platform wording in newly added content |
| Repository & code quality | Checks dangerous Git objects, encoding, and syntax, and runs Ruff, ShellCheck, actionlint, yamllint, and Lizard |
| Secrets & SAST | Uses Gitleaks to block real secrets; offline Semgrep findings are advisory |
| Dependency vulnerabilities | Compares Trivy base/head results when dependency manifests change |
| All required checks | Aggregates the preceding jobs and provides the single branch-protection check |

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
incremental problems, including real secrets, forbidden identity fields,
definite syntax errors, legal-file or original-header damage, unsupported SPDX
additions, and confirmed sensitive runtime wording.

Whole-repository open-source compliance audit skills, quality and security
audit skills, history-rewrite skills, remediation reports, target repository
source, credentials, caches, and runner data are intentionally excluded.

Repository mode, upstream provenance, third-party registration, complete
license obligations, whole-tree file headers, historical metadata, and full
quality/security coverage remain part of periodic whole-repository audits.
Precise exceptions for protected external contracts must be centrally reviewed
in the universal policy and must not be supplied by an untrusted caller.

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
- a pre-populated offline Trivy cache;
- an isolated, disposable, or equivalently hardened execution environment.

All scanner images must be preloaded during runner provisioning. The PR
workflow never pulls images from the network. If an image is missing or its
digest does not match the policy, the affected check returns `Invalid Scan`
instead of silently passing. After provisioning or cleanup, validate each
reference in the policy's `images` map with `docker image inspect`.

Configure the organization or repository Actions Variable `HYGON_TRIVY_CACHE`
with the absolute path of the offline Trivy cache. Scanner containers use
read-only source mounts, `--network=none`, dropped Linux capabilities, and
`no-new-privileges`.

Before allowing untrusted pull requests in a public repository to use
self-hosted runners, review GitHub's Fork Workflow approval settings.

## Local development and validation

The following commands target a Linux environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
python3 -m compileall -q src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) for
development and security guidance.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE)
and [NOTICE](NOTICE).
