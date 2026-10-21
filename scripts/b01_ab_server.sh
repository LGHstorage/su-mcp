#!/usr/bin/env bash
# Baseline study 01, condition A or B (first argument): SU programs behind a shell (A) or typed calls (B).
# Evaluation only; never the production server.
set -euo pipefail
MODE="${1:?usage: b01_ab_server.sh A|B}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CWPROOT="${CWPROOT:-$HOME/cwp}"
export SU_MCP_ROOT="$ROOT"
export B01_MODE="$MODE"
export B01_WORK="$HOME/su-mcp-b01-ab/$MODE"
export B01_INPUT="$ROOT/test_dataset/Baseline01_challenge"
export B01_SU_BIN="$CWPROOT/bin"
export B01_LOG="$ROOT/results/baseline01/runlogs/$MODE"
export B01_SUBMIT="$ROOT/results/baseline01/submitted/$MODE"
mkdir -p "$B01_WORK" "$B01_LOG" "$B01_SUBMIT"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
# stdout belongs to the MCP protocol stream; nothing else may write to it
exec "$PY" "$ROOT/evalsrv/baseline01_server.py"
