#!/usr/bin/env bash
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

phase="检查门禁目录和 Python"
fail() {
  local message="质量门禁启动失败：${phase}。$1"
  echo "::error::$message" >&2
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '\n%s\n' "$message" >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 1
}
trap 'fail "请查看本步骤上方的具体错误；源码扫描尚未开始。"' ERR

: "${GITHUB_ACTION_PATH:?缺少 GITHUB_ACTION_PATH}"
: "${RUNNER_TEMP:?缺少 RUNNER_TEMP}"
: "${GITHUB_OUTPUT:?缺少 GITHUB_OUTPUT}"
[[ -f "$GITHUB_ACTION_PATH/pyproject.toml" && -d "$GITHUB_ACTION_PATH/src/hygon_pr_gate" && -d "$GITHUB_ACTION_PATH/policies" ]] || fail "门禁检出不完整。"
[[ -n "${GATE_BOOTSTRAP_UV:-}" && -x "$GATE_BOOTSTRAP_UV" ]] || fail "setup-uv 未提供可执行的 uv，请检查环境准备步骤。"

phase="创建临时目录"
gate_env=$(mktemp -d "$RUNNER_TEMP/quality-gate-python.XXXXXXXX")
export UV_PYTHON_INSTALL_DIR="$gate_env/python"
export UV_CACHE_DIR="$gate_env/cache"
export UV_PYTHON_DOWNLOADS=automatic
export UV_HTTP_TIMEOUT=30
export UV_HTTP_RETRIES=2
# Do not discover target repository configuration or host/user Python packages.
cd "$gate_env"
phase="下载并准备 Python 3.11；请检查访问 GitHub Python 下载地址的网络、磁盘空间和目录写权限"
"$GATE_BOOTSTRAP_UV" --no-config venv --managed-python --python 3.11 "$gate_env/venv"
gate_python="$gate_env/venv/bin/python"

phase="安装 PyYAML 6.0.3；请确认 Runner 能访问 pypi.org 和 files.pythonhosted.org，或已配置网络代理"
"$GATE_BOOTSTRAP_UV" --no-config pip install --python "$gate_python" \
  --default-index https://pypi.org/simple --only-binary=:all: --no-deps 'PyYAML==6.0.3'

phase="验证 Python 和 PyYAML"
"$gate_python" -I -c 'import sys, yaml; print("门禁 Python：", sys.executable); print("PyYAML：", yaml.__version__)'
printf 'gate-path=%s\npython-path=%s\n' "$GITHUB_ACTION_PATH" "$gate_python" >> "$GITHUB_OUTPUT"
echo "质量门禁 Python 环境已就绪。"
