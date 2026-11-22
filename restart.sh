#!/usr/bin/env bash
# Reset the active solver to baseline, verify tests, and run a clean RSI cycle.
set -euo pipefail

cd "$(dirname "$0")"

RUN_ID="${1:-demo-run}"

echo "[restart.sh] Resetting src/rsi_demo/solver.py to v0-baseline..."
python3 run_rsi.py --reset-only

echo "[restart.sh] Clearing previous artifacts for run '${RUN_ID}'..."
rm -rf "runs/${RUN_ID}"

echo "[restart.sh] Running test suite..."
python3 -m pytest -v

echo "[restart.sh] Starting fresh RSI demo run (${RUN_ID})..."
python3 run_rsi.py --run-id "${RUN_ID}"
