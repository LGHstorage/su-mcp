#!/usr/bin/env bash
# SU-MCP environment check
set -u
echo "== python =="
python3 --version
echo
echo "== CWPROOT =="
echo "${CWPROOT:-(not set)}"
echo
echo "== SU programs =="
for p in sufilter sugain suwind susort surange sugethw sufind sudoc \
         segyread suvelan sunmo sustack suplane susynlv; do
    printf '%-12s %s\n' "$p" "$(command -v "$p" || echo 'missing')"
done
echo
echo "== sufind filter (first 10 lines) =="
PAGER=cat sufind filter 2>&1 | head -10
echo
echo "== project directories =="
root="$(cd "$(dirname "$0")/.." && pwd)"
for d in raw work results qc logs; do
    printf '%-8s %s\n' "$d" "$([ -d "$root/$d" ] && echo present || echo 'missing')"
done
