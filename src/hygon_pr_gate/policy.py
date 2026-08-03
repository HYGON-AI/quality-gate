# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Load the universal, repository-independent incremental PR policy."""

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml


DEFAULT_POLICY_ID = "hygon-pr-gate-v1.2"
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SUPPORTED_LICENSES = {"MIT", "BSD-3-Clause", "Apache-2.0"}
SENSITIVE_LIST_FIELDS = {
    "legacy_dcu": {
        "terms",
        "excluded_paths",
        "advisory_paths",
        "allowed_identifiers",
        "allowed_identifier_patterns",
        "allowed_url_patterns",
        "allowed_content_patterns",
    },
    "hcu_runtime": {
        "terms",
        "hcu_markers",
        "non_hcu_markers",
        "hcu_owned_paths",
        "excluded_paths",
        "allowed_output_patterns",
    },
}
SENSITIVE_REGEX_FIELDS = {
    ("legacy_dcu", "allowed_identifier_patterns"),
    ("legacy_dcu", "allowed_url_patterns"),
    ("legacy_dcu", "allowed_content_patterns"),
    ("hcu_runtime", "allowed_output_patterns"),
}


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError("required policy file does not exist: {}".format(path))
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("policy root must be a mapping: {}".format(path))
    return value


def _mapping(value: Any, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("{} must be a mapping".format(label))
    return value


def _string_list(
    mapping: Dict[str, Any],
    field: str,
    label: str,
    *,
    required: bool = False,
) -> list:
    value = mapping.get(field)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("{} must be a list of non-empty strings".format(label))
    if required and not value:
        raise ValueError("{} must not be empty".format(label))
    return value


def _validate_sensitive_diff(pr_policy: Dict[str, Any]) -> None:
    config = _mapping(pr_policy.get("sensitive_diff"), "PR policy sensitive_diff")
    if config.get("enabled") is not True:
        raise ValueError("universal sensitive-diff policy must be enabled")

    patterns = {}
    for section, fields in SENSITIVE_LIST_FIELDS.items():
        values = _mapping(
            config.get(section),
            "PR policy sensitive_diff.{}".format(section),
        )
        for field in sorted(fields):
            required = (section, field) in {
                ("legacy_dcu", "terms"),
                ("hcu_runtime", "terms"),
                ("hcu_runtime", "hcu_markers"),
            }
            entries = _string_list(
                values,
                field,
                "PR policy sensitive_diff.{}.{}".format(section, field),
                required=required,
            )
            if (section, field) in SENSITIVE_REGEX_FIELDS:
                patterns[(section, field)] = entries

    for (section, field), entries in patterns.items():
        for pattern in entries:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(
                    "sensitive_diff.{}.{} contains invalid regex {!r}: {}".format(
                        section,
                        field,
                        pattern,
                        error,
                    )
                )


def _validate_central_policy(
    pr_policy: Dict[str, Any],
    open_source: Dict[str, Any],
) -> None:
    if pr_policy.get("policy_id") != DEFAULT_POLICY_ID:
        raise ValueError("PR policy ID does not match the universal policy")
    if pr_policy.get("scope", {}).get("block_new_findings_only") is not True:
        raise ValueError("PR policy must block newly introduced findings only")
    if set(open_source.get("allowed_licenses", [])) != SUPPORTED_LICENSES:
        raise ValueError("open-source policy allowed-license set is invalid")
    admission = open_source.get("license_admission")
    if admission is not None:
        if not isinstance(admission, dict):
            raise ValueError("open-source license_admission must be a mapping")
        if set(admission.get("approved", [])) != SUPPORTED_LICENSES:
            raise ValueError(
                "open-source license_admission approved set is invalid"
            )
        if admission.get("legal_review") != ["*"]:
            raise ValueError(
                "open-source license_admission must route other licenses to legal review"
            )
    _validate_sensitive_diff(pr_policy)


def load_policy(policy_root: Path, repository: str) -> Dict[str, Any]:
    """Return one centrally reviewed policy for every valid caller repository.

    Repository-specific provenance, license ownership, and whole-tree
    classification are intentionally left to periodic full-repository audits.
    The PR gate only enforces high-confidence incremental invariants.
    """

    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must use OWNER/REPOSITORY format")

    pr_policy = load_yaml(
        policy_root / "pr" / "{}.yaml".format(DEFAULT_POLICY_ID)
    )
    quality_id = str(pr_policy.get("quality_security_policy") or "")
    quality = load_yaml(
        policy_root / "quality-security" / "{}.yaml".format(quality_id)
    )
    open_source_id = str(pr_policy.get("open_source_policy") or "")
    open_source = load_yaml(
        policy_root / "base" / "{}.yaml".format(open_source_id)
    )
    brand_id = str(
        open_source.get("brand_identity", {}).get("ruleset") or ""
    )
    brand = load_yaml(policy_root / "brand" / "{}.yaml".format(brand_id))
    _validate_central_policy(pr_policy, open_source)

    result = deepcopy(pr_policy)
    result["policy_mode"] = "universal"
    result["quality_security"] = quality
    result["open_source"] = open_source
    result["brand_identity"] = brand
    return result
