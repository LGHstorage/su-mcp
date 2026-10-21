"""S1: acquisition (field) statics, applied once and in the right direction (v0.32)."""

from __future__ import annotations

import numpy as np

from . import config, evidence, governance, runner, sufile
from .paths import as_rel, safe_output_path

ACQSTATICS_VERSION = "acqstatics-0.2"
SIGN_SEGY = -1                 # sustatic sign giving T' = T + s
FB_OFFSET_M = (50.0, 400.0)
FB_WINDOW_S = 1.0
FB_FRACTION = 0.25
MIN_TRACES_PER_SHOT = 6
# v0.33 L1: first arrivals across the spread (land reflection window)
FA_OFFSET_FRACTION = (0.25, 0.75)
FA_SLOW_M_S = 1000.0
FA_PAD_S = 0.5
FA_MIN_PICKS = 10
FA_MIN_SHOTS = 10
FA_MAD_K = 3.0
FA_MAX_SPREAD_S = 0.25          # p10-p90 of the per-shot window start
FA_VELOCITY_RANGE = (300.0, 8000.0)

__all__ = ["ACQSTATICS_VERSION", "SIGN_SEGY", "first_break_intercept", "statics_present",
           "first_arrivals", "fit_first_arrival_line", "land_first_arrivals", "apply"]


def _hdr(path, geom, keys):
    return {k: np.asarray(v) for k, v in sufile.read_header_columns(path, keys, geom).items()}


def statics_present(path, geom=None) -> bool:
    geom = geom or sufile.geometry(path)
    h = _hdr(path, geom, ["sstat", "gstat"])
    return bool(np.any(h["sstat"]) or np.any(h["gstat"]))


def first_break_intercept(path, geom=None) -> dict:
    """Median over shots of the intercept of first-break time against |offset| (50-400 m, first sample above a
    quarter of the trace maximum in the first second)."""
    geom = geom or sufile.geometry(path)
    h = _hdr(path, geom, ["offset", "fldr"])
    off = np.abs(h["offset"].astype(float))
    sel = np.flatnonzero((off >= FB_OFFSET_M[0]) & (off <= FB_OFFSET_M[1]))
    if sel.size == 0:
        return {"intercept_s": None, "shots": 0, "reason": "no trace at 50-400 m offset"}
    dt, t0 = geom["dt_s"], geom["t_start_s"]
    n = min(geom["ns"], int(round(FB_WINDOW_S / dt)))
    fb = np.empty(sel.size)
    for a in range(0, sel.size, 4000):
        idx = sel[a:a + 4000]
        d = np.abs(np.asarray(sufile.read_traces(path, idx, geom), dtype=np.float64)[:, :n])
        mx = d.max(axis=1, keepdims=True)
        hit = d > FB_FRACTION * np.where(mx > 0, mx, np.inf)
        k = np.where(hit.any(axis=1), hit.argmax(axis=1), -1)
        fb[a:a + idx.size] = np.where(k >= 0, t0 + k * dt, np.nan)
    shots = h["fldr"][sel]
    xs = off[sel]
    icpt = []
    for s in np.unique(shots):
        m = (shots == s) & np.isfinite(fb)
        if m.sum() < MIN_TRACES_PER_SHOT:
            continue
        A = np.c_[np.ones(m.sum()), xs[m]]
        c = np.linalg.lstsq(A, fb[m], rcond=None)[0]
        icpt.append(c[0])
    if not icpt:
        return {"intercept_s": None, "shots": 0, "reason": "no shot has enough near-offset traces"}
    return {"intercept_s": round(float(np.median(icpt)), 4), "shots": len(icpt),
            "rule": "first sample above 1/4 of the trace maximum in the first 1 s; 50-400 m; "
                    "one straight-line fit per shot; median over shots"}


def fit_first_arrival_line(offsets, picks):
    """Straight line t = a + p*x through one shot's picks, refitted without residuals beyond FA_MAD_K robust
    deviations."""
    x = np.asarray(offsets, dtype=float)
    t = np.asarray(picks, dtype=float)
    ok = np.isfinite(t)
    x, t = x[ok], t[ok]
    if x.size < FA_MIN_PICKS or np.ptp(x) <= 0:
        return None
    A = np.c_[np.ones(x.size), x]
    c = np.linalg.lstsq(A, t, rcond=None)[0]
    r = t - A @ c
    med = float(np.median(r))
    mad = float(np.median(np.abs(r - med)))
    keep = np.abs(r - med) <= FA_MAD_K * 1.4826 * mad if mad > 0 else np.ones(x.size, bool)
    if keep.sum() < FA_MIN_PICKS:
        return None
    c = np.linalg.lstsq(A[keep], t[keep], rcond=None)[0]
    return float(c[0]), float(c[1]), int(keep.sum())


