# v2.0.5 header preservation and release plan

**Goal:** Ignore presentation-only header edits while protecting copyright, SPDX and recognized complete traditional license notices. Release v2.0.5 only after passing Linux and live PR validation.

**Architecture:** A small pure parser extracts comment-header text without executing source. Whitespace and comment wrappers normalize to word sequences; substantive words, punctuation and order remain significant. Known complete MIT/BSD-3-Clause and Apache-2.0 notice templates identify traditional notices. Unknown/partial notices never imply an approved license. Preserve recognized original notice bodies even when SPDX remains present. No automatic source edits or H1/H2/H3 attribution inference.

**Tech stack:** Python 3.9+, unittest, production Git diff/scanners, GitHub Actions.

1. Add `tests/test_license_headers.py` with failing reflow/comment-style cases and removal/replacement controls; add complete/partial traditional notices and body-deletion cases.
2. Implement `src/hygon_pr_gate/header_notices.py`; integrate in `native_checks.py`. Preserve existing rule identifiers where practical, add a distinct traditional-body-removal blocker. No changes to identity or scanner failure policy.
3. Add tests for recognized MIT/BSD/Apache templates with and without SPDX, duplicate declarations, comments versus source literals, incomplete and unknown headers, and original attribution preservation.
4. Update README/English README, package version and workflow version to v2.0.5. Document conservative recognition scope and migration behavior. Prepare release notes.
5. Push candidate PR #11; run full Linux CI and actual consumer PR #33 against the candidate. Keep deliberate fixtures out of main.
6. Merge candidate through normal GitHub rules (no bypass). Check release commit CI, create immutable v2.0.5 tag and Release, then update stable with an exact lease against its previously observed tag object. Verify both tags dereference to the same tested commit.

Known boundary: this is syntactic preservation and template recognition, not a legal/originality determination. Header scanning remains bounded by the existing configured line limit. Pure reflow of root legal files is also normalized without treating changed wording as preserved.
