# Remove Semgrep from the PR gate

User decision: remove the Semgrep check instead of upgrading or suppressing
parser errors. Remove it from workflow selection, CLI accepted checks and the
executor dispatch/default list. Keep the Code security job (Gitleaks only) and
All required checks name stable. Other blockers and Invalid Scan behavior stay.

Historical private parser helpers/configuration remain for diagnostic regression
tests but are not registered as runnable PR checks. No node images are deleted.
Current required images: Gitleaks, Ruff, quality-tools. Static security findings
previously supplied by Semgrep are no longer covered, including Python/JS/TS.

Validation: CLI rejects Semgrep; default and workflow never select it; real
integration asserts the helper is not invoked and summaries do not mention it.
Test starred subscripts, known quality blockers, malformed Python, secret
advisories and scanner failure handling. Run Linux unit/self/bootstrap and all
real-tool tests before PR. Independent approval is required before release and
stable promotion. Rollback is the previous immutable release.
