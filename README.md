# HYGON Quality Gate

HYGON Quality Gate is a reusable GitHub Actions workflow for incremental pull
request checks. It evaluates only the commits, files, and changed lines
introduced by a pull request.

HYGON Quality Gate 是面向 Pull Request 的增量质量、安全与开源合规门禁，仅检查
本次 PR 引入的 Commit、文件及变更行。

## Scope / 公开范围

This repository contains only:

- the reusable PR workflow;
- one universal, centrally reviewed incremental gate policy;
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
| Identity, license & wording | Commit 身份字段、法律文件和原版权声明保护，以及 PR 新增 DCU 和 HCU 运行时 AMD/XGMI 可见文本检查 |
| Repository & code quality | 危险 Git 对象、编码、语法、Ruff、ShellCheck、actionlint、yamllint 和 Lizard |
| Secrets & SAST | Gitleaks 硬阻断真实密钥；离线 Semgrep 发现作为提示项 |
| Dependency vulnerabilities | 依赖清单变化时比较 Trivy base/head 结果 |
| All required checks | 汇总前述检查并提供唯一的分支保护检查项 |

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
Checks / All required checks
```

Each scan group writes the complete report to both the expanded job log and
the GitHub Job Summary. Blockers and advisories are also emitted as escaped
file/line annotations, so developers can locate findings without leaving the
job page.

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

All pinned scanner images must be preloaded during runner provisioning. The PR
workflow never pulls images from the network. If an image is missing or its
digest does not match the policy, the affected check returns `Invalid Scan`
instead of silently passing. Validate the runner after provisioning with
`docker image inspect` against every reference under the policy `images` map.

所有固定版本扫描镜像必须在 Runner 初始化阶段预装。PR 执行期间不会联网拉取镜像；
镜像缺失或摘要不匹配时，相应检查会明确返回“扫描无效”，不会按通过处理。Runner
交付或清理后，应逐项使用 `docker image inspect` 核对策略 `images` 中的镜像引用。

Configure the organization or repository Actions variable
`HYGON_TRIVY_CACHE` with the absolute path of the offline Trivy cache. The gate
uses read-only source mounts, `--network=none`, dropped Linux capabilities, and
`no-new-privileges` for scanner containers.

For a public repository, review GitHub's fork-workflow approval settings before
allowing untrusted pull requests to use self-hosted runners.

## Universal policy and full audits / 通用策略与全仓审计

Any repository with a valid `OWNER/REPOSITORY` name can call the same reviewed
workflow version; callers do not need a repository-specific profile. The PR
gate blocks only high-confidence incremental problems such as real secrets,
forbidden identities, definite syntax errors, legal-file or original-header
damage, unsupported SPDX additions, and confirmed sensitive runtime wording.

任意公开或私有仓库均可直接调用同一固定版本，无需逐仓登记 Profile。新增源码的原创、
上游、第三方或生成物归属无法仅凭 PR 差异可靠判断，因此只提示开发复核，不在通用门禁中
机械添加或强制指定许可证文件头。

Repository mode, upstream provenance, third-party registration, complete
license obligations, whole-tree file headers, historical metadata, and full
quality/security coverage remain part of periodic whole-repository audits.
Precise central exceptions for protected external contracts are reviewed in
the universal policy and must not be supplied by an untrusted caller.

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
