# HYGON Quality Gate

## 通用增量检查范围

当前门禁不再提供密钥泄露检测，无需安装或预装 Gitleaks 镜像。其余六个外部工具继续使用。

- 新增文件检查全部文本，已有文件检查新增行。AMD/XGMI 可见输出按大小写不敏感的子串匹配，不要求 HCU 路径或标记，不排除测试和文档目录。
- DCU 内容检查不再按文件后缀筛选，也不因 `docs/internal/` 路径降级；移除了旧策略中项目专用的标识符豁免。
- PNG/JPEG/GIF 图片载荷及 Notebook 的 `image/*` 值不参与敏感字段检查，路径仍检查。ELF（包括 `.so`、`.o` 和可执行文件）、LLVM bitcode、静态库归档、Mach-O 按内容识别并跳过源码文本和敏感输出检查，在现有检查说明中列出文件及跳过原因；文件路径、大小、链接仍检查。其他不可解析二进制、读取失败、文本超过读取上限和解析失败会列出具体原因并返回扫描无效。
- Semgrep 报告解析失败或必需工具未生成报告时，不能按通过处理。
- Python 输出检查支持直接和转义字符串、简单变量赋值、字符串加法、简单 `.format()` 和 f-string 固定文字。仅赋值或字典字段不视为输出；`print(len("amd"))` 不因内部字符串误报。仍不能追踪任意变量、跨函数返回值或所有动态拼接，通过不代表已验证全部运行时输出。
- 外部扫描前要求检出版本与指定 head 一致且工作区干净（包括未跟踪文件）。单个文件失败时保留同项检查中已发现的问题并继续检查其他文件；后续工具失败时保留此前工具发现的问题，并同时展示阻断和失败原因。
- 仅删除行不会把旧行的问题算作本次新增；`--native-only` 无阻断时显示“内置预检通过，完整门禁未执行”。
- 工作流的 `target` 和容器的 `/repo` 是由门禁统一创建的工作目录，不要求调用方仓库具有相同的宿主机路径。


HYGON Quality Gate 是面向 Pull Request（PR）的增量质量、安全与开源合规门禁，
仅检查本次 PR 引入的提交、文件及变更行。

[English documentation](README.en.md)

## 快速接入

1. 将 [`examples/workflows/quality-gate.yml`](examples/workflows/quality-gate.yml)
   复制到目标仓库的 `.github/workflows/quality-gate.yml`。
2. 根据目标仓库实际情况调整 `pull_request.branches`。
3. 将 `QUALITY_GATE_REF` 替换为已审核的发布 Tag 或完整 Commit SHA。

以下示例使用当前稳定版本 [`v2.0.3`](https://github.com/HYGON-AI/quality-gate/releases/tag/v2.0.3)：

```yaml
jobs:
  checks:
    name: Checks
    uses: HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml@v2.0.3
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

| Job | 检查内容 |
| --- | --- |
| Identity, license & wording | <ol><li>Commit 作者、提交者、邮箱及提交信息</li><li>LICENSE/NOTICE/COPYING、原版权声明和 SPDX 标识</li><li><code>THIRD_PARTY_NOTICES.md</code> 变更</li><li>新增内容中的组织与平台表述</li></ol> |
| Repository & code quality | <ol><li>危险符号链接、异常路径、Git Blob 和大文件</li><li>UTF-8 编码、控制字符和换行格式</li><li>Python/YAML 语法及 Workflow 引用</li><li>Ruff Python Lint</li><li>ShellCheck Shell Lint</li><li>actionlint GitHub Actions Lint</li><li>yamllint YAML Lint</li><li>Lizard 代码复杂度分析</li></ol> |
| Code Security | <ol><li>Semgrep 静态应用安全测试，当前作为提示项</li></ol> |
| All required checks | <ol><li>汇总前述检查结果</li><li>生成统一的分支保护检查项和 Job Summary</li></ol> |

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
高置信度的增量问题，例如不合规身份字段、确定的语法错误、许可证文件或
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
- 隔离、可销毁或具备等效加固措施的执行环境。

所有扫描镜像必须在 Runner 初始化阶段预装。PR 执行期间不会联网拉取镜像；镜像缺失
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
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
python3 -m compileall -q src tests
```

真实工具集成验证需要 Docker 权限，并提前准备策略中固定的三个镜像；验证会创建临时 Git 仓库，不运行目标代码、不联网拉取镜像。报告目录应放在仓库外：

```bash
PYTHONPATH=src .venv/bin/python tests/real_tools_integration.py --output /tmp/quality-gate-integration
```

覆盖六个真实工具、正常通过、敏感输出阻断、已有告警与新增告警的区分，以及解析失败时保留已有发现。Semgrep 安全规则、ShellCheck 警告和复杂度在当前策略中作为提示，不能将“工具已执行”理解成“所有告警都阻断”。

开发和安全说明请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[SECURITY.md](SECURITY.md)。

## License

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
