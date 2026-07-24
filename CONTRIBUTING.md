# Contributing

感谢参与 HYGON Quality Gate。

## Development

1. 从最新 `main` 创建独立分支。
2. 使用 Python 3.9 或更高版本创建虚拟环境。
3. 安装项目依赖并运行全部自测试。
4. 提交 Pull Request，不直接向受保护分支推送。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .

PYTHONPATH=src .venv/bin/python tests/pr_gate_self_test.py
python3 -m compileall -q src tests
```

## Commit requirements

- Author、Committer 和 Commit message 不得包含不符合当前开源主体要求的身份字段。
- 不得提交 Token、密码、私钥、真实凭据、目标仓库源码、原始扫描结果或运行缓存。
- GitHub Actions 和第三方依赖必须固定到可审计版本或完整 Commit SHA。
- 新增或修改源码应保留原始权利人声明，并使用适用的 SPDX 标识。
- 不得把全仓审计 Skill、目标仓库源码、扫描报告或 Runner 数据迁入本仓库。

推荐 Commit message：

```text
<type>: <summary>
```

常用 `type`：`feat`、`fix`、`ci`、`docs`、`test`、`refactor`、`chore`。

## License

除非另有明确说明，提交到本项目的贡献依据 Apache License 2.0 提供。
