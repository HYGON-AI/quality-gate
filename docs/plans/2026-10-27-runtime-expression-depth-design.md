# Bounded long-addition analysis

## Incident and scope

Stable v2.0.8 rejects lightop PR #114 because `setup.py` builds a source-file
list through 35 nested additions, exceeding the expression evaluator's depth
limit of 20. The source parses successfully. The same structure reproduces
with its older 27-addition build script. Keep target repository sources and
raw reports outside this repository.

## Design

Evaluate addition trees with an explicit stack, preserving Python's grouping,
left-to-right evaluation and the existing unknown-value short circuit. Visit
addition trees iteratively as well, retaining inspection of nested calls.
Non-addition expression nesting keeps its existing depth limit. Existing work,
time, string-size, candidate-count and workflow resource limits stay enabled.

Simply raising the depth threshold postpones the failure; treating exceeded
limits as a successful scan would hide incomplete analysis. Neither is used.

## Verification and delivery

Add portable regressions for list/call chains, long sensitive-string chains,
grouping, incremental origins, nested calls and retained limits. Run the full
self-test and unit suites, bootstrap checks and real lightop Git-scope replay
on the runner's Python 3.12.13. Verify the hosted Python 3.9/3.11/3.12 CI matrix
on the PR. Keep stable unchanged until independent review and release.
