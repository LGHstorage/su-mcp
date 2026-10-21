#!/usr/bin/env bash
# MCP client (Windows) -> wsl.exe -> this script -> MCP server
#
# Windows env entries do not reach WSL, and a login shell can print to stdout and break the
# MCP stream. This script sets the environment itself and keeps stdout for the server.
# Diagnostics go to stderr.
set -eu

here="$(cd "$(dirname "$0")/.." && pwd)"

cwproot_ok() { [ -n "${1:-}" ] && [ -x "$1/bin/surange" ]; }

# 1) keep a valid CWPROOT
if ! cwproot_ok "${CWPROOT:-}"; then
    # 2) derive it from surange on PATH
    found="$(command -v surange 2>/dev/null || true)"
    if [ -n "$found" ]; then
        candidate="$(cd "$(dirname "$(readlink -f "$found")")/.." && pwd)"
        cwproot_ok "$candidate" && CWPROOT="$candidate"
    fi
fi
if ! cwproot_ok "${CWPROOT:-}"; then
    # 3) try common install locations
    for candidate in "${HOME:-/root}/cwp" "${HOME:-/root}/src/cwp" \
                     /usr/local/cwp /opt/cwp /usr/local/SeisUnix; do
        cwproot_ok "$candidate" && { CWPROOT="$candidate"; break; }
    done
fi
if ! cwproot_ok "${CWPROOT:-}"; then
    echo "mcp_launch: Seismic Unix not found." >&2
    echo "  set CWPROOT in this script or put \$CWPROOT/bin on PATH." >&2
    exit 1
fi

export CWPROOT
export PATH="$CWPROOT/bin:$PATH"
export SU_MCP_ROOT="$here"

python="$here/.venv/bin/python"
if [ ! -x "$python" ]; then
    python="$(command -v python3 || true)"
    [ -n "$python" ] || { echo "mcp_launch: python3 not found." >&2; exit 1; }
    echo "mcp_launch: no .venv, using $python." >&2
fi

exec "$python" "$here/server.py"