def first_arrivals(path, geom=None) -> dict:
    """v0.33 L1: where the first arrivals leave the spread, measured on the gathers."""
    geom = geom or sufile.geometry(path)
    h = _hdr(path, geom, ["offset", "fldr"])
    off = np.abs(h["offset"].astype(float))
    xmax = float(off.max()) if off.size else 0.0
    base = {"rule": "L1 (v0.33): first arrivals, quarter-maximum pick, robust line per shot over "
                    "25-75% of the maximum offset, evaluated at the maximum offset; median over shots",
            "max_offset_m": round(xmax, 1), "algorithm_version": ACQSTATICS_VERSION}
    lo, hi = FA_OFFSET_FRACTION[0] * xmax, FA_OFFSET_FRACTION[1] * xmax
    sel = np.flatnonzero((off >= lo) & (off <= hi))
    dt, t0 = geom["dt_s"], geom["t_start_s"]
    search = min(geom["ns"] * dt, hi / FA_SLOW_M_S + FA_PAD_S)
    n = max(1, min(geom["ns"], int(round(search / dt))))
    base["search_to_s"] = round(t0 + n * dt, 3)
    if sel.size == 0:
        return {**base, "status": "UNKNOWN", "reason": "no trace between 25% and 75% of the maximum offset"}
    fb = np.full(sel.size, np.nan)
    for a in range(0, sel.size, 4000):
        idx = sel[a:a + 4000]
        d = np.abs(np.asarray(sufile.read_traces(path, idx, geom), dtype=np.float64)[:, :n])
        mx = d.max(axis=1, keepdims=True)
        hit = d > FB_FRACTION * np.where(mx > 0, mx, np.inf)
        k = np.where(hit.any(axis=1), hit.argmax(axis=1), -1)
        fb[a:a + idx.size] = np.where(k >= 0, t0 + k * dt, np.nan)
    shots = h["fldr"][sel]
    rows = []
    for s in np.unique(shots):
        m = shots == s
        fit = fit_first_arrival_line(off[sel][m], fb[m])
        if fit is None or fit[1] <= 0:
            continue
        rows.append((fit[0], fit[1], fit[0] + fit[1] * xmax))
    if len(rows) < FA_MIN_SHOTS:
        return {**base, "status": "UNKNOWN", "shots": len(rows),
                "reason": f"only {len(rows)} shot(s) give a first-arrival line (need {FA_MIN_SHOTS})"}
    r = np.array(rows)
    ta = float(np.median(r[:, 2]))
    p10, p90 = (float(v) for v in np.percentile(r[:, 2], [10, 90]))
    slow = float(np.median(r[:, 1]))
    vel = 1.0 / slow
    out = {**base, "shots": len(rows), "t_a_s": round(ta, 4),
           "intercept_s": round(float(np.median(r[:, 0])), 4),
           "slowness_s_per_m": slow, "velocity_m_s": round(vel, 1),
           "t_a_p10_p90_s": [round(p10, 4), round(p90, 4)]}
    if not (FA_VELOCITY_RANGE[0] <= vel <= FA_VELOCITY_RANGE[1]):
        return {**out, "status": "UNKNOWN",
                "reason": f"first-arrival velocity {vel:.0f} m/s is outside {FA_VELOCITY_RANGE}"}
    if p90 - p10 > FA_MAX_SPREAD_S:
        return {**out, "status": "UNKNOWN",
                "reason": (f"the window start varies by {p90 - p10:.2f} s across shots (p10-p90), "
                           f"more than {FA_MAX_SPREAD_S} s")}
    return {**out, "status": "MEASURED"}


def land_first_arrivals(manifest):
    """L0 + L1: the measured first arrivals when S1 applied datum statics, else None."""
    acq = (manifest or {}).get("acquisition_statics") or {}
    fa = acq.get("first_arrivals") or {}
    if acq.get("applied") is True and acq.get("verdict") == "PASS" and fa.get("status") == "MEASURED":
        return fa
    return None


def _write_headers(path, geom, sstat, gstat, tstat):
    """Rewrite sstat/gstat/tstat of a product this module made (domain code only)."""
    order = geom.get("_order", "<")
    raw = np.fromfile(path, dtype=np.uint8).reshape(geom["ntr"], geom["trace_bytes"])
    for off, vals in ((98, sstat), (100, gstat), (102, tstat)):
        raw[:, off:off + 2] = np.asarray(vals, dtype=order + "i2").view(np.uint8).reshape(-1, 2)
    path.write_bytes(raw.tobytes())


