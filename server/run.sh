#!/usr/bin/env bash
# Start the BwithU server. Usage: ./run.sh [config name, default bwithu]
set -euo pipefail
cd "$(dirname "$0")"
CONFIG="${1:-bwithu}"
if [ -f ../.env ]; then set -a; . ../.env; set +a; fi
# OpenBLAS's own thread pool can deadlock with our many handler threads (seen with numpy + torch).
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
exec .venv/bin/python src/demo.py --config "config/$CONFIG.yaml"
