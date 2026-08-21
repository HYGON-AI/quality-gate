# HYGON Quality Gate

HYGON Quality Gate 是面向 Pull Request（PR）的增量质量、安全与开源合规门禁，
仅检查本次 PR 引入的提交、文件及变更行。

[English documentation](README.en.md)

## 快速接入

1. 将 [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
   复制到目标仓库的 `.github/workflows/quality-gate.yml`。
2. 根据目标仓库实际情况调整 `pull_request.branches`。
3. 将 `QUALITY_GATE_REF` 替换为已审核的发布 Tag 或完整 Commit SHA。

以下示例使用当前稳定版本 [`v2.0.2`](https://github.com/HYGON-AI/quality-gate/releases/tag/v2.0.2)：

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@v2.0.2
    permissions:
      contents: read
```

完整 Commit SHA 具有更强的不可变性，适合需要严格固定版本的仓库；如需集中升级，
也可以使用经过审核的发布 Tag。

在目标仓库的分支保护或 Ruleset 中，将以下检查设置为 Required Check：

```text
Checks / All required checks
```

## 检查项

| Job | 用途 |
| --- | --- |
| Identity, license & wording | 检查 Commit 身份字段、LICENSE/NOTICE/COPYING、原版权声明、`THIRD_PARTY_NOTICES.md` 变更，以及新增内容中的组织与平台表述 |
| Repository & code quality | 检查危险 Git 对象、编码和语法，并运行 Ruff、ShellCheck、actionlint、yamllint 和 Lizard |
| Secrets & SAST | 使用 Gitleaks 硬阻断真实密钥；离线 Semgrep 发现作为提示项 |
| Dependency vulnerabilities | 依赖清单变化时比较 Trivy base/head 扫描结果 |
| All required checks | 汇总前述检查，并作为唯一的分支保护检查项 |

目标仓库中未固定到完整 Commit SHA 的 Action 和 reusable workflow 引用会被报告为
提示项，但不会阻断合并。

每个检查组都会将完整报告写入 Job 日志和 GitHub Job Summary。阻断项和提示项还会
生成经过转义的文件/行注解，开发人员可以直接在 Actions 页面定位问题。

## 门禁范围

本仓库仅包含：

- 可复用的 PR Workflow；
- 一套统一且集中审核的增量门禁策略；
- Workflow 运行所需的最小 Python 实现；
- 原生测试和扫描器输出测试。

任意公开或私有仓库均可调用同一已审核版本，无需逐仓登记 Profile。PR 门禁只阻断
高置信度的增量问题，例如真实密钥、不合规身份字段、确定的语法错误、许可证文件或
原版权声明破坏、不受支持的 SPDX 新增，以及确认存在问题的敏感运行时表述。

本仓库不包含全仓开源合规审计 Skill、全仓质量安全审计 Skill、历史重写 Skill、
整改报告、目标仓库源码、凭据、缓存或 Runner 运行数据。

仓库模式、上游来源、第三方登记、完整许可证义务、全仓文件头、历史元数据以及全量
质量和安全覆盖，仍由周期性全仓审计负责。受保护外部契约的精确例外必须在统一策略中
集中审核，不能由不受信任的调用方传入。

## 版本一致性

可复用 Workflow 使用 `job.workflow_repository` 和 `job.workflow_sha` 检出门禁引擎。
因此，Workflow、策略和引擎始终来自调用方选定的同一 Commit，不需要维护第二个内嵌的
引擎 SHA。

## Runner 要求

默认 Runner 标签为：

```json
["self-hosted", "linux", "x64", "quality"]
```

Runner 必须提供：

- Git、Docker、Python 3.9+ 和 PyYAML；
- 策略文件
  [`policies/quality-security/hygon-quality-security-v1.1.yaml`](policies/quality-security/hygon-quality-security-v1.1.yaml)
  中固定版本的扫描镜像；
- 预先填充的离线 Trivy 缓存；
- 隔离、可销毁或具备等效加固措施的执行环境。

所有扫描镜像必须在 Runner 初始化阶段预装。PR 执行期间不会联网拉取镜像；镜像缺失
或摘要不匹配时，相应检查会返回 `Invalid Scan`，不会静默通过。Runner 交付或清理后，
应逐项使用 `docker image inspect` 核对策略 `images` 中的镜像引用。

请通过组织级或仓库级 Actions Variable `HYGON_TRIVY_CACHE` 配置离线 Trivy 缓存的
绝对路径。扫描容器使用只读源码挂载、`--network=none`、移除 Linux capabilities 和
`no-new-privileges` 等限制。

公开仓库允许不受信任的 PR 使用自建 Runner 前，必须审查 GitHub 的 Fork Workflow
审批设置。

## 本地开发与验证

以下命令适用于 Linux 环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
python3 -m compileall -q src tests
```

开发和安全说明请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[SECURITY.md](SECURITY.md)。

## License

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
