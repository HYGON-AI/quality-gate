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
