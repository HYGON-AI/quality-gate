# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Load immutable PR policy and repository profiles from the central repository."""

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml


REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REPOSITORY_MODES = {"original", "fork", "submodule-patch", "overlay"}
PROFILE_PATH_LISTS = {
    "legal_files",
    "third_party_registries",
    "third_party_paths",
    "generated_paths",
    "hygon_owned_paths",
    "upstream_paths",
    "patch_paths",
}


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError("required policy file does not exist: {}".format(path))
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("policy root must be a mapping: {}".format(path))
    return value


def _profile_name(repository: str) -> str:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must use OWNER/REPOSITORY format")
    return repository.replace("/", "_") + ".yaml"


def load_policy(policy_root: Path, repository: str) -> Dict[str, Any]:
    profile = load_yaml(policy_root / "repository-profiles" / _profile_name(repository))
    if int(profile.get("schema_version", 0)) != 1:
        raise ValueError("repository profile schema_version must be 1")
    if profile.get("repository") != repository:
        raise ValueError("repository profile does not match caller repository")
    repository_mode = str(profile.get("repository_mode") or "")
    if repository_mode not in REPOSITORY_MODES:
        raise ValueError(
            "repository profile repository_mode must be one of: {}".format(
                ", ".join(sorted(REPOSITORY_MODES))
            )
        )
    for field in sorted(PROFILE_PATH_LISTS):
        values = profile.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise ValueError(
                "repository profile {} must be a list of non-empty paths".format(
                    field
                )
            )
    policy_id = str(profile.get("policy") or "")
    pr_policy = load_yaml(policy_root / "pr" / "{}.yaml".format(policy_id))
    if pr_policy.get("policy_id") != policy_id:
        raise ValueError("PR policy ID does not match filename")
    if pr_policy.get("scope", {}).get("block_new_findings_only") is not True:
        raise ValueError("PR policy must block newly introduced findings only")
    quality_id = str(pr_policy.get("quality_security_policy") or "")
    quality = load_yaml(policy_root / "quality-security" / "{}.yaml".format(quality_id))
    open_source_id = str(pr_policy.get("open_source_policy") or "")
    open_source = load_yaml(policy_root / "base" / "{}.yaml".format(open_source_id))
    brand_id = str(open_source.get("brand_identity", {}).get("ruleset") or "")
    brand = load_yaml(policy_root / "brand" / "{}.yaml".format(brand_id))
    allowed = {"MIT", "BSD-3-Clause", "Apache-2.0"}
    if set(open_source.get("allowed_licenses", [])) != allowed:
        raise ValueError("open-source policy allowed-license set is invalid")
    admission = open_source.get("license_admission")
    if admission is not None:
        if not isinstance(admission, dict):
            raise ValueError("open-source license_admission must be a mapping")
        if set(admission.get("approved", [])) != allowed:
            raise ValueError(
                "open-source license_admission approved set is invalid"
            )
        if admission.get("legal_review") != ["*"]:
            raise ValueError(
                "open-source license_admission must route other licenses to legal review"
            )
    if profile.get("license") not in allowed:
        raise ValueError("repository profile license is not automatically allowed")
    checks = profile.get("checks") or {}
    for required in ("security", "quality", "compliance", "commit_identity"):
        if checks.get(required) is not True:
            raise ValueError("repository profile may not disable required check: {}".format(required))
    result = deepcopy(pr_policy)
    result["profile"] = profile
    result["quality_security"] = quality
    result["open_source"] = open_source
    result["brand_identity"] = brand
    return result
