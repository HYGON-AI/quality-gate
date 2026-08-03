#!/usr/bin/env python3
# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""End-to-end native self tests for the HYGON incremental PR gate."""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from hygon_pr_gate.audit_pr import _github_annotation, run_gate
from hygon_quality_security.secret_placeholders import (
    deterministic_placeholder_reason,
)


ROOT = Path(__file__).resolve().parents[1]
HYGON = "Copyright (c) 2026 Hygon Information Technology Co., Ltd."
FORBIDDEN_A = "su" + "gon"
SENSITIVE_DEVICE = "dcu"
SENSITIVE_VENDOR = "amd"
SENSITIVE_LINK = "xgmi"
EXPECTED_WORKFLOW_CHECKS = {
    "governance-compliance-check": (
        "Identity, license & wording",
        "identity,compliance,sensitive-diff",
    ),
    "repository-integrity-quality-check": (
        "Repository & code quality",
        "git-encoding,syntax-workflow,ruff,quality-tools",
    ),
    "security-check": ("Secrets & SAST", "gitleaks,semgrep"),
    "dependency-security-check": ("Dependency vulnerabilities", "trivy"),
}


def run(command, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "{} failed: {}".format(
                " ".join(command), completed.stderr.decode("utf-8", errors="replace")
            )
        )
    return completed.stdout.decode("utf-8", errors="replace").strip()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def initialize(repo: Path) -> str:
    run(["git", "init", "-q", "-b", "main", str(repo)], repo.parent)
    run(["git", "config", "user.name", "Hygon Developer"], repo)
    run(["git", "config", "user.email", "developer@hygon.com"], repo)
    write(repo / "LICENSE", "Apache License\nVersion 2.0\nOriginal terms\n")
    write(repo / "NOTICE", "Original upstream notice\n")
    write(
        repo / "base.py",
        "# Copyright (c) Original Author\n"
        "# SPDX-License-Identifier: Apache-2.0\n"
        "VALUE = 1\n",
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "chore(core): initialize fixture"], repo)
    return run(["git", "rev-parse", "HEAD"], repo)


def arguments(
    repo: Path,
    base: str,
    head: str,
    summary: Path,
    repository="HYGON-AI/sglang-das",
    policy_root=ROOT / "policies",
):
    return argparse.Namespace(
        repo=repo,
        repository=repository,
        base=base,
        head=head,
        policy_root=policy_root,
        summary=summary,
        native_only=True,
    )


