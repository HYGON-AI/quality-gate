# ARC acceptance resumption implementation plan

> Execute directly with the available executing-plans skill; no subagents.

**Goal:** Complete corrected two-node collective proof, then HCU multi-child cancellation and clean recovery.

**Architecture:** Same quality-gate test branch, owned namespaces/queues, approved nmz3/4/6, fixed test image IDs, nonroot/no task credentials, ARC min1/max4. Reuse existing tested fixture/cleanup. No production gate, foreign Runner, driver/plugin/clock/network-policy or privilege changes. This is a fresh bounded batch, not a claim that yesterday's 5h soak completed.

**Window:** User resumed on2026-11-07. This batch stops submissions06:40UTC (14:40China); cleanup by06:50UTC. No recurring automation or renewed5hload inferred.

1. Readiness: all3Ready/noPressure, rootfree>25Gi/RAMavailable>64Gi, exact cached image IDs, no KFD processes/K8sHCUreservation, no old node-CI listeners able to race test allocations. Preserve quality/foreign pools. If conflict, use only safely isolated approved nodes or request coordination; do not kill others.
2. Regression-first: test new fixed cutoff boundaries for pair/combination drivers; update only those old expired test cutoffs; all ARC unit checks must pass. Retain actual collective payload-allowlist fix. Pin new source then reusable workflow, narrowly replace only own inactive old test references in group5; keep other entries/access unchanged.
3. Recheck collective admission/RBAC using server dry-run before live submission. No new permissions. First nmz3-nmz4 then otherpairs only after PASS. Capture both rank reports, compile/JUnit/binary artifacts, node/image/UID correlation,20roundsGloo+RCCL all_reduce/all_gather and socket transport proof. Failure pauses that profile; inspect before retry. RDMA remains separate/unproven.
4. GPU cancellation: fresh gpu-queue same-node8Running+1Pending witness with recordedJob/PodUIDs, cancel ownGitHubrun, verify allchildren absent/finally+independentcleanup, then a new successful probe. Do not count a missed cancellation window as PASS.
5. Stop/cancel/delete only this batch's correlated test tasks at deadline; confirm no own orphans and own pool returnsmin1. Persist run/UID/evidence/results and honest untested items. No all-repo migration.

**Files:** scripts/arc-pair.py, scripts/arc-hcu-combinations.py, tests/test_arc_collective.py, tests/test_arc_hcu_combinations.py; pinned .github/workflows/arc-collective.yml,arc-hcu-combinations.yml and arc-soak-trigger.yml. Operator-only local helpers track readiness and selected workflow access. Test command: python -m unittest discover -s tests -p 'test_arc*.py'.
