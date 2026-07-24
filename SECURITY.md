# Security Policy

## Supported versions

Security fixes are applied to the latest released minor version and the
current `main` branch.

## Reporting a vulnerability

请使用 GitHub 仓库的 **Security > Report a vulnerability** 私密报告入口提交安全
问题。请勿在公开 Issue、Pull Request、日志或扫描报告中提交真实凭据、可直接利用
的攻击载荷或内部环境信息。

报告应包括：

- 受影响版本或完整 Commit SHA；
- 影响范围和复现前提；
- 已完成脱敏的最小复现步骤；
- 建议的缓解或修复方式（如有）。

维护者完成初步确认前，请不要公开披露问题细节。

## Self-hosted runners

Public-fork pull requests must not reach a persistent trusted runner without
the repository owner's explicit approval. Use an isolated, disposable or
equivalently hardened runner with no production credentials.
