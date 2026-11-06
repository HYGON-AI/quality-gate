# ARC One-Hour Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continue bounded ARC validation for one hour, ending 2026-11-06 14:02 Asia/Shanghai (06:02 UTC), and produce an evidence-backed readiness/gap report.

**Architecture:** Existing ARC 0.15.1 dispatch pool, min=1 max=4, test runner pods pinned to nmz3. Keep GitHub execution and Volcano compute scheduling distinct. No production migration during this window.

**Tech Stack:** GitHub Actions, Helm, Kubernetes 1.31.11, ARC, Volcano; Python local read-only observers; PowerShell/gh.

## Boundaries

- Only push tests to test/arc-platform-20261106 in HYGON-AI/quality-gate; no main/stable edits or PR merge.
- Do not stop other runners, restart nodes, change clocks, clean images/disks, increase runner max, or change production access policies.
- Never mount administrator kubeconfig or App private key into a test runner/compute pod. Credentials only in existing approved secure locations; never put credentials in automation prompts, logs, commits or new plaintext files.
- GPU workloads require an exclusive, confirmed non-conflicting test card pool. An idle snapshot alone is insufficient while an old runner can still accept GPU work. If exclusivity cannot be proved, perform dry-run/read-only validation only and record GPU tests deferred.
- No production capacity claim from sleep-based concurrency tests. Record cold-start/queue/log-upload latency separately from actual compute.
- Stop starting new work at 14:02; cancel only this plan's unfinished test runs if needed, observe cleanup, report, delete temporary heartbeat. Do not cancel unrelated jobs.

## Completed before this window

- Six concurrent-demand jobs: all passed, observed four executing and two queued; recovery to one idle.
- Deliberate exit 17: correct failure. One-minute timeout: cancelled, no false success.
- Explicit cancellation: cancelled; task runner pods removed.
- Two follow-up jobs: checkout exact commit and temporary-file isolation passed.
- Retired fixed runner k8s-dispatch-01 (ID 78), directory retained, no target processes remain.

## Task 1: Efficiency and repeated scaling

Create a branch-filtered arc-platform-efficiency.yml with <=12 bounded jobs and short duration. No GPU or privileged execution. Validate YAML, pinned actions and exact branch guard before pushing. Record jobs' GitHub timestamps, runner names and pod snapshots. Evaluate max four executing, fair progress, no stranded queued jobs, return to idle, and repeat once only if new evidence is needed. Use existing run/job IDs to avoid duplicate dispatch.

## Task 2: Logs and artifacts

In a trusted test workflow create a small synthetic artifact without environment dumps, upload with a verified full-SHA official action, then download/verify with another ephemeral job. Bound artifact retention and size. Preserve failures as failures. No sensitive contents or repository secrets requested.

## Task 3: Read-only readiness audit

Inspect controller/listener stability, pod CPU/memory limits, service-account permissions, host mounts, storage/log retention, time drift and current node labels. Record gaps; don't silently relax policy. Current cluster has nmz3/4/6 only. User confirmed all three BW1100; nmz6 plugin reports BW1101, so use a distinct operator-owned scheduling-class label in a future approved rollout. Other four nodes are not yet joined.

## Task 4: Volcano feasibility

Read existing Volcano smoke scripts/workflows without rerunning old host-dispatch jobs. Check API/RBAC/queue/admission and server-side dry-run manifests if safe. Current ARC runner has automountServiceAccountToken=false, no kubectl guarantee, and no compute-submit role. Design a least-privilege submitter and validated resource interface; do not give general public-PR runners broad Pod creation rights. If new trust/security choices are needed, record a blocker rather than apply cluster-admin access.

## Task 5: Wrap-up

Save all observations and status to E:/Codex工作目录/outputs/arc-20261106/hour-progress.md and result files. Summarize passes, actual failures, deferred tests, efficiency tradeoffs, and migration prerequisites. Link real GitHub runs. Verify test pods reclaimed and one idle runner remains; no silent claim that all functionality is proven.