def apply(manifest, dataset_id, src, run_id):
    """S1. Returns (path_to_use, record). Files without source/receiver statics pass through."""
    geom = sufile.geometry(src)
    h = _hdr(src, geom, ["sstat", "gstat", "tstat"])
    sstat, gstat, tstat = (h[k].astype(np.int64) for k in ("sstat", "gstat", "tstat"))
    if not (np.any(sstat) or np.any(gstat)):
        prior = (manifest or {}).get("acquisition_statics") or {}
        if prior.get("applied") is True:
            # v0.33 R2: S1 applied them at sort_cmp to the file this one is (or derives from)
            return src, {"applied": False, "status": "APPLIED_AT_SORT_CMP", "rule": "S1 (v0.32) / R2 (v0.33)",
                         "reason": ("the acquisition statics were applied at sort_cmp (S1, "
                                    f"first-break intercept {prior.get('intercept_before_s')} -> "
                                    f"{prior.get('intercept_after_s')} s); not applied again"),
                         "sort_cmp_record": {k: prior.get(k) for k in (
                             "verdict", "intercept_before_s", "intercept_after_s", "total_range_ms",
                             "output")}}
        reason = "no source or receiver statics in headers"
        if np.any(tstat):
            v = np.unique(tstat)
            reason += ((f"; tstat = {int(v[0])} ms" if v.size == 1 else
                        f"; tstat {int(v.min())}-{int(v.max())} ms")
                       + " is recorded as already applied (SEG-Y total static applied) and is left alone")
        return src, {"applied": False, "reason": reason, "rule": "S1 (v0.32)"}
    bad = np.flatnonzero(tstat != sstat + gstat)
    if bad.size:
        raise ValueError(f"Acquisition statics are inconsistent: {bad.size} trace(s) have "
                         "tstat != sstat+gstat. Refusing to apply them.")
    before = first_break_intercept(src, geom)
    corrected = safe_output_path(as_rel(config.WORK_DIR / dataset_id /
                                        f"{dataset_id}_cmp_sorted_statics.su"), overwrite=True)
    args = runner.validate_params({"hdrs": 1, "sign": SIGN_SEGY})
    result = runner.run_trusted("sustatic", args, stdout_path=corrected, stdin_path=src)
    cgeom = sufile.geometry(corrected)
    zeros = np.zeros(cgeom["ntr"], dtype=np.int64)
    _write_headers(corrected, cgeom, zeros, zeros, tstat)
    after = first_break_intercept(corrected, cgeom)
    b, a = before.get("intercept_s"), after.get("intercept_s")
    ok = (b is not None and a is not None and abs(a) < abs(b)) or governance.off()
    record = {"rule": "S1 (v0.32): T' = T + s (sustatic hdrs=1 sign=-1), gated by the near-offset "
                      "first-break intercept moving toward zero",
              "source_range_ms": [int(sstat.min()), int(sstat.max())],
              "receiver_range_ms": [int(gstat.min()), int(gstat.max())],
              "total_range_ms": [int(tstat.min()), int(tstat.max())],
              "intercept_before_s": b, "intercept_after_s": a,
              "shots_measured": [before.get("shots"), after.get("shots")],
              "elapsed_s": result.get("elapsed_s"), "algorithm_version": ACQSTATICS_VERSION}
    if ok:
        evidence.add_artifact(manifest, "cmp_static_corrected", corrected,
                              "acquisition-static-corrected", parents=[as_rel(src)], run_id=run_id)
        # v0.33 L1: the land reflection window, measured on the corrected gathers
        return corrected, {**record, "applied": True, "verdict": "PASS", "output": as_rel(corrected),
                           "first_arrivals": first_arrivals(corrected, cgeom)}
    # the statics would move the first breaks away from the datum: not applied, and removed from the headers so
    # that nothing applies them later; the gathers stay uncorrected
    plain = safe_output_path(as_rel(config.WORK_DIR / dataset_id /
                                    f"{dataset_id}_cmp_sorted_nostatics.su"), overwrite=True)
    plain.write_bytes(src.read_bytes())
    _write_headers(plain, geom, np.zeros_like(sstat), np.zeros_like(gstat), np.zeros_like(tstat))
    return plain, {**record, "applied": False, "verdict": "FAIL",
                   "reason": ("applying the header statics in the SEG-Y sense moves the near-offset "
                              "first-break intercept away from zero "
                              f"({b} -> {a} s); the file's sign convention contradicts SEG-Y, so "
                              "they are not applied and the gathers stay uncorrected"),
                   "output": as_rel(plain)}
