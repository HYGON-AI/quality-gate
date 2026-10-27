# Analysis scaling and executable workflow scope

## Failures and approach

Sglang's large `server_args.py` exhausts 500,000 analysis operations while
merging unchanged bindings across branches. Reuse already bounded candidate
lists only when both branch states share the identical list object. Charge
join work, preserve typed values and origin unions for changed states, and
retain every existing resource limit. Do not skip changed code or raise limits.

The quality driver recursively sends `.github/workflows/configs/` mappings to
Actionlint. Recognize only direct `.github/workflows/*.yml` or `*.yaml` files
as executable workflows, with the same classification in native checks and the
standalone driver. Nested YAML still receives ordinary syntax/duplicate-key
checks; genuine workflow errors and reference diagnostics remain enabled.

## Verification

Pair large unchanged-state fixtures with changed-value/origin/type cases and
resource exhaustion. Compare optimized joins with the old bounded join over
valid typed states. Pair nested configuration maps with genuine workflow errors,
and test classification parity between native and container code.

Run the full suite and Python 3.9/3.11/3.12 CI. Replay exact historical Sglang
and vLLM failures without executing repository code, plus lightop and Megatron
regressions. Test real pinned images and keep raw source/reports out of this
repository. Publish only after independent approval and passing verification.
