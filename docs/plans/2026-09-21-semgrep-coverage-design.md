# Narrow C++ parser compatibility exception

User approved a trial implementation, not a release or stable update.
Keep the tested production image. Do not skip files or suppress findings.
Enable only the reproduced C++ warning fingerprint through the central policy:
code 2, level warn, type Other syntax error, exact simple-var message with
matching source path and positive line number. Unknown/malformed errors,
missing reports and process failures remain invalid scans.

Return known compatibility warnings as advisory findings with locations and
an explicit partial scanner state. Do not drop coverage warnings during changed
line filtering. Unknown coverage failures take precedence; real blockers retain
their level. Summaries show partial coverage prominently even alongside blockers.

Validation: known fingerprint and each near miss; mixed known/unknown errors;
mixed real blocker and compatibility warning; missing/malformed report and
process failure; partial summary; production-image replay of pinned PR source.
No change to tag, stable, release, repository workflow or runner configuration.

## Trial validation

- 13 focused parser/executor/summary unit tests passed locally.
- Linux full unit regression: 139 tests passed.
- Production pinned Semgrep image replayed the original topology.cpp through the
  patched executor: partial state, one located advisory at line 1136, zero blockers.
  Rendered heading explicitly states incomplete coverage, not full scan success.
- Candidate Semgrep 1.177.0 was not adopted: it reproduces the same parser issue.
- This was an isolated executor replay, not a rerun of the GitHub PR's four Jobs.
  Production remains unchanged until a separately approved rollout.
