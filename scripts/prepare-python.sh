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
# Probe outside the target checkout; ignore injected PYTHONPATH/PYTHONHOME.
cd "$RUNNER_TEMP"
candidates=()
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  candidates+=("$VIRTUAL_ENV/bin/python")
fi
candidates+=(python3 python python3.14 python3.13 python3.12 python3.11 python3.10 python3.9)
gate_python=""
base_python=""
for candidate in "${candidates[@]}"; do
  candidate_path=$(command -v "$candidate" 2>/dev/null) || continue
  if ! "$candidate_path" -E -c 'import sys; print("检测 Python：", sys.executable, sys.version.split()[0]); raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "跳过不满足 Python 3.9+ 要求的解释器：$candidate_path"
    continue
  fi
  [[ -n "$base_python" ]] || base_python="$candidate_path"
  if "$candidate_path" -E -c 'import yaml; assert callable(yaml.safe_load)' 2>/dev/null; then
    gate_python="$candidate_path"
    break
  fi
  echo "Python 可用但缺少可用 PyYAML：$candidate_path"
done
[[ -n "$base_python" ]] || fail "未找到 Python 3.9+。请为 Runner 服务用户安装并将 python3 加入 PATH，或激活已有虚拟环境；不会自动下载 Python。"

if [[ -z "$gate_python" ]]; then
  phase="创建独立环境；请为 $base_python 补齐 venv/ensurepip 支持并检查临时目录写权限"
  gate_env=$(mktemp -d "$RUNNER_TEMP/quality-gate-python.XXXXXXXX")
  "$base_python" -E -m venv "$gate_env"
  gate_python="$gate_env/bin/python"
  phase="安装 PyYAML 6.0.3；请检查 PyPI 网络或代理，也可由管理员为 Runner 所用 Python 预装 PyYAML"
  "$gate_python" -I -m pip --isolated --disable-pip-version-check install \
    --index-url https://pypi.org/simple --only-binary=:all: --no-deps \
    --retries 2 --timeout 30 'PyYAML==6.0.3'
else
  echo "复用 Runner 已有 Python 和 PyYAML，无需下载或安装。"
fi

phase="验证 Python 和 PyYAML"
"$gate_python" -E -c 'import sys, yaml; print("门禁 Python：", sys.executable); print("PyYAML：", yaml.__version__)'
printf 'gate-path=%s\npython-path=%s\n' "$GITHUB_ACTION_PATH" "$gate_python" >> "$GITHUB_OUTPUT"
echo "质量门禁 Python 环境已就绪。"
