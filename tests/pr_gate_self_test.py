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

from hygon_pr_gate.audit_pr import run_gate
from hygon_pr_gate.policy import REPOSITORY_MODES
from hygon_pr_gate.profile_admission import render_admission


ROOT = Path(__file__).resolve().parents[1]
HYGON = "Copyright (c) 2026 Hygon Information Technology Co., Ltd."
FORBIDDEN_A = "su" + "gon"
SENSITIVE_DEVICE = "dcu"
SENSITIVE_VENDOR = "amd"
SENSITIVE_LINK = "xgmi"
EXPECTED_WORKFLOW_CHECKS = {
    "governance-compliance-check": (
        "Governance & Compliance",
        "identity,compliance,sensitive-diff",
    ),
    "repository-integrity-quality-check": (
        "Repository Integrity & Quality",
        "git-encoding,syntax-workflow,ruff,quality-tools",
    ),
    "security-check": ("Security", "gitleaks,semgrep"),
    "dependency-security-check": ("Dependency Security", "trivy"),
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
        "新增第三方源码缺少明确版权或 SPDX",
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
    args.display_name = "Repository Integrity & Quality"
    summary, code = run_gate(args)
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Repository Integrity & Quality" in content
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


def assert_unknown_repository_is_invalid(root: Path) -> None:
    repo = root / "unknown"
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
        arguments(repo, base, head, root / "unknown.md", repository="HYGON-AI/not-registered")
    )
    assert code == 1
    assert "Invalid Scan / 扫描无效" in summary.read_text(encoding="utf-8")
    assert "扫描无效" in summary.read_text(encoding="utf-8")


def write_test_profile(
    policy_root: Path,
    *,
    repository: str,
    repository_mode: str,
    hygon_owned_paths=None,
    upstream_paths=None,
    patch_paths=None,
) -> None:
    profile = {
        "schema_version": 1,
        "repository": repository,
        "repository_mode": repository_mode,
        "policy": "hygon-pr-gate-v1.2",
        "license": "Apache-2.0",
        "checks": {
            "security": True,
            "quality": True,
            "compliance": True,
            "commit_identity": True,
            "hcu_runtime_wording": False,
        },
        "legal_files": ["LICENSE", "NOTICE"],
        "third_party_registries": ["THIRD_PARTY_NOTICES.md"],
        "third_party_paths": ["third_party/vendor/**"],
        "generated_paths": ["**/*_pb2.py"],
        "hygon_owned_paths": hygon_owned_paths or [],
        "upstream_paths": upstream_paths or [],
        "patch_paths": patch_paths or [],
    }
    filename = repository.replace("/", "_") + ".yaml"
    write(
        policy_root / "repository-profiles" / filename,
        yaml.safe_dump(profile, default_flow_style=False),
    )


def assert_repository_modes_drive_compliance(root: Path) -> None:
    policy_root = root / "mode-policies"
    shutil.copytree(ROOT / "policies", policy_root)

    original_repository = "HYGON-AI/test-original"
    write_test_profile(
        policy_root,
        repository=original_repository,
        repository_mode="original",
    )
    original = root / "mode-original"
    original.mkdir()
    base = initialize(original)
    write(original / "missing.py", "VALUE = 1\n")
    run(["git", "add", "missing.py"], original)
    run(["git", "commit", "-q", "-m", "feat: add original source"], original)
    head = run(["git", "rev-parse", "HEAD"], original)
    summary, code = run_gate(
        arguments(
            original,
            base,
            head,
            root / "mode-original.md",
            repository=original_repository,
            policy_root=policy_root,
        )
    )
    assert code == 2, summary.read_text(encoding="utf-8")
    assert "HYGON 新增源码缺少完整合规文件头" in summary.read_text(
        encoding="utf-8"
    )

    fork_repository = "HYGON-AI/test-fork"
    write_test_profile(
        policy_root,
        repository=fork_repository,
        repository_mode="fork",
    )
    fork = root / "mode-fork"
    fork.mkdir()
    base = initialize(fork)
    write(fork / "unclassified.py", "VALUE = 1\n")
    run(["git", "add", "unclassified.py"], fork)
    run(["git", "commit", "-q", "-m", "feat: sync source"], fork)
    head = run(["git", "rev-parse", "HEAD"], fork)
    summary, code = run_gate(
        arguments(
            fork,
            base,
            head,
            root / "mode-fork.md",
            repository=fork_repository,
            policy_root=policy_root,
        )
    )
    assert code == 0, summary.read_text(encoding="utf-8")
    content = summary.read_text(encoding="utf-8")
    assert "Fork 新增源码的来源待确认" in content
    assert "HYGON 新增源码缺少完整合规文件头" not in content

    patch_repository = "HYGON-AI/test-submodule-patch"
    write_test_profile(
        policy_root,
        repository=patch_repository,
        repository_mode="submodule-patch",
        upstream_paths=["third_party/verl/**"],
        patch_paths=["patches/**"],
    )
    patch_repo = root / "mode-submodule-patch"
    patch_repo.mkdir()
    base = initialize(patch_repo)
    write(patch_repo / "third_party/verl/upstream.py", "VALUE = 1\n")
    run(["git", "add", "."], patch_repo)
    run(["git", "commit", "-q", "-m", "chore: update upstream fixture"], patch_repo)
    head = run(["git", "rev-parse", "HEAD"], patch_repo)
    summary, code = run_gate(
        arguments(
            patch_repo,
            base,
            head,
            root / "mode-submodule-patch.md",
            repository=patch_repository,
            policy_root=policy_root,
        )
    )
    assert code == 0, summary.read_text(encoding="utf-8")
    assert "HYGON 新增源码缺少完整合规文件头" not in summary.read_text(
        encoding="utf-8"
    )


