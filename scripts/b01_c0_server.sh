#!/usr/bin/env bash
# Baseline study 01, condition C0: the production code with evidence governance OFF. Evaluation only.
# Register it in the MCP client next to the production seismic-unix server.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SU_MCP_GOVERNANCE=off SU_MCP_EVAL_DEPLOYMENT=baseline01
export SU_MCP_RUNTIME="$HOME/su-mcp-b01-c0/runtime" SU_MCP_STATE="$HOME/su-mcp-b01-c0/state"
export SU_MCP_LOG_DIR="$ROOT/results/baseline01/runlogs/C0"
export CWPROOT="${CWPROOT:-$HOME/cwp}"
export SU_MCP_ROOT="$ROOT"
export PATH="$CWPROOT/bin:$PATH"
mkdir -p "$SU_MCP_RUNTIME" "$SU_MCP_STATE" "$SU_MCP_LOG_DIR"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
# stdout belongs to the MCP protocol stream; nothing else may write to it
exec "$PY" "$ROOT/server.py"
