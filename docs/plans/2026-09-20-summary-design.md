# Concise summary and live PR validation

Keep all four job/check names and decision rules unchanged. Show the decision,
blocker/advisory counts and executed workflow version/SHA before collapsed scope
and tool details. Keep errors expanded and advisory detail collapsed. Distinguish
no applicable targets from successful scanning. The aggregate states gate success,
not repository merge permission. Version is candidate metadata in the executed
workflow, never fetched from a moving latest tag.

Validate presentation with unit tests and existing regressions. Use a disposable
open-source-governance PR referencing only the candidate branch. Run clean YAML
edge fixtures, then deliberate duplicate-key and Python-syntax failures in separate
commits. Preserve run links for review; do not merge the test PR or move stable.
