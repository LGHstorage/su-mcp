#!/usr/bin/env bash
# Test data. Three copies of one synthetic line that differ only in the cdp header.
#
#   A  raw/line01.su          no cdp           -> geometry must be computed
#   B  raw/line02_cdp_ok.su   correct cdp      -> nothing to compute
#   C  raw/line03_cdp_bad.su  cdp = shot number -> present but wrong, stack must be refused
#
#   raw/line01.sgy      A as SEG-Y (IBM float, big-endian)
#   raw/line01_le.sgy   the same data, little-endian (byte-order test)
#
# A header that is present but wrong is the dangerous case, so C is included.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
raw="$root/raw"
# Python from install.sh, else .venv, else python3.
python="${SU_MCP_PYTHON:-}"
if [ -z "$python" ]; then
    if [ -x "$root/.venv/bin/python" ]; then python="$root/.venv/bin/python"
    else python="python3"; fi
fi
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "[1/4] susynlv synthesis"
susynlv nt=751 dt=0.004 ft=0.0 \
    nxs=40 fxs=0 dxs=50 \
    nxo=48 fxo=-1175 dxo=50 \
    v00=1500 dvdz=0.6 \
    ref="1:0,500;6000,700" \
    ref="1:0,1100;6000,1500" \
    ref="1:0,1900;6000,1950" > "$tmp/syn.su"

echo "[2/4] coordinates and noise -> A (no cdp)"
# susynlv writes coordinates x1000; scale back to m and recompute offset
suchw < "$tmp/syn.su" key1=sx key2=sx a=0 b=1 c=0 d=1000 \
  | suchw key1=gx key2=gx a=0 b=1 c=0 d=1000 \
  | suchw key1=offset key2=gx key3=sx a=0 b=1 c=-1 d=1 \
  | suaddnoise sn=6 seed=1234 > "$raw/line01.su"

echo "[3/4] B (correct cdp) / C (wrong cdp)"
# midpoint spacing 25 m, bin 50 m, cdp = (sx+gx+1175)/50 + 1
suchw < "$raw/line01.su" key1=cdp key2=sx key3=gx a=1225 b=1 c=1 d=50 \
    > "$raw/line02_cdp_ok.su"
# shot number written into cdp
suchw < "$raw/line01.su" key1=cdp key2=fldr a=0 b=1 c=0 d=1 \
    > "$raw/line03_cdp_bad.su"

echo "[4/4] SEG-Y conversion"
segyhdrs < "$raw/line01.su" hfile="$tmp/h" bfile="$tmp/b" > /dev/null 2>&1
segywrite < "$raw/line01.su" tape="$raw/line01.sgy" \
    hfile="$tmp/h" bfile="$tmp/b" >/dev/null 2>&1

# The little-endian copy is made by swapping the big-endian file, not with segywrite endian=,
# whose result depends on how SU was built.
"$python" - "$root" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from sumcp import segy
raw = sys.argv[1] + "/raw"
if segy.diagnose(raw + "/line01.sgy")["byte_order"] != "big":
    segy.rewrite_byte_order(raw + "/line01.sgy", raw + "/tmp.sgy")
    import os; os.replace(raw + "/tmp.sgy", raw + "/line01.sgy")
print("  ", segy.rewrite_byte_order(raw + "/line01.sgy", raw + "/line01_le.sgy"))
PY

echo
for f in line01.su line02_cdp_ok.su line03_cdp_bad.su line01.sgy line01_le.sgy; do
    printf '%-22s %10d bytes\n' "$f" "$(stat -c%s "$raw/$f")"
done
echo
echo "cdp range:"
for f in line01.su line02_cdp_ok.su line03_cdp_bad.su; do
    printf '%-22s %s\n' "$f" "$(surange < "$raw/$f" 2>/dev/null | grep -E '^cdp' || echo 'no cdp')"
done
