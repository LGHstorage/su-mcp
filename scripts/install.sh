#!/usr/bin/env bash
# Install and check SU-MCP. From the project folder:
#
#     bash scripts/install.sh
#
# Options:
#   --skip-venv       skip the virtual environment and dependencies
#   --skip-testdata   do not rebuild the test data
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
skip_venv=0
skip_testdata=0
for arg in "$@"; do
    case "$arg" in
        --skip-venv) skip_venv=1 ;;
        --skip-testdata) skip_testdata=1 ;;
        *) echo "unknown option: $arg"; exit 2 ;;
    esac
done

fail() { echo; echo "stopped: $*"; exit 1; }

echo "=============================================="
echo " 1. environment"
echo "=============================================="
python3 - <<'PY' || fail "Python 3.10 or later is required."
import sys
print(f"python {sys.version.split()[0]}")
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

# CWPROOT must hold bin and src; without src, su_help and su_search do not work.
cwproot_ok() {
    [ -n "${1:-}" ] && [ -d "$1/bin" ] && [ -x "$1/bin/surange" ]
}

resolved=""
if cwproot_ok "${CWPROOT:-}"; then
    resolved="$CWPROOT"
elif [ -n "${CWPROOT:-}" ]; then
    echo "CWPROOT=$CWPROOT  has no bin/surange, looking on PATH."
fi

if [ -z "$resolved" ]; then
    # <root>/bin/surange
    found="$(command -v surange 2>/dev/null || true)"
    if [ -n "$found" ]; then
        candidate="$(cd "$(dirname "$(readlink -f "$found")")/.." && pwd)"
        if cwproot_ok "$candidate"; then
            resolved="$candidate"
            echo "CWPROOT from surange on PATH: $resolved"
        fi
    fi
fi

if [ -z "$resolved" ]; then
    fail "$(cat <<'MSG'
Seismic Unix not found.

  - if SU is installed, find it with  which surange  and
                            export CWPROOT=<that path without /bin/surange>
    e.g. /home/USER/cwp/bin/surange  ->  export CWPROOT=/home/USER/cwp
  - otherwise install CWP/SU first.

'/path/to/cwp' in the README is a placeholder.
MSG
)"
fi

export CWPROOT="$resolved"
export PATH="$CWPROOT/bin:$PATH"
echo "CWPROOT = $CWPROOT"

missing=""
for p in surange sugethw suwind sugain sufilter susort sudoc sufind \
         segyread segyhdrs segywrite susynlv suchw suaddnoise suplane; do
    [ -x "$CWPROOT/bin/$p" ] || command -v "$p" >/dev/null 2>&1 || missing="$missing $p"
done
[ -z "$missing" ] || fail "SU programs not found:$missing"
echo "$(ls "$CWPROOT/bin" | wc -l) SU programs found"

# sudoc reads $CWPROOT/src, so bin alone is not enough.
if PAGER=cat sudoc sufilter 2>/dev/null | grep -qi sufilter; then
    echo "sudoc works (su_help and su_search available)"
else
    echo
    echo "warning: sudoc cannot find the sufilter documentation."
    echo "      check that $CWPROOT/src exists. Only su_help and su_search are affected."
fi

mkdir -p raw work results qc logs state/datasets

echo
echo "=============================================="
echo " 2. virtual environment and dependencies"
echo "=============================================="
if [ "$skip_venv" -eq 1 ]; then
    # Use an existing .venv if there is one.
    if [ -x .venv/bin/python ]; then
        python="$root/.venv/bin/python"
        echo "using the existing .venv: $python"
    else
        python="python3"
        echo "skipped (--skip-venv), no .venv, using system python3."
    fi
else
    if [ ! -x .venv/bin/python ]; then
        # --copies: symlinks can fail on mounted Windows drives
        python3 -m venv --copies .venv 2>/tmp/su-mcp-venv.err || {
            echo "--- venv error ---"; cat /tmp/su-mcp-venv.err
            fail "$(cat <<'MSG'
Could not create the virtual environment. On Ubuntu or WSL the venv module is often missing

    sudo apt update && sudo apt install -y python3-venv python3-dev

Install it and run again.
MSG
)"
        }
    fi
    python="$root/.venv/bin/python"
    "$python" -m pip install --upgrade pip >/dev/null
    "$python" -m pip install -r requirements.txt || fail "dependency installation failed."
    "$python" -c 'import mcp, numpy, matplotlib' \
        || fail "installed, but the import failed."
    echo "mcp, numpy, matplotlib ready"
fi

echo
echo "=============================================="
echo " 3. test data"
echo "=============================================="
if [ "$skip_testdata" -eq 1 ] || [ -f raw/line01.sgy ]; then
    echo "already present (delete raw/line01.sgy and run scripts/make_test_data.sh to rebuild)"
else
    SU_MCP_PYTHON="$python" bash scripts/make_test_data.sh
fi

echo
echo "=============================================="
echo " 4. unit tests"
echo "=============================================="
# Stop here if a dependency is missing.
"$python" - <<'PY' || fail "$(cat <<'MSG'
Required packages are missing. Either run

    bash scripts/install.sh              (creates the environment and installs)
    .venv/bin/python -m pip install -r requirements.txt

--skip-venv needs an existing .venv.
MSG
)"
import importlib.util, sys
missing = [m for m in ("numpy", "matplotlib") if importlib.util.find_spec(m) is None]
if missing:
    print("missing packages:", ", ".join(missing))
    sys.exit(1)
print("numpy, matplotlib found")
PY
SU_MCP_ROOT="" "$python" -W ignore::ResourceWarning -m unittest discover -s tests \
    || fail "unit tests failed."

echo
echo "=============================================="
echo " 5. MCP round trip"
echo "=============================================="
if "$python" -c "import mcp" 2>/dev/null; then
    "$python" dev/mcp_roundtrip.py || fail "MCP round trip failed."
else
    echo "skipped, the mcp package is missing (pip install -r requirements.txt)"
fi

echo
echo "=============================================="
echo " done, MCP client configuration"
echo "=============================================="
cat <<JSON
{
  "mcpServers": {
    "seismic-unix": {
      "command": "$python",
      "args": ["$root/server.py"],
      "env": {
        "CWPROOT": "$CWPROOT",
        "SU_MCP_ROOT": "$root"
      }
    }
  }
}
JSON
