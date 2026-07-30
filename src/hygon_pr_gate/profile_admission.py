#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Validate a caller repository profile before starting PR scans."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .policy import load_policy


def render_admission(
    *,
    repository: str,
    summary: Path,
    policy_root: Path,
) -> int:
    lines = [
        "# Profile Admission / 仓库准入",
        "",
        "- Repository / 仓库：`{}`".format(repository),
    ]
    try:
        policy = load_policy(policy_root.resolve(), repository)
        profile = policy["profile"]
    except Exception as error:
        lines.extend(
            [
                "- Status / 状态：❌ Invalid / 无效",
                "",
                "## Required Change / 必须修改",
                "",
                "- 中央 `policies/repository-profiles` 中缺少有效且经过审核的仓库 Profile，"
                "或 Profile 与中央策略不一致。",
                "- Error / 错误：`{}: {}`".format(
                    type(error).__name__,
                    str(error).replace("`", "'").replace("\n", " ")[:800],
                ),
                "- 其他扫描 Job 未启动，避免将同一配置错误重复报告为多个扫描失败。",
                "",
            ]
        )
        result = 1
    else:
        lines.extend(
            [
                "- Status / 状态：✅ Admitted / 已准入",
                "- Repository Mode / 仓库模式：`{}`".format(
                    profile["repository_mode"]
                ),
                "- Policy / 策略：`{}`".format(profile["policy"]),
                "- License / 主许可证：`{}`".format(profile["license"]),
                "",
                "Profile 已通过中央准入校验，可以启动增量扫描。",
                "",
            ]
        )
        result = 0
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(lines), encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hygon-profile-admission")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--policy-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return render_admission(
        repository=args.repository,
        summary=args.summary.resolve(),
        policy_root=args.policy_root,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