def assert_clean_pr_passes(root: Path) -> None:
    repo = root / "clean"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "good.py",
        "# {}\n# SPDX-License-Identifier: Apache-2.0\n"
        "VALUE = 2\nEXAMPLE = 'SPDX-License-Identifier: GPL-3.0'\n".format(HYGON),
    )
    run(["git", "add", "good.py"], repo)
    run(["git", "commit", "-q", "-m", "feat(runtime): add supported value"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(arguments(repo, base, head, root / "clean.md"))
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "# Quality Gate · PR 增量门禁" in content
    assert "Check / 检查项：`All Checks`（全部检查）" in content
    assert "本检查通过" in content
    assert "Blockers / 阻断问题：0" in content


def assert_clear_violations_block(root: Path) -> None:
    repo = root / "blocked"
    repo.mkdir()
    base = initialize(repo)
    write(repo / "LICENSE", "Replacement private terms\n")
    write(repo / "base.py", "VALUE = 2\n")
    write(repo / "bad.py", "def broken(:\n    return 1\n")
    write(repo / "third_party/vendor.c", "int vendor(void) { return 1; }\n")
    write(
        repo / ".github/workflows/test.yml",
        "name: test\non: [pull_request]\njobs:\n  test:\n    runs-on: self-hosted\n"
        "    steps:\n      - uses: actions/checkout@v4\n",
    )
    os.symlink("../../outside", repo / "escape-link")
    run(["git", "add", "."], repo)
    run(
        [
            "git", "-c", "user.name=Hygon Developer",
            "-c", "user.email=developer@{}.com".format(FORBIDDEN_A),
            "commit", "-q", "-m", "fix(runtime): add blocked fixture",
        ],
        repo,
    )
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(arguments(repo, base, head, root / "blocked.md"))
    assert code == 2, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    for marker in (
        "禁止的品牌身份",
        "逃逸仓库的符号链接",
        "Python 文件存在明确语法错误",
        "删除或重写了原 LICENSE",
        "删除或替换了原版权/许可证声明",
        "新增源码的版权和许可证归属待复核",
    ):
        assert marker in content, marker
    assert "本检查阻断" in content


def assert_mutable_action_is_advisory(root: Path) -> None:
    repo = root / "mutable-action"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / ".github/workflows/test.yml",
        "name: test\non: [pull_request]\njobs:\n  test:\n    runs-on: self-hosted\n"
        "    steps:\n      - uses: actions/checkout@v4\n",
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "ci: add workflow"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    args = arguments(repo, base, head, root / "mutable-action.md")
    args.checks = "git-encoding,syntax-workflow,ruff,quality-tools"
    args.display_name = "Repository & code quality"
    summary, code = run_gate(args)
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Repository & code quality" in content
    assert "Workflow 使用可移动 Action" in content
    assert "Advisories / 提示问题：1" in content
    assert "Blockers / 阻断问题：0" in content


def assert_replacement_character_blocks(root: Path) -> None:
    repo = root / "garbled-text"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "garbled.py",
        "# {}\n# SPDX-License-Identifier: Apache-2.0\n"
        "MESSAGE = 'broken � text'\n".format(HYGON),
    )
    run(["git", "add", "garbled.py"], repo)
    run(["git", "commit", "-q", "-m", "fix(text): add garbled fixture"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    args = arguments(repo, base, head, root / "garbled.md")
    args.checks = "git-encoding"
    args.display_name = "File Integrity"
    summary, code = run_gate(args)
    assert code == 2, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Check / 检查项：`File Integrity`（文件完整性）" in content
    assert "Built-in / 内置检查" in content
    assert "`git-encoding`" not in content
    assert "native-git" not in content
    assert "Unicode 替换字符" in content
    assert "U+FFFD" in content

    args.display_name = "Code Quality"
    summary, code = run_gate(args)
    assert code == 1
    mismatch = summary.read_text(encoding="utf-8")
    assert "PR check display name mismatch" in mismatch
    assert "expected File Integrity, got Code Quality" in mismatch


def assert_existing_debt_is_not_blocked(root: Path) -> None:
    repo = root / "existing-debt"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "legacy.py",
        "# Copyright (c) Original Author\n"
        "# SPDX-License-Identifier: GPL-3.0\n"
        "LEGACY_OWNER = {!r}\n".format(FORBIDDEN_A)
        + "VALUE = 1\n",
    )
    write(
        repo / ".github/workflows/legacy.yml",
        "name: old\non: [pull_request]\njobs:\n  test:\n    runs-on: self-hosted\n"
        "    steps:\n      - uses: actions/checkout@v4\n",
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "chore(test): add legacy baseline debt"], repo)
    base = run(["git", "rev-parse", "HEAD"], repo)
    write(
        repo / "legacy.py",
        "# Copyright (c) Original Author\n"
        "# SPDX-License-Identifier: GPL-3.0\n"
        "LEGACY_OWNER = {!r}\n".format(FORBIDDEN_A)
        + "VALUE = 2\n",
    )
    write(
        repo / ".github/workflows/legacy.yml",
        "name: new\non: [pull_request]\njobs:\n  test:\n    runs-on: self-hosted\n"
        "    steps:\n      - uses: actions/checkout@v4\n",
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "fix(test): update unrelated values"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(arguments(repo, base, head, root / "existing-debt.md"))
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "禁止的品牌身份" not in content
    assert "可移动 Action" not in content
    assert "未自动准入或复合许可证" not in content


def assert_legal_file_additions_preserve_content(root: Path) -> None:
    repo = root / "legal-additions"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "NOTICE",
        "Inserted attribution before\n"
        "Original upstream notice\n"
        "Inserted attribution after\n",
    )
    run(["git", "add", "NOTICE"], repo)
    run(["git", "commit", "-q", "-m", "docs: add scoped attribution"], repo)
    preserved_head = run(["git", "rev-parse", "HEAD"], repo)
    args = arguments(repo, base, preserved_head, root / "legal-additions.md")
    args.checks = "compliance"
    args.display_name = "License Compliance"
    summary, code = run_gate(args)
    assert code == 0, summary.read_text(encoding="utf-8")

    write(repo / "NOTICE", "Inserted attribution only\n")
    run(["git", "add", "NOTICE"], repo)
    run(["git", "commit", "-q", "-m", "test: remove original notice"], repo)
    removed_head = run(["git", "rev-parse", "HEAD"], repo)
    args = arguments(repo, base, removed_head, root / "legal-removal.md")
    args.checks = "compliance"
    args.display_name = "License Compliance"
    summary, code = run_gate(args)
    assert code == 2, summary.read_text(encoding="utf-8")
    assert "PR 删除或重写了原 NOTICE 内容" in summary.read_text(encoding="utf-8")


def assert_non_secret_model_key_is_ignored(root: Path) -> None:
    repo = root / "non-secret-model-key"
    repo.mkdir()
    initialize(repo)
    path = "tests/hcu/test_report.py"
    write(
        repo / path,
        "write_result(\n"
        "    model_key=\"bw1100_gsm8k_hcu\",\n"
        "    api_key=\"opaque-nonplaceholder-value-123456\",\n"
        ")\n",
    )
    run(["git", "add", path], repo)
    run(["git", "commit", "-q", "-m", "test: add report identifiers"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    policy = yaml.safe_load(
        (
            ROOT
            / "policies/quality-security/hygon-quality-security-v1.1.yaml"
        ).read_text(encoding="utf-8")
    )
    config = policy["scanners"]["gitleaks"]["placeholder_filter"]
    common = {
        "Commit": head,
        "File": path,
        "RuleID": "generic-api-key",
    }
    assert (
        deterministic_placeholder_reason(
            dict(common, StartLine=2),
            source_repo=repo,
            target_commit=head,
            config=config,
        )
        == "non-secret-assignment"
    )
    assert (
        deterministic_placeholder_reason(
            dict(common, StartLine=3),
            source_repo=repo,
            target_commit=head,
            config=config,
        )
        is None
    )


def assert_github_annotation_contract() -> None:
    annotation = _github_annotation(
        {
            "level": "blocker",
            "rule_id": "TEST.RULE",
            "path": "src/a,b.py",
            "line": 7,
            "title": "Unsafe title\ncontinued",
            "remediation": "Fix the finding.",
        }
    )
    assert annotation.startswith(
        "::error file=src/a%2Cb.py,line=7,title=TEST.RULE::"
    )
    assert "%0A" in annotation


def assert_unregistered_repository_uses_universal_policy(root: Path) -> None:
    repo = root / "unregistered"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "good.py",
        "# {}\n# SPDX-License-Identifier: Apache-2.0\nVALUE = 2\n".format(HYGON),
    )
    run(["git", "add", "good.py"], repo)
    run(["git", "commit", "-q", "-m", "feat(runtime): add value"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(
        arguments(
            repo,
            base,
            head,
            root / "unregistered.md",
            repository="HYGON-AI/not-registered",
        )
    )
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Invalid Scan / 扫描无效" not in content
    assert "本检查通过" in content


def assert_invalid_repository_name_is_invalid(root: Path) -> None:
    repo = root / "invalid-repository"
    repo.mkdir()
    base = initialize(repo)
    write(
        repo / "good.py",
        "# {}\n# SPDX-License-Identifier: Apache-2.0\nVALUE = 2\n".format(
            HYGON
        ),
    )
    run(["git", "add", "good.py"], repo)
    run(["git", "commit", "-q", "-m", "feat(runtime): add value"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(
        arguments(
            repo,
            base,
            head,
            root / "invalid-repository.md",
            repository="invalid repository name",
        )
    )
    assert code == 1
    content = summary.read_text(encoding="utf-8")
    assert "Invalid Scan / 扫描无效" in content
    assert "OWNER/REPOSITORY" in content


def assert_universal_compliance_is_high_confidence(root: Path) -> None:
    repo = root / "universal-compliance"
    repo.mkdir()
    base = initialize(repo)

    write(repo / "unclassified.py", "VALUE = 1\n")
    run(["git", "add", "unclassified.py"], repo)
    run(["git", "commit", "-q", "-m", "feat: add unclassified source"], repo)
    unclassified_head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(
        arguments(repo, base, unclassified_head, root / "unclassified.md")
    )
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "新增源码的版权和许可证归属待复核" in content
    assert "Advisories / 提示问题：1" in content
    assert "Blockers / 阻断问题：0" in content

    write(
        repo / "hygon-without-spdx.py",
        "# {}\nVALUE = 2\n".format(HYGON),
    )
    run(["git", "add", "hygon-without-spdx.py"], repo)
    run(["git", "commit", "-q", "-m", "test: add incomplete HYGON header"], repo)
    incomplete_head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(
        arguments(
            repo,
            unclassified_head,
            incomplete_head,
            root / "hygon-without-spdx.md",
        )
    )
    assert code == 2, summary.read_text(encoding="utf-8")
    assert "新增 HYGON 源码文件头缺少 SPDX" in summary.read_text(
        encoding="utf-8"
    )

    legal_repo = root / "legal-file-move"
    legal_repo.mkdir()
    legal_base = initialize(legal_repo)
    run(["git", "mv", "LICENSE", "LEGAL.txt"], legal_repo)
    run(["git", "commit", "-q", "-m", "test: move root license"], legal_repo)
    legal_head = run(["git", "rev-parse", "HEAD"], legal_repo)
    summary, code = run_gate(
        arguments(
            legal_repo,
            legal_base,
            legal_head,
            root / "legal-file-move.md",
        )
    )
    assert code == 2, summary.read_text(encoding="utf-8")
    assert "PR 删除了原 LICENSE 文件" in summary.read_text(encoding="utf-8")


def assert_invalid_central_sensitive_policy_is_invalid(root: Path) -> None:
    policy_root = root / "invalid-central-policy"
    shutil.copytree(ROOT / "policies", policy_root)
    policy_path = policy_root / "pr" / "hygon-pr-gate-v1.2.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy["sensitive_diff"]["legacy_dcu"]["allowed_content_patterns"] = ["["]
    write(policy_path, yaml.safe_dump(policy, default_flow_style=False))

    repo = root / "invalid-central-policy-repo"
    repo.mkdir()
    base = initialize(repo)
    write(repo / "value.py", "VALUE = 2\n")
    run(["git", "add", "value.py"], repo)
    run(["git", "commit", "-q", "-m", "test: add value"], repo)
    head = run(["git", "rev-parse", "HEAD"], repo)
    summary, code = run_gate(
        arguments(
            repo,
            base,
            head,
            root / "invalid-central-policy.md",
            policy_root=policy_root,
        )
    )
    assert code == 1
    content = summary.read_text(encoding="utf-8")
    assert "Invalid Scan / 扫描无效" in content
    assert "invalid regex" in content


def assert_sensitive_diff_scope(root: Path) -> None:
    repo = root / "sensitive-diff"
    repo.mkdir()
    initialize(repo)
    write(
        repo / "legacy.py",
        "MESSAGE = {!r}\n".format(SENSITIVE_VENDOR + " historical text"),
    )
    write(
        repo / "python" / "sglang" / "srt" / "hcu" / "existing_multiline.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "logger.info(\"\"\"AMD GPU compatibility\n"
        "old description\n"
        "\"\"\")\n",
    )
    historical_path = "docs/internal/dcu-main-conflict-ledger.md"
    write(repo / historical_path, "Historical migration ledger.\n")
    run(
        [
            "git",
            "add",
            "legacy.py",
            "python/sglang/srt/hcu/existing_multiline.py",
            historical_path,
        ],
        repo,
    )
    run(["git", "commit", "-q", "-m", "chore(test): add historical text"], repo)
    base = run(["git", "rev-parse", "HEAD"], repo)

    # Historical sensitive text and unrelated substrings are outside the
    # incremental token gate.
    write(
        repo / "legacy.py",
        "MESSAGE = {!r}\nVALUE = 2\n".format(
            SENSITIVE_VENDOR + " historical text"
        ),
    )
    write(
        repo / "src" / "qwamdd" / "uidcui.py",
        "DCUTLASS_ENABLE_TENSOR_CORE_MMA = True\n"
        "DCUTLASS_DEBUG_TRACE_LEVEL = 0\n"
        "DCUTLASS_ENABLE_GDC_FOR_SM100 = True\n"
        "DCUTLASS_ENABLE_GDC_FOR_SM90 = True\n"
        "DCUTLASS_TEST_ENABLE_CACHED_RESULTS = True\n"
        "DCUTLASS_TEST_LEVEL = 0\n"
        "DCUTLASS_VERSIONS_GENERATED = True\n"
        "class EAGLEDraftExtendCudaGraphRunner:\n"
        "    pass\n"
        "EXTERNAL = 'https://harbor.sourcefind.cn:5443/dcu/approved/image'\n"
        "BARE_IMAGE = 'harbor.sourcefind.cn:5443/dcu/admin/base/dev'\n"
        "CPU_VENDOR = 'amd64'\n"
        "AMDGPU_TARGETS = 'gfx'\n"
        "HSA_XGMI_LINK = 1\n"
        "logger.warning('FP16 params may not work on AMD CPUs')\n"
        "DESCRIPTION = 'AMD/HIP backend compatibility'\n",
    )
    write(
        repo / "src" / "rename_source.py",
        "VALUE = 1\n",
    )
    write(
        repo / "python" / "sglang" / "srt" / "hcu" / "existing_multiline.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "logger.info(\"\"\"AMD GPU compatibility\n"
        "updated description\n"
        "\"\"\")\n",
    )
    write(
        repo / historical_path,
        "Historical migration ledger.\n"
        "Runtime audit found no is_dcu predicate.\n",
    )
    run(
        [
            "git",
            "add",
            "legacy.py",
            "src/qwamdd/uidcui.py",
            "src/rename_source.py",
            "python/sglang/srt/hcu/existing_multiline.py",
            historical_path,
        ],
        repo,
    )
    run(["git", "commit", "-q", "-m", "fix(test): add clean line"], repo)
    clean_head = run(["git", "rev-parse", "HEAD"], repo)
    clean_args = arguments(repo, base, clean_head, root / "sensitive-clean.md")
    clean_args.checks = "sensitive-diff"
    clean_args.display_name = "Sensitive Diff Text"
    summary, code = run_gate(clean_args)
    assert code == 0, summary.read_text(encoding="utf-8")
    clean_content = summary.read_text(encoding="utf-8")
    assert "Added content contains a legacy DCU token" in clean_content
    assert (
        "Changed destination path contains a legacy DCU token" not in clean_content
    )
    assert "Advisories / 提示问题：1" in clean_content

    # DCU is a repository-rename rule: exact tokens in destination paths and
    # added content are blocked, while unrelated substrings remain allowed.
    sensitive_path = "scripts/ci/{}/test.sh".format(SENSITIVE_DEVICE)
    write(
        repo / sensitive_path,
        "is_{}=1\n".format(SENSITIVE_DEVICE)
        + "register_{}_ci=1\n".format(SENSITIVE_DEVICE)
        + "registerDcuCi=1\n"
        + "DCUMLABackend = object()\n"
        + "BACKEND='HWBackend.{}'\n".format(SENSITIVE_DEVICE.upper())
        + "SGLANG_{}_ENABLE=1\n".format(SENSITIVE_DEVICE.upper())
        + "IMAGE='{}_CI_IMAGE'\n".format(SENSITIVE_DEVICE.upper())
        + "echo '{} device'\n".format(SENSITIVE_DEVICE.upper())
        + "EXTERNAL='https://example.invalid/dcu/dev'\n",
    )
    run(["git", "mv", "src/rename_source.py", "src/dcu_utils.py"], repo)
    run(["git", "add", sensitive_path], repo)
    run(["git", "commit", "-q", "-m", "test(gate): add legacy device tokens"], repo)
    dcu_head = run(["git", "rev-parse", "HEAD"], repo)
    blocked_args = arguments(repo, clean_head, dcu_head, root / "dcu-blocked.md")
    blocked_args.checks = "sensitive-diff"
    blocked_args.display_name = "Sensitive Diff Text"
    summary, code = run_gate(blocked_args)
    assert code == 2, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Changed destination path contains a legacy DCU token" in content
    assert "Added content contains a legacy DCU token" in content
    assert "DCUMLABackend" in content
    assert "example.invalid/dcu/dev" in content
    assert "SENSITIVE_DIFF.LEGACY_DCU_PATH" not in content

    # AMD/XGMI are blocked only in an HCU-owned user-visible output sink.
    hcu_path = "python/sglang/srt/hcu/runtime.py"
    write(
        repo / hcu_path,
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "logger.info('Using {} GPU with {}')\n".format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "logger.warning('Using AmD GPU with XgMi')\n"
        + "STATUS = {'status': 'AMD topology unavailable'}\n",
    )
    write(
        repo / "python/sglang/srt/generic_runtime.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "if is_hcu():\n"
        "    logger.error('{} 1 hop {} detection failed')\n".format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "if not is_hcu():\n"
        "    logger.warning('{} GPU compatibility path')\n".format(
            SENSITIVE_VENDOR.upper()
        )
        + "if is_hcu() and feature_enabled:\n"
        "    logger.info('HCU fast path')\n"
        "else:\n"
        "    logger.warning('{} fallback path')\n".format(
            SENSITIVE_VENDOR.upper()
        )
        + "if backend == 'hcu':\n"
        "    logger.info('{} GPU with {} from string condition')\n".format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "if is_hcu():\n"
        "    log_info_on_rank0('{} GPU with {} from rank0 logger')\n".format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "    log_warning_on_rank0('{} GPU from rank0 warning')\n".format(
            SENSITIVE_VENDOR.upper()
        )
        + "    log_error_on_rank0('{} from rank0 error')\n".format(
            SENSITIVE_LINK.upper()
        ),
    )
    write(
        repo / "src" / "hcu" / "runtime.cpp",
        "TORCH_WARN(\n"
        '    "{} GPU with {} from multiline call");\n'.format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "std::cerr\n"
        '    << "{} from stream output" << std::endl;\n'.format(
            SENSITIVE_LINK.upper()
        )
        + 'LOG(INFO) << "{} GPU from LOG call";\n'.format(
            SENSITIVE_VENDOR.upper()
        )
        + 'SPDLOG_WARN("{} GPU from spdlog");\n'.format(
            SENSITIVE_VENDOR.upper()
        )
        + 'fprintf(stderr, "{} GPU from fprintf");\n'.format(
            SENSITIVE_VENDOR.upper()
        )
        + 'puts("{} GPU from puts");\n'.format(SENSITIVE_VENDOR.upper()),
    )
    write(
        repo / "scripts" / "runtime.sh",
        "if is_hcu; then\n"
        "    echo '{} GPU with {} from shell branch'\n".format(
            SENSITIVE_VENDOR.upper(), SENSITIVE_LINK.upper()
        )
        + "fi\n",
    )
    write(
        repo / "src" / "generic_runtime.cpp",
        "if (is_hcu()) {\n"
        '    std::cout << "AMD GPU from HCU C++ branch" << std::endl;\n'
        "}\n"
        "if (!is_hcu()) {\n"
        '    std::cout << "AMD GPU from non-HCU C++ branch" << std::endl;\n'
        "}\n",
    )
    run(
        [
            "git",
            "add",
            hcu_path,
            "python/sglang/srt/generic_runtime.py",
            "src/hcu/runtime.cpp",
            "src/generic_runtime.cpp",
            "scripts/runtime.sh",
        ],
        repo,
    )
    run(["git", "commit", "-q", "-m", "test(gate): add HCU runtime wording"], repo)
    runtime_head = run(["git", "rev-parse", "HEAD"], repo)
    runtime_args = arguments(
        repo, dcu_head, runtime_head, root / "hcu-runtime-blocked.md"
    )
    runtime_args.checks = "sensitive-diff"
    runtime_args.display_name = "Sensitive Diff Text"
    summary, code = run_gate(runtime_args)
    assert code == 2, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "HCU user-visible output contains AMD/XGMI wording" in content
    assert "info()" in content
    assert "error()" in content
    assert "fallback path" in content
    assert "string condition" in content
    assert "rank0 logger" in content
    assert "rank0 warning" in content
    assert "rank0 error" in content
    assert "multiline call" in content
    assert "stream output" in content
    assert "LOG call" in content
    assert "spdlog" in content
    assert "fprintf" in content
    assert "puts" in content
    assert "shell branch" in content
    assert "HCU C++ branch" in content
    assert "non-HCU C++ branch" not in content
    assert "compatibility path" not in content

    # Identifiers and comments are not user-visible sinks. AMD paths are also
    # legal because AMD does not participate in path hard blocking.
    write(
        repo / "test" / "registered" / "amd" / "compatibility.py",
        "# AMD and XGMI upstream compatibility\n"
        "AMDGPU_TARGETS = 'gfx'\n"
        "HSA_XGMI_LINK = 1\n",
    )
    write(
        repo / "python/sglang/srt/hcu/identifiers.py",
        "# AMD and XGMI implementation notes\n"
        "AMDGPU_TARGETS = 'gfx'\n"
        "HSA_XGMI_LINK = 1\n"
        "logger.warning('FP16 params may not work on AMD CPUs')\n"
        "logger.info('HSA_XGMI_LINK is configured')\n"
        "if is_hcu():\n"
        "    logger.info('HCU path')\n"
        "else:\n"
        "    logger.info('AMD GPU compatibility path')\n"
        "if is_amd():\n"
        "    logger.info('AMD GPU explicit compatibility branch')\n"
        "else:\n"
        "    logger.info('HCU native branch')\n",
    )
    write(
        repo / "scripts" / "non_hcu_runtime.sh",
        "if ! is_hcu; then\n"
        "    echo 'AMD GPU with XGMI from non-HCU shell branch'\n"
        "fi\n",
    )
    write(
        repo / "src" / "generic_comment.cpp",
        "/*\n"
        "if (is_hcu()) {\n"
        "*/\n"
        "// if (is_hcu()) {\n"
        'const char* url = "https://example.invalid/is_hcu/path";\n'
        'LOG_INFO("AMD GPU from comment-only HCU marker");\n',
    )
    write(
        repo / "scripts" / "hcu" / "compat.sh",
        "if is_amd; then\n"
        "    echo 'AMD GPU explicit compatibility branch'\n"
        "else\n"
        "    echo 'HCU native branch'\n"
        "fi\n",
    )
    write(
        repo / "docs" / "hcu" / "debug.md",
        "Example fixture: logger.info(\"AMD GPU\")\n",
    )
    write(
        repo / "tests" / "hcu" / "test_logging.py",
        "EXPECTED_LOG = 'AMD GPU compatibility mode'\n",
    )
    run(
        [
            "git",
            "add",
            "test/registered/amd/compatibility.py",
            "python/sglang/srt/hcu/identifiers.py",
            "scripts/non_hcu_runtime.sh",
            "src/generic_comment.cpp",
            "scripts/hcu/compat.sh",
            "docs/hcu/debug.md",
            "tests/hcu/test_logging.py",
        ],
        repo,
    )
    run(["git", "commit", "-q", "-m", "test(gate): add allowed identifiers"], repo)
    allowed_head = run(["git", "rev-parse", "HEAD"], repo)
    allowed_args = arguments(
        repo, runtime_head, allowed_head, root / "hcu-runtime-allowed.md"
    )
    allowed_args.checks = "sensitive-diff"
    allowed_args.display_name = "Sensitive Diff Text"
    summary, code = run_gate(allowed_args)
    assert code == 0, summary.read_text(encoding="utf-8")


def assert_shared_workflow_contract() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "pr-quality-gate.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]
    matrix = jobs["incremental_check"]["strategy"]["matrix"]["include"]
    checks = {
        item["check_id"]: (item["display_name"], item["scanners"])
        for item in matrix
    }
    assert checks == EXPECTED_WORKFLOW_CHECKS
    assert all(
        not display_name.endswith("-check")
        for display_name, _scanners in checks.values()
    )
    assert "profile_admission" not in jobs
    assert "needs" not in jobs["incremental_check"]
    assert jobs["hygon-pr-gate-result-check"]["name"] == "All required checks"
    assert jobs["hygon-pr-gate-result-check"]["needs"] == ["incremental_check"]
    assert "CHECK_DISPLAY_NAME: ${{ matrix.display_name }}" in workflow_text
    assert '--display-name "$CHECK_DISPLAY_NAME"' in workflow_text
    assert "hygon_pr_gate.profile_admission" not in workflow_text
    assert "Repository policy" not in workflow_text
    assert "# All required checks · PR 门禁汇总" in workflow_text
    assert "Merge Blocked / 阻断合并" in workflow_text
    assert "Merge Allowed / 允许合并" in workflow_text
    assert "HYGON-AI/open-source-governance" not in workflow_text
    assert "repository: ${{ job.workflow_repository }}" in workflow_text
    assert "ref: ${{ job.workflow_sha }}" in workflow_text
    assert "uses: ./quality-gate" in workflow_text
    assert "QUALITY_GATE_ROOT: ${{ steps.quality_gate.outputs.gate-path }}" in workflow_text
    assert "TRIVY_CACHE_PATH: ${{ vars.HYGON_TRIVY_CACHE }}" in workflow_text
    assert 'export HYGON_TRIVY_CACHE="$TRIVY_CACHE_PATH"' in workflow_text
    assert "--github-annotations" in workflow_text
    assert 'cat "$summary"' in workflow_text
    assert "actions/checkout@1af3b93b6815bc44a9784bd300feb67ff0d1eeb3" in workflow_text
    assert not list((ROOT / "policies" / "repository-profiles").glob("*.yaml"))

    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert {"gate-path", "python-path"}.issubset(action["outputs"])

    template_path = ROOT / "examples" / "workflows" / "quality-gate.yml"
    template_text = template_path.read_text(encoding="utf-8")
    template = yaml.safe_load(template_text)
    assert template["name"] == "Quality Gate"
    assert template["jobs"]["checks"]["name"] == "Checks"
    assert "HYGON-AI/quality-gate/.github/workflows/pr-quality-gate.yml" in template_text
    assert "QUALITY_GATE_REF" in template_text


def main() -> None:
    assert_shared_workflow_contract()
    with tempfile.TemporaryDirectory(prefix="hygon-pr-gate-test-") as directory:
        root = Path(directory)
        assert_clean_pr_passes(root)
        assert_clear_violations_block(root)
        assert_replacement_character_blocks(root)
        assert_existing_debt_is_not_blocked(root)
        assert_legal_file_additions_preserve_content(root)
        assert_non_secret_model_key_is_ignored(root)
        assert_github_annotation_contract()
        assert_unregistered_repository_uses_universal_policy(root)
        assert_invalid_repository_name_is_invalid(root)
        assert_mutable_action_is_advisory(root)
        assert_universal_compliance_is_high_confidence(root)
        assert_invalid_central_sensitive_policy_is_invalid(root)
        assert_sensitive_diff_scope(root)
    print("hygon-pr-gate self tests: OK")


if __name__ == "__main__":
    main()
