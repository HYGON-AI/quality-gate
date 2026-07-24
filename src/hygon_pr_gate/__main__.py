# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Module entry point for the PR gate."""

from .audit_pr import main


if __name__ == "__main__":
    raise SystemExit(main())
