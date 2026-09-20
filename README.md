# HYGON Quality Gate

HYGON Quality Gate 是面向 Pull Request（PR）的增量质量、安全与开源合规门禁，
仅检查本次 PR 引入的提交、文件及变更行。

[English documentation](README.en.md)

本文描述 `v2.0.5`。固定版本标签保持不变，`stable` 是集中升级的滚动入口。

## 快速接入

1. 将 [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
   复制到目标仓库的 `.github/workflows/quality-gate.yml`。
2. 根据目标仓库实际情况调整 `pull_request.branches`。
3. 将 `QUALITY_GATE_REF` 替换为已审核的发布 Tag 或完整 Commit SHA。

以下示例使用固定版本 [`v2.0.5`](https://github.com/HYGON-AI/quality-gate/releases/tag/v2.0.5)：

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@v2.0.5
    permissions:
      contents: read
```

完整 Commit SHA 具有更强的不可变性，适合需要严格固定版本的仓库；如需集中升级，
也可以使用经过审核的发布 Tag。

已采用集中升级的仓库继续使用 `@stable`，无需每次修改调用文件。Runner Group 的
Selected workflows 必须允许对应引用，例如
`HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@refs/tags/stable`。

在目标仓库的分支保护或 Ruleset 中，将以下检查设置为 Required Check：

```text
Checks / All required checks
```

## 检查项

| Job | 检查内容 |
| --- | --- |
| Identity, license & wording | <ol><li>Commit 作者、提交者、邮箱及提交信息</li><li>LICENSE/NOTICE/COPYING、原版权声明和 SPDX 标识</li><li><code>THIRD_PARTY_NOTICES.md</code> 变更</li><li>新增内容中的组织与平台表述</li></ol> |
| Repository & code quality | <ol><li>危险符号链接、异常路径、Git Blob 和大文件</li><li>UTF-8 编码、控制字符和换行格式</li><li>Python/YAML 语法及 Workflow 引用</li><li>Ruff Python Lint</li><li>ShellCheck Shell Lint</li><li>actionlint GitHub Actions Lint</li><li>yamllint YAML Lint</li><li>Lizard 代码复杂度分析</li></ol> |
| Secrets & SAST | <ol><li>Gitleaks 密钥泄露检测，仅提示且脱敏，不因命中阻断</li><li>Semgrep 静态应用安全测试，当前作为提示项</li></ol> |
| All required checks | <ol><li>汇总前述检查结果</li><li>生成统一的分支保护检查项和 Job Summary</li></ol> |

目标仓库中未固定到完整 Commit SHA 的 Action 和 reusable workflow 引用会被报告为
提示项，但不会阻断合并。

每个检查组都会将完整报告写入 Job 日志和 GitHub Job Summary。阻断项和提示项还会
生成经过转义的文件/行注解。页面提示按同文件同规则聚合，最多展示十条提示；
详细提示折叠保留在 Summary，减少重复告警。

## 门禁范围

本仓库仅包含：

- 可复用的 PR Workflow；
- 一套统一且集中审核的增量门禁策略；
- Workflow 运行所需的最小 Python 实现；
- 原生测试和扫描器输出测试。

任意公开或私有仓库均可调用同一已审核版本，无需逐仓登记 Profile。PR 门禁只阻断
高置信度的增量问题，例如不合规身份字段、确定的语法错误、许可证文件或
原版权声明破坏、不受支持的 SPDX 新增。密钥及 DCU/AMD/XGMI 词法命中仅提示，
不得据此机械修改上游版权、真实后端和 API/ABI 名称。

普通 YAML 支持多文档和自定义标签的语法检查，不执行对象构造；明确语法错误、
重复键仍阻断，Actions Workflow 必须为单文档映射。已识别的 Helm 模板提示需渲染
验证，不宣称模板已通过。仅改注释且其余内容完全不变的已有语法问题降为提示；
这不等于完整的基线语义差分，也不能保证识别所有模板或语言版本。

扫描器失败、镜像或报告缺失仍是 `Invalid Scan`，与源码违规分开说明，不能静默通过。

### 文件头检查边界

- 原版权/SPDX 声明允许空白、换行和常见注释包装变化；权利人、年份和声明内容不能删除或替换。
- 完整标准 MIT、BSD-3-Clause 正文和 Apache-2.0 标准声明头可在没有 SPDX 时识别；
  原正文的授权条件、免责声明被删除或改写仍阻断，新增 SPDX 不能替代原正文。
- 仅有许可证名称、残缺正文或无法识别的变体，不被推断成已准入许可证。
  来源不明、缺少声明的新增源码仅提示；含 HYGON 声明但既无 SPDX 又无可完整识别许可证的新增源码仍阻断。
- 不要求所有上游代码添加 HYGON Copyright，不自动修改文件，不自动判断 H1/H2/H3 或原创归属。
- 识别仍受策略文件头扫描行数限制；这不是任意许可证全文识别或法律适用性证明。

摘要保留现有四个 Job 名称，默认展示结论、阻断/提示计数及实际版本和 SHA；
扫描详情折叠，无适用文件显示“无需检查”。门禁通过不代表已经满足全部仓库合并规则。

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

- Git、Docker、Bash 和兼容工作流所用 Action 的 Runner；
- Python 3.9+、可写临时目录及 PyYAML；
- 策略文件
  [`policies/quality-security/hygon-quality-security-v1.1.yaml`](policies/quality-security/hygon-quality-security-v1.1.yaml)
  中固定版本的扫描镜像；
- 隔离、可销毁或具备等效加固措施的执行环境。

优先复用已有 Python 和 PyYAML；缺少 PyYAML 时在 `RUNNER_TEMP` 创建独立 venv，
安装 `PyYAML==6.0.3`。此时需要 venv/ensurepip 和 PyPI 网络访问；不会自动下载
Python，也不修改系统环境。预装 PyYAML 可避免这一步联网。

所有扫描镜像（包括 Gitleaks）必须在 Runner 初始化阶段预装。PR 执行期间不会联网拉取镜像；镜像缺失
或摘要不匹配时，相应检查会返回 `Invalid Scan`，不会静默通过。Runner 交付或清理后，
应逐项使用 `docker image inspect` 核对策略 `images` 中的镜像引用。

公开仓库允许不受信任的 PR 使用自建 Runner 前，必须审查 GitHub 的 Fork Workflow
审批设置。

## 本地开发与验证

以下命令适用于 Linux 环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python tests/runner_bootstrap_integration.py -v
python3 -m compileall -q src tests
```

预装策略中的四个 Docker 镜像后，再执行真实扫描器集成测试：

```bash
PYTHONPATH=src .venv/bin/python tests/gitleaks_integration.py
PYTHONPATH=src .venv/bin/python tests/real_tools_integration.py --output /tmp/quality-gate-integration
```

测试命令与测试通过是不同的：发布前须确认 Linux 自测、启动环境测试和真实扫描器
集成测试结果；本地单测通过不能替代完整验证。

开发和安全说明请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[SECURITY.md](SECURITY.md)。

## License

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
