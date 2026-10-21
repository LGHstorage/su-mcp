"""Baseline study 02: usability labels (CRITERIA section 4), with the frozen study 01 oracle procedure."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("b01_oracle", ROOT / "dev/baseline01/oracle.py")
O = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(O)
HIDDEN = ROOT / "results/baseline02/hidden"
WORK = Path.home() / "baseline02_oracle_work"


def label(case, ref):
    out = HIDDEN / f"label_{case}.json"
    if out.exists():
        raise SystemExit(f"{out} exists")
    info = json.loads((HIDDEN / f"generation_{case}.json").read_text())
    path = ROOT / info["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
        raise SystemExit(f"{case}: file hash differs from generation record")
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "cmp_sorted.su").unlink(missing_ok=True)
    d, applied = O.correct(O.read_segy(path), info)
    order = O.cmp_sort(d)
    u = np.unique(d["cdp"])
    cdps = list(u[::20]) + ([int(u[-1])] if u[-1] not in u[::20] else [])
    c, tn, vn = O.truth_functions(cdps)
    s = O.nmo_stack(WORK, case, d, order, c, tn, vn, O.SMUTE)
    dd = np.asarray(s["data"])
    live = (np.linalg.norm(dd[:, 340:710], axis=1) > 0) & (np.linalg.norm(dd[:, 690:1210], axis=1) > 0)
    m = O.reference_match(dd[live], np.asarray(s["cdp"])[live], ref, 0)
    best = m["0.7-2.4s"]["best_lag_pm20ms"]
    rec = {"case": case, "file": info["file"], "applied": applied, "oracle_best_lag": best,
           "oracle_zero_lag": m["0.7-2.4s"]["zero_lag"], "traces_scored": m["traces"],
           "dead_traces": int((~live).sum()), "usable": bool(best >= O.E.GOOD),
           "good_threshold": round(float(O.E.GOOD), 4),
           "oracle_code_sha256": hashlib.sha256((ROOT / "dev/baseline01/oracle.py").read_bytes()).hexdigest()}
    (WORK / "cmp_sorted.su").unlink(missing_ok=True)
    out.write_text(json.dumps(rec, indent=1))
    print(case, applied, best, rec["usable"], flush=True)


if __name__ == "__main__":
    ref = O.load_reference()
    for c in sys.argv[1:]:
        label(c, ref)
