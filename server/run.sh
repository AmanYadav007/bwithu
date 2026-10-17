#!/usr/bin/env bash
# Start the BwithU server. Usage: ./run.sh [bwithu|bwithu_dev]
set -euo pipefail
cd "$(dirname "$0")"
CONFIG="${1:-bwithu}"
if [ -f ../.env ]; then set -a; . ../.env; set +a; fi
# OpenBLAS's own thread pool can deadlock with our many handler threads (seen with numpy + torch).
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
if [ "$CONFIG" = "bwithu" ] && [ -z "${DASHSCOPE_API_KEY:-}" ]; then
  echo "DASHSCOPE_API_KEY is empty in ../.env. Use './run.sh bwithu_dev' to test without Qwen." >&2
  exit 1
fi
exec .venv/bin/python src/demo.py --config "config/$CONFIG.yaml"
