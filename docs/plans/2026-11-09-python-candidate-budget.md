# Python candidate overflow implementation plan

**Goal:** Fix composable_kernel-das PR #10's unused kernel-name candidate
explosion, without changing policy, images, workflow scope or scanner limits.

**Architecture:** Preserve the existing 256-value cap. Defer only candidate-count
overflow in variable bindings using an explicit opaque state. Propagate it through
existing supported expressions and control-flow joins; reading it at a visible
output sink still fails the scan. Reassignment can replace it with a fully known
value. Other budget errors remain immediate. No partial candidate truncation.

**Tech Stack:** Python >=3.9, AST visitor, unittest, existing native gate replay.

## Alternatives

- Raising the cap only moves the combinatorial failure and increases memory use.
- Skipping the file or all overflowing expressions silently can miss output.
- Deferred fail-closed bindings address unused computed names while preserving
  failure when the existing output analysis needs the overflowing value.

## Execution (Code / executing-plans, no delegation)

1. Add `tests/test_runtime_candidates.py`: synthetic conditional kernel naming,
   alias/format/addition/join propagation, overwrite, independent sensitive output,
   incremental origins and retained limits. Run the new suite against unmodified
   code and retain the expected failures. Keep real repository source outside this
   repository; fetch/read it only, never execute it.
2. Modify only candidate-overflow handling in
   `src/hygon_pr_gate/sensitive_diff_check.py`. Update earlier candidate-limit
   fixtures to consume the oversized value at an output sink so they continue to
   verify fail-closed behavior. Add corresponding integration fixtures.
3. Run focused and full unit tests, self-test, compile and bootstrap suites.
   Replay the exact failing Git range with unchanged policies and check that
   findings are retained. Run GitHub's existing Python 3.9/3.11/3.12 matrix.
4. Prepare a small PR and patch release notes/version metadata. Require independent
   approval and passing validation before merging/releasing/moving stable. Do not
   bypass branch protection or change existing immutable tags.

## Acceptance

- Real file/range no longer fails on unused candidate overflow.
- Overflow used in a recognized output sink remains Invalid Scan, including via
  aliases, branches, loops, formatting and augmented assignment.
- Unrelated output and split sensitive strings retain incremental origins.
- Work/time, expression-depth, string-size and 256-candidate caps stay unchanged.
- Production main/stable and node configuration are not edited during development.
