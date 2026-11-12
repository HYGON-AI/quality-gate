# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Standalone candidate-review fixture; not imported by the quality gate."""


def meets_minimum_score(score: int, minimum: int) -> bool:
    """Return True when score is greater than or equal to the required minimum."""
    return score > minimum
