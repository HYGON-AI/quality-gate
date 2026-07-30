# HYGON Quality Gate

HYGON Quality Gate is a reusable GitHub Actions workflow for incremental pull
request checks. It evaluates only the commits, files, and changed lines
introduced by a pull request.

HYGON Quality Gate 是面向 Pull Request 的增量质量、安全与开源合规门禁，仅检查
本次 PR 引入的 Commit、文件及变更行。

## Scope / 公开范围

This repository contains only:

- the reusable PR workflow;
- incremental gate rules and repository profiles;
- the minimum Python implementation used by the workflow;
- native and scanner-output tests.

Whole-repository audit engines, audit skills, remediation reports, target
repository source, credentials, caches, and runner data are intentionally not
included.

本仓库不包含全仓开源合规审计 Skill、全仓质量安全审计 Skill、历史重写 Skill、
目标仓库源码、扫描报告、凭据或 Runner 运行数据。

## Checks / 检查项

| Job | Purpose / 用途 |
| --- | --- |
| Profile Admission | 在启动扫描前校验中央仓库 Profile；未登记时其余扫描不启动 |
| Governance & Compliance | Commit 身份字段、法律文件、原版权声明、模式化来源，以及 PR 新增 DCU 和 HCU 运行时 AMD/XGMI 可见文本检查 |
| Repository Integrity & Quality | 危险 Git 对象、编码、语法、Ruff、ShellCheck、actionlint、yamllint 和 Lizard |
| Security | Gitleaks 硬阻断真实密钥；离线 Semgrep 发现作为提示项 |
| Dependency Security | 依赖清单变化时比较 Trivy base/head 结果 |
| Quality Gate Result | 汇总前述检查并提供唯一的分支保护检查项 |

目标仓库中未固定到完整 Commit SHA 的 Action 和 reusable workflow 引用会被
报告为提示项，不阻断合并。

## Use from another repository / 业务仓库接入

Copy [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
to `.github/workflows/quality-gate.yml`, update the target branches, and replace
`QUALITY_GATE_REF` with a reviewed release tag or Commit SHA:

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@QUALITY_GATE_REF
    permissions:
      contents: read
```

The required branch-protection check is:

```text
Checks / Quality Gate Result
```

A full Commit SHA provides stronger immutability, but it is recommended rather
than required. A reviewed release tag may be used when centralized version
upgrades are preferred.

## Version consistency / 版本一致性

The reusable workflow checks out its engine from `job.workflow_repository` at
`job.workflow_sha`. Therefore, the workflow, policies, and engine always come
from the same Commit selected by the caller; there is no second embedded engine
SHA to update.

## Runner requirements / Runner 要求

The default runner labels are:

```json
["self-hosted", "linux", "x64", "quality"]
```

The runner must provide:

- Git, Docker, Python 3.9+ and PyYAML;
- the scanner images pinned in
  [`policies/quality-security/hygon-quality-security-v1.1.yaml`](policies/quality-security/hygon-quality-security-v1.1.yaml);
- a pre-populated offline Trivy cache;
- an isolated, disposable or equivalently hardened execution environment.

Configure the organization or repository Actions variable
`HYGON_TRIVY_CACHE` with the absolute path of the offline Trivy cache. The gate
uses read-only source mounts, `--network=none`, dropped Linux capabilities, and
`no-new-privileges` for scanner containers.

For a public repository, review GitHub's fork-workflow approval settings before
allowing untrusted pull requests to use self-hosted runners.

## Register a repository / 登记仓库

Every caller must have a reviewed profile in
[`policies/repository-profiles`](policies/repository-profiles). Add
`OWNER_REPOSITORY.yaml`, select `original`, `fork`, `submodule-patch`, or
`overlay` mode, set its expected license and reviewed ownership paths, then run
the self-tests before release. A missing or invalid profile fails only
`Profile Admission`; the four scan groups do not start.

Repositories that enable `checks.sensitive_diff` or
`checks.hcu_runtime_wording` must also declare reviewed HCU-owned paths and
precise external-contract exceptions under `sensitive_diff`. Exceptions are
limited to verified identifiers, regular expressions, URLs, or content
patterns; malformed configuration is rejected by `Profile Admission`.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
python3 -m compileall -q src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
