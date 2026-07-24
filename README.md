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
| Commit Identity | Commit Author、Committer、邮箱和消息中的禁止身份字段 |
| File Integrity | 危险链接、异常路径、UTF-8、乱码和大文件 |
| Workflow Integrity | Python/YAML 明确语法错误和未固定 SHA 的 Actions 引用 |
| License Compliance | 法律文件、原版权声明、新增源码和第三方来源 |
| Secret Detection | Gitleaks 扫描 PR 引入的 Commit，并过滤确定性示例占位符 |
| Code Security | 离线 Semgrep 规则，仅对 PR 适用源码及变更行报告 |
| Code Quality | Ruff、ShellCheck、actionlint、yamllint 和 Lizard |
| Dependency Security | 依赖清单变化时比较 Trivy base/head 结果 |
| Quality Gate Result | 汇总前述检查并提供唯一的分支保护检查项 |

## Use from another repository / 业务仓库接入

Copy [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
to `.github/workflows/quality-gate.yml`, update the target branches, and replace
`QUALITY_GATE_FULL_COMMIT_SHA` with a reviewed 40-character Commit SHA:

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@QUALITY_GATE_FULL_COMMIT_SHA
    permissions:
      contents: read
```

The required branch-protection check is:

```text
Checks / Quality Gate Result
```

Do not use a branch name or a movable tag for a production gate. Business
repositories should upgrade the pinned SHA through a reviewed pull request.

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
`OWNER_REPOSITORY.yaml`, set its expected license and legal/third-party paths,
then run the self-tests before release.

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
