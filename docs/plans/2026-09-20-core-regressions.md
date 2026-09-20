# Core gate regression plan

**Goal:** Independently verify compliance headers, commit metadata and sensitive wording, including summary locations.

**Architecture:** Real temporary Git repositories feed the production scope extractor and scanners. Each case has an isolated base/head pair. Synthetic identities never enter published commit metadata. Existing decision policy is unchanged.

**Tech stack:** Python unittest, Git, existing native scanners and Markdown renderer.

1. Add `tests/test_core_governance.py`: independent allowed/forbidden author email, committer email, subject and body; assert exact rule, severity, commit SHA and summary title. Include a bad earlier commit followed by a clean commit.
2. Add isolated header cases: valid original and upstream attribution, absent/partial header, missing SPDX, unsupported SPDX, removal versus preservation of upstream header. Assert exact findings and source location when available.
3. Add sensitive wording cases: runtime output, compatibility identifiers/comments, incidental substrings and unchanged historical lines. Assert advisory versus no finding and exact line.
4. Run `python -m unittest discover -s tests -p test_core_governance.py -v`, then full test discovery. Publish tests to the existing candidate PR and run full Linux CI.
5. Publish synthetic rendered case summaries to CI step summary for inspection, and use the disposable consumer PR for an additional compliance/wording check. Do not merge PRs or move stable.

Acceptance: exact finding sets, positive and negative cases, full CI evidence. Report skips and any uncovered areas explicitly.

## Approved follow-up design

User approved fixing mixed-case standalone AMD/XGMI missed by camel-token splitting. Recover an entire alphanumeric word only when it equals a configured term case-insensitively; do not add substring matching or change advisory severity. Test word boundaries explicitly.

Add the user's Apache-2.0/MIT/BSD-3-Clause H1/H2/H3 templates as allowed cases, plus Apache missing-upstream-header cases. These verify non-rejection, not automatic classification of originality or substantive contribution. The current scanner does not enforce H2/H3 contribution registration completeness.
