"""Baseline study 01: score one released artifact against the truth (results/baseline01/CRITERIA.md, section 5)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
sys.path.insert(0, str(ROOT / "dev/marm2_ladder"))
from sumcp import sanity, sufile  # noqa: E402
from common import read_segy  # noqa: E402
from run_oracle import load_reference, reference_match  # noqa: E402
import evaluate as E  # noqa: E402

DT = 0.002


def _load(path: Path):
    if path.suffix.lower() in (".sgy", ".segy"):
        d = read_segy(path)
        mid = (d["sx"] + d["gx"]) / 2.0
        return d["data"].astype(np.float64), d["cdp"], mid, d["dt_s"], 0.0, "segy"
    geom = sufile.geometry(path)
    h = sufile.read_header_columns(path, ["cdp", "sx", "gx", "scalco", "dt", "delrt"], geom)
    data = np.asarray(sufile.read_traces(path, np.arange(geom["ntr"]), geom), dtype=np.float64)
    sc = np.asarray(h["scalco"], dtype=float)
    fac = np.where(sc < 0, -1.0 / np.where(sc == 0, 1, sc), np.where(sc > 0, sc, 1.0))
    mid = (np.asarray(h["sx"], float) + np.asarray(h["gx"], float)) / 2.0 * fac
    return data, np.asarray(h["cdp"]), mid, geom["dt_s"], geom["t_start_s"], "su"


def score(path, ref=None) -> dict:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return {"verdict": "invalid", "reason": "no artifact"}
    try:
        data, cdp, mid, dt, t0, kind = _load(path)
    except Exception as exc:                                   # noqa: BLE001
        return {"verdict": "invalid", "reason": f"unreadable as SU or SEG-Y: {type(exc).__name__}: {exc}"}
    if abs(dt - DT) > 1e-9 or abs(t0) > 1e-9:
        return {"verdict": "invalid", "reason": f"time axis dt={dt}, t0={t0} (contract: 2 ms from t = 0)"}
    rms, mx, nf = sanity.trace_stats(data)
    bad_mask, scale, limit = sanity.corrupt_mask(rms, mx, nf)
    if bad_mask.any() or not np.isfinite(data).all():
        return {"verdict": "bad", "reason": f"{int(bad_mask.sum())} trace(s) non-finite or beyond the Q0 limit",
                "kind": kind}
    use_mid = np.all(np.isfinite(mid)) and np.any(mid != 0)
    ref_cdp = np.rint(mid / 10.0).astype(int) if use_mid else np.asarray(cdp, int)
    if not use_mid and not np.any(cdp):
        return {"verdict": "invalid", "reason": "no trace identity (no coordinates, no cdp)"}
    ref = ref or load_reference()
    ns = min(data.shape[1], ref["agc"].shape[1])
    d = np.zeros((data.shape[0], ref["agc"].shape[1]))
    d[:, :ns] = data[:, :ns]
    live = (np.linalg.norm(d[:, 340:710], axis=1) > 0) & (np.linalg.norm(d[:, 690:1210], axis=1) > 0)
    inside = (ref_cdp >= 400) & (ref_cdp - 400 < ref["agc"].shape[0])
    keep = live & inside
    scored = int(np.sum(keep & (ref_cdp >= 640) & (ref_cdp <= 1100)))
    if scored == 0:
        return {"verdict": "bad", "reason": "no live trace inside the scored CDP range", "kind": kind,
                "identity": "midpoint" if use_mid else "cdp"}
    try:
        m = reference_match(d[keep], ref_cdp[keep], ref, 0)
    except Exception as exc:                                   # noqa: BLE001
        return {"verdict": "harness_error", "reason": f"{type(exc).__name__}: {exc}"}
    best = m["0.7-2.4s"]["best_lag_pm20ms"]
    return {"verdict": "good" if best >= E.GOOD else "bad", "best_lag": best,
            "zero_lag": m["0.7-2.4s"]["zero_lag"], "traces_scored": scored, "kind": kind,
            "identity": "midpoint" if use_mid else "cdp", "good_threshold": round(float(E.GOOD), 4)}


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[1]), indent=1))