def assert_profile_admission(root: Path) -> None:
    admitted = root / "profile-admitted.md"
    assert (
        render_admission(
            repository="HYGON-AI/sglang-das",
            summary=admitted,
            policy_root=ROOT / "policies",
        )
        == 0
    )
    admitted_text = admitted.read_text(encoding="utf-8")
    assert "Admitted / 已准入" in admitted_text
    assert "Repository Mode / 仓库模式：`fork`" in admitted_text

    rejected = root / "profile-rejected.md"
    assert (
        render_admission(
            repository="HYGON-AI/not-registered",
            summary=rejected,
            policy_root=ROOT / "policies",
        )
        == 1
    )
    rejected_text = rejected.read_text(encoding="utf-8")
    assert "Invalid / 无效" in rejected_text
    assert "其他扫描 Job 未启动" in rejected_text

    invalid_policy_root = root / "profile-invalid-policies"
    shutil.copytree(ROOT / "policies", invalid_policy_root)
    profile_path = (
        invalid_policy_root
        / "repository-profiles"
        / "HYGON-AI_sglang-das.yaml"
    )
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["sensitive_diff"]["legacy_dcu"]["allowed_content_patterns"] = ["["]
    write(profile_path, yaml.safe_dump(profile, default_flow_style=False))
    invalid = root / "profile-invalid-sensitive-diff.md"
    assert (
        render_admission(
            repository="HYGON-AI/sglang-das",
            summary=invalid,
            policy_root=invalid_policy_root,
        )
        == 1
    )
    invalid_text = invalid.read_text(encoding="utf-8")
    assert "Invalid / 无效" in invalid_text
    assert "invalid regex" in invalid_text
    assert "其他扫描 Job 未启动" in invalid_text


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
    run(
        [
            "git",
            "add",
            "legacy.py",
            "python/sglang/srt/hcu/existing_multiline.py",
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
    run(
        [
            "git",
            "add",
            "legacy.py",
            "src/qwamdd/uidcui.py",
            "src/rename_source.py",
            "python/sglang/srt/hcu/existing_multiline.py",
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
    assert REPOSITORY_MODES == {
        "original",
        "fork",
        "submodule-patch",
        "overlay",
    }
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
    assert jobs["profile_admission"]["name"] == "Profile Admission"
    assert jobs["incremental_check"]["needs"] == "profile_admission"
    assert jobs["hygon-pr-gate-result-check"]["name"] == "Quality Gate Result"
    assert set(jobs["hygon-pr-gate-result-check"]["needs"]) == {
        "profile_admission",
        "incremental_check",
    }
    assert "CHECK_DISPLAY_NAME: ${{ matrix.display_name }}" in workflow_text
    assert '--display-name "$CHECK_DISPLAY_NAME"' in workflow_text
    assert "-m hygon_pr_gate.profile_admission" in workflow_text
    assert "其余扫描未启动" in workflow_text
    assert 'display_result="Skipped / 未启动"' in workflow_text
    assert "# Quality Gate Result · PR 门禁汇总" in workflow_text
    assert "Merge Blocked / 阻断合并" in workflow_text
    assert "Merge Allowed / 允许合并" in workflow_text
    assert "HYGON-AI/open-source-governance" not in workflow_text
    assert "repository: ${{ job.workflow_repository }}" in workflow_text
    assert "ref: ${{ job.workflow_sha }}" in workflow_text
    assert "uses: ./quality-gate" in workflow_text
    assert "QUALITY_GATE_ROOT: ${{ steps.quality_gate.outputs.gate-path }}" in workflow_text
    assert "TRIVY_CACHE_PATH: ${{ vars.HYGON_TRIVY_CACHE }}" in workflow_text
    assert 'export HYGON_TRIVY_CACHE="$TRIVY_CACHE_PATH"' in workflow_text

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
        assert_unknown_repository_is_invalid(root)
        assert_mutable_action_is_advisory(root)
        assert_repository_modes_drive_compliance(root)
        assert_profile_admission(root)
        assert_sensitive_diff_scope(root)
    print("hygon-pr-gate self tests: OK")


if __name__ == "__main__":
    main()
