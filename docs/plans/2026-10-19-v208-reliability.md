# v2.0.8 Reliability Implementation Plan

**Goal:** Fix confirmed stable gate failures and add explicitly approved OpenMDW-1.1 admission, without changing check names or advisory/blocking policy.

**Architecture:** Keep the existing incremental pipeline. Bound and deduplicate static analysis, classify Git links separately from blobs, force trustworthy text diffs and mandatory Ruff configuration, and make operational failures explicit. No target code execution and no automatic license expansion beyond OpenMDW-1.1.

**Tech Stack:** Python 3.9+, Git, Docker, GitHub Actions, unittest, pinned scanner images.

## Approved design / alternatives

Chosen: targeted v2.0.8 reliability release. Rejected: scanner bypasses (false passes) and broad license auto-approval (not authorized). User approved the scope and OpenMDW-1.1 admission on 2026-10-19. Original notices and license preservation still apply.

## Tasks

1. Add `tests/test_reliability.py`: bounded branch analysis, budget failures, gitlinks, attribute-hidden changes, isolated Ruff, safe scanner diagnostics and OpenMDW admission. Run `PYTHONPATH=src python -m unittest discover -s tests -p test_reliability.py -v`; confirm baseline failures using bounded inputs only.
2. Fix `src/hygon_pr_gate/sensitive_diff_check.py`: deduplicate typed values and merge origins, enforce candidate/string/operation/time budgets before expansion. Test branch joins, loops, f-strings, format combinations and fail-closed budget outcomes.
3. Fix `git_scope.py`, `native_checks.py`, `local_executor.py`: identify gitlinks from tree mode, skip blob scanning but retain path checks; disable textconv/external diff and force text patches; mandatory Ruff isolation/no-noqa. Prove F823 cannot be hidden by configs, attributes or inline suppressions.
4. Improve executor diagnostics: classify missing images, ENOSPC, permissions, timeouts and missing/malformed reports; never expose untrusted scanner source/secret output. Add phase/version logs and Linux process limits. Do not change system Python or install node packages.
5. Add OpenMDW-1.1 to central approved sets and documentation. Test valid headers and unchanged preservation/unknown-license blocking.
6. Run compile, full unittest suite, native self test and bootstrap integration. Run all four real scanners and adverse cases on an isolated temporary Linux checkout with limits; repeat smoke checks on nmz1/4/6. Replay Megatron and PyTorch exact base/head snapshots; record elapsed time and RSS.
7. Update version to 2.0.8, CI compatibility checks, README/changelog/release notes. Create candidate PR, run hosted CI, obtain required independent approval. Do not bypass branch protection.
8. After successful merge and verification, create v2.0.8 release; move stable only after recording its old tag SHA (11e41137c3691ea13be41aff761851f6e354ada9, commit ab2c31c23bbd538947ae2dbd60672c8c196ddaf2). Verify exact tag targets. Existing runner workflow allowlist already includes stable; do not expand runner access automatically.

## Evidence / acceptance

- Original Megatron reproducer: 20 unchanged sequential if statements created 1,048,576 copies of one value. Fixed result must stay one value; 500 branches remain bounded.
- PyTorch gitlink updates must not require the submodule commit in the superproject object database. `.gitmodules` still scanned.
- Failed scanner or analysis budget must produce Invalid Scan, never Passed.
- All required checks remains the only aggregate required check; C/C++ Semgrep, complexity/style and secret advisory policy unchanged.
- Release is blocked on failed regression, missing real-image evidence, or required approval.
