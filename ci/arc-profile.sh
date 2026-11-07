#!/usr/bin/env bash
set -euo pipefail
# Executed ONLY inside the uncredentialed Volcano compute Pod.
exec python3 -u tests/fixtures/arc_e2e/run_profile.py
