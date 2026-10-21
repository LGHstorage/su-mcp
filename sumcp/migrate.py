"""Post-stack time migration behind a gate (v0.24)."""

from __future__ import annotations

import json
import shutil

import numpy as np

from . import config, evidence, governance, provenance, runner, sanity, sufile
from . import conditioning as K
from . import stack as S
from .paths import as_rel, safe_input_path, safe_output_path

MIGRATE_VERSION = "migrate-0.4"
METHODS = ("phase_shift", "phase_shift_blend", "phase_shift_smooth",
           "depth_convert", "depth_pspi")      # v0.28: the last two are depth (depth.py)
DEFAULT_METHOD = "phase_shift_smooth"   # v0.27 M6
SMOOTH_LOCATIONS = 5               # v0.27 M6
SIDE_TAPER_TRACES = 10
PAD_FRACTION = 0.5
FOCUS_MIN = 0.5                    # M1
FOCUS_HALF_TRACES = 2
FOCUS_HALF_SAMPLES = 12
SEARCH_HALF_TRACES = 40
SEARCH_HALF_SECONDS = 0.3
IMPULSE_X = (0.25, 0.5, 0.75)
IMPULSE_T = (0.3, 0.5, 0.7)
SENSITIVITY_SCALES = (0.95, 1.05)  # M2
LATERAL_SPREAD_MAX = 0.10          # M3 (v0.25: report only)
APERTURE_DEG = 30.0                # M5
EDGE_FRACTION_MAX = 0.5            # M5
STABILITY_WINDOW_S = 1.0           # M8
STABILITY_MIN = 0.5                # M8

__all__ = ["MIGRATE_VERSION", "METHODS", "DEFAULT_METHOD", "rms_grid", "dix",
           "location_rms", "smooth_locations", "lateral_spread", "impulse_section", "focus",
           "dominant_frequency", "migrate_stack"]


def location_rms(function, t):
    """v_rms(t) of one location on the sample grid (linear, constant outside)."""
    tt = np.array([p["t0_s"] for p in function], dtype=float)
    vv = np.array([p["v_m_s"] for p in function], dtype=float)
    return np.interp(t, tt, vv)


def smooth_locations(loc_vrms, window=SMOOTH_LOCATIONS):
    """v0.27 M6: each location's v_rms(t) replaced by the sample-by-sample median of the `window` locations
    nearest in order (window shifted inside the line at the ends; every location when there are `window` or
    fewer)."""
    arr = np.stack([np.asarray(v, dtype=float) for v in loc_vrms])
    n = arr.shape[0]
    out = []
    for i in range(n):
        if n <= window:
            lo, hi = 0, n
        else:
            lo = max(0, min(i - window // 2, n - window))
            hi = lo + window
        out.append(np.median(arr[lo:hi], axis=0))
    return out


def knot_spacing(function):
    """Median spacing of a location's control points (s)."""
    tt = np.array([p["t0_s"] for p in function], dtype=float)
    return float(np.median(np.diff(tt))) if tt.size > 1 else 0.0


def time_smooth(v, length_s, dt):
    """v0.27+ M7: boxcar in time (edges held), length in seconds."""
    k = int(round(length_s / dt))
    v = np.asarray(v, dtype=float)
    if k <= 1:
        return v.copy()
    ker = np.ones(k) / k
    return np.convolve(np.pad(v, k, mode="edge"), ker, "same")[k:-k]


def m7_velocities(locs, t, dt):
    """M6 then M7: the migration v_rms per location (v0.31)."""
    loc_vrms = smooth_locations([location_rms(l["function"], t) for l in locs])
    return [time_smooth(v, knot_spacing(l["function"]), dt) for l, v in zip(locs, loc_vrms)]


def stability_windows(mig, alts, t, t_from, width=STABILITY_WINDOW_S):
    """M8: per window, the lower of the median trace correlations with the +-5% images."""
    out = []
    a = t_from
    while a < t[-1] - 1e-9:
        b = min(t[-1] + 1e-9, a + width)
        i0, i1 = int(np.searchsorted(t, a)), int(np.searchsorted(t, b))
        vals = []
        for alt in alts:
            rs = []
            for x, y in zip(mig[:, i0:i1], alt[:, i0:i1]):
                nx, ny = np.linalg.norm(x), np.linalg.norm(y)
                if nx > 0 and ny > 0 and np.isfinite(nx) and np.isfinite(ny):
                    r = float(x @ y / (nx * ny))
                    if np.isfinite(r):
                        rs.append(r)
            vals.append(float(np.median(rs)) if rs else None)
        good = [v for v in vals if v is not None]
        out.append({"from_s": round(a, 3), "to_s": round(float(b), 3),
                    "stability": round(min(good), 3) if good else None})
        a = b
    return out


def grid_from(loc_cdps, loc_vrms, cdps):
    """v_rms for every output cdp from per-location functions: 1/v^2 linear in cdp."""
    xs = np.asarray(loc_cdps, dtype=float)
    s = 1.0 / np.stack(loc_vrms) ** 2
    cdps = np.asarray(cdps, dtype=float)
    out = np.empty((cdps.size, s.shape[1]))
    for i in range(s.shape[1]):
        out[:, i] = np.interp(cdps, xs, s[:, i])
    return 1.0 / np.sqrt(out)


def rms_grid(locations, cdps, t):
    """v_rms for every output cdp: 1/v^2 linear in cdp between locations."""
    locs = sorted(locations, key=lambda l: int(l["cdp"]))
    xs = np.array([int(l["cdp"]) for l in locs], dtype=float)
    s = np.stack([1.0 / location_rms(l["function"], t) ** 2 for l in locs])   # (nloc, ns)
    cdps = np.asarray(cdps, dtype=float)
    out = np.empty((cdps.size, t.size))
    for i in range(t.size):
        out[:, i] = np.interp(cdps, xs, s[:, i])
    return 1.0 / np.sqrt(out)


def dix(vrms, dt):
    """Interval velocity from RMS velocity on a regular time grid starting at 0."""
    vrms = np.asarray(vrms, dtype=float)
    n = vrms.size
    t = np.arange(n) * dt
    tv2 = t * vrms ** 2
    vint2 = np.empty(n)
    vint2[0] = vrms[0] ** 2
    vint2[1:] = np.diff(tv2) / dt
    return np.sqrt(np.clip(vint2, (0.5 * vrms.min()) ** 2, None))


def lateral_spread(locations, supported, t):
    """M3: max over supported times of (max - min) / median v_rms across locations."""
    best, at = 0.0, None
    funcs = {int(l["cdp"]): location_rms(l["function"], t) for l in locations}
    for i, ti in enumerate(t):
        vals = [f[i] for c, f in funcs.items() if (supported.get(c) or 0) >= ti > 0]
        if len(vals) < 2:
            continue
        v = np.asarray(vals)
        spread = float((v.max() - v.min()) / np.median(v))
        if spread > best:
            best, at = spread, float(ti)
    return {"spread": round(best, 4), "at_s": at}


def edge_fraction(ntr, dx, t, v, t_from, degrees=APERTURE_DEG):
    """M5: share of (trace, t) cells, t >= t_from, closer to a line end than the aperture A(t) = v(t) t / 2
    tan(degrees), where the operator runs off the line."""
    x = np.arange(ntr) * dx
    d = np.minimum(x - x[0], x[-1] - x)
    sel = t >= t_from
    if not sel.any():
        return {"fraction": None, "reason": "no samples below the last direct arrival"}
    a = v[sel] * t[sel] / 2.0 * np.tan(np.radians(degrees))
    frac = float((d[:, None] < a[None, :]).mean())
    return {"fraction": round(frac, 3), "aperture_deg": degrees,
            "line_length_m": round(float(x[-1] - x[0]), 1),
            "aperture_at_end_m": round(float(a[-1]), 1), "from_s": round(float(t_from), 3)}


def dominant_frequency(data, dt, lo=5.0, hi=60.0):
    spec = (np.abs(np.fft.rfft(data, axis=1)) ** 2).sum(axis=0)
    f = np.fft.rfftfreq(data.shape[1], dt)
    band = (f >= lo) & (f <= hi)
    return float(f[band][np.argmax(spec[band])])


def _ricker(tt, f0):
    a = (np.pi * f0 * tt) ** 2
    return (1 - 2 * a) * np.exp(-a)


def impulse_section(ntr, ns, dt, dx, f0, apexes, vrms_at):
    """Zero-offset diffractions for apexes [(trace, t0)], curvature from vrms_at(trace, t0)."""
    t = np.arange(ns) * dt
    x = np.arange(ntr) * dx
    sec = np.zeros((ntr, ns))
    for i0, t0 in apexes:
        v = vrms_at(i0, t0)
        td = np.sqrt(t0 ** 2 + 4 * (x - x[i0]) ** 2 / v ** 2)
        sec += _ricker(t[None, :] - td[:, None], f0) * (t0 / td)[:, None]
    return sec


def focus_windows(dt, dx, period, v_apex):
    """Windows that scale with the wavelet (v0.24 addendum 1)."""
    ht = max(1, int(round(0.5 * period / dt)))
    hx = max(FOCUS_HALF_TRACES, int(round(v_apex * period / 4.0 / dx)))
    st = max(int(round(SEARCH_HALF_SECONDS / dt)), int(round(2 * period / dt)))
    sx = max(SEARCH_HALF_TRACES, 4 * hx)
    return ht, hx, st, sx


def focus(mig, i0, t0, dt, period, dx=None, v_apex=None):
    """M1 for one apex: energy near the migrated peak, and where the peak is."""
    if dx is None or v_apex is None:
        ht, hx, st, sx = FOCUS_HALF_SAMPLES, FOCUS_HALF_TRACES, \
            int(round(SEARCH_HALF_SECONDS / dt)), SEARCH_HALF_TRACES
    else:
        ht, hx, st, sx = focus_windows(dt, dx, period, v_apex)
    k0 = int(round(t0 / dt))
    a, b = max(0, i0 - sx), min(mig.shape[0], i0 + sx + 1)
    c, d = max(0, k0 - st), min(mig.shape[1], k0 + st + 1)
    win = mig[a:b, c:d]
    e = win ** 2
    total = float(e.sum())
    j, m = np.unravel_index(int(np.argmax(np.abs(win))), win.shape)
    near = float(e[max(0, j - hx):j + hx + 1, max(0, m - ht):m + ht + 1].sum())
    dtr = int(a + j - i0)
    dts = (c + m - k0) * dt
    ratio = near / total if total > 0 else 0.0
    tol_x = max(1, hx // 2)
    ok = ratio >= FOCUS_MIN and abs(dtr) <= tol_x and abs(dts) <= period / 4
    return {"apex_trace": int(i0), "apex_t_s": round(float(t0), 3), "focus": round(ratio, 3),
            "peak_shift_traces": dtr, "peak_shift_ms": round(1000 * float(dts), 1),
            "window_traces": int(hx), "window_samples": int(ht),
            "tolerance_traces": int(tol_x), "ok": bool(ok)}


class _Runner:
    """Runs sumigps on sections written in the stack's own byte order."""

    def __init__(self, stack_path, geom, tmp, dx):
        self.stack_path, self.geom, self.tmp, self.dx = stack_path, geom, tmp, dx
        self.raw = np.fromfile(stack_path, dtype=np.uint8).reshape(geom["ntr"], geom["trace_bytes"])
        self.n = 0

    def write(self, data):
        self.n += 1
        p = self.tmp / f"in_{self.n}.su"
        p.write_bytes(K.write_block(self.raw, data, self.geom))
        return p

    def migrate(self, src, vint):
        self.n += 1
        vf = self.tmp / f"v_{self.n}.bin"
        np.asarray(vint, dtype="=f4").tofile(vf)
        out = self.tmp / f"mig_{self.n}.su"
        ntr = self.geom["ntr"]
        args = runner.validate_params({"dx": round(float(self.dx), 3),
                                       "nxpad": int(round(PAD_FRACTION * ntr)),
                                       "ltaper": min(SIDE_TAPER_TRACES, max(0, ntr // 4))})
        args.append(f"vfile={vf}")      # built here, never from a caller's string
        runner.run_trusted("sumigps", args, stdout_path=out, stdin_path=src)
        g = sufile.geometry(out)
        return sufile.read_traces(out, np.arange(g["ntr"]), g).astype(np.float64)


def _blend(migs, loc_cdps, cdps):
    """Each output trace from the two bracketing location migrations (linear in cdp)."""
    loc_cdps = np.asarray(loc_cdps, dtype=float)
    out = np.zeros_like(migs[0])
    for i, c in enumerate(np.asarray(cdps, dtype=float)):
        if c <= loc_cdps[0]:
            out[i] = migs[0][i]
        elif c >= loc_cdps[-1]:
            out[i] = migs[-1][i]
        else:
            k = int(np.searchsorted(loc_cdps, c)) - 1
            w = (c - loc_cdps[k]) / (loc_cdps[k + 1] - loc_cdps[k])
            out[i] = (1 - w) * migs[k][i] + w * migs[k + 1][i]
    return out


def _migrate(run, src, method, locs, loc_vint, median_vint, cdps, scale=1.0):
    if method == "phase_shift":
        return run.migrate(src, scale * median_vint)
    if method == "phase_shift_smooth" and len(loc_vint) <= SMOOTH_LOCATIONS:
        return run.migrate(src, scale * loc_vint[0])     # one common function
    migs = [run.migrate(src, scale * v) for v in loc_vint]
    return _blend(migs, [int(l["cdp"]) for l in locs], cdps)


def _refuse_corrupt(stack_path, geom):
    """v0.30 Q0: migration spreads one sample over the whole aperture."""
    q0 = sanity.scan(stack_path, geom)
    if q0["corrupt_count"]:
        raise ValueError(
            f"Q0: the stack holds {q0['corrupt_count']} corrupt trace(s) at CDP "
            f"{q0['corrupt_cdps'][:10]} (non-finite or beyond 120 dB of the median trace RMS); "
            "migration would spread them over its aperture. Run condition_gathers "
            "[{\"op\": \"kill_corrupt\"}], re-pick and restack first. Refused.")


def _median_trace_corr(a, b, i0):
    rs = []
    for x, y in zip(a[:, i0:], b[:, i0:]):
        nx, ny = np.linalg.norm(x), np.linalg.norm(y)
        if nx > 0 and ny > 0 and np.isfinite(nx) and np.isfinite(ny):
            r = float(x @ y / (nx * ny))
            if np.isfinite(r):
                rs.append(r)
    return round(float(np.median(rs)), 3) if rs else None      # v0.30 N0: never NaN


def migrate_stack(dataset_id: str, *, method: str = DEFAULT_METHOD,
                  overwrite: bool = False) -> dict:
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    if method in ("depth_convert", "depth_pspi"):
        from . import depth
        return depth.depth_image(dataset_id, method, overwrite=overwrite)
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["velocity.validated", "stack.completed"], "Migration")
    stack_cap = evidence.get_capability(manifest, "stack.completed")
    stack_ev = stack_cap.get("evidence") or {}
    stack_path = safe_input_path(evidence.get_artifact(manifest, "stack")["path"])
    geom = sufile.geometry(stack_path)
    if not governance.off():
        _refuse_corrupt(stack_path, geom)
    if abs(geom["t_start_s"]) > 1e-9:
        raise ValueError(f"The stack starts at {geom['t_start_s']} s; sumigps assumes the "
                         "first sample is at t = 0. Refused.")
    model = json.loads(safe_input_path(
        evidence.get_artifact(manifest, "velocity_model")["path"]).read_text(encoding="utf-8"))
    locs = sorted(model["locations"], key=lambda l: int(l["cdp"]))
    if not locs:
        raise ValueError("The velocity model has no valid location.")
    bin_m = ((evidence.get_capability(manifest, "geometry.cmp_assigned") or {})
             .get("evidence", {}) or {}).get("bin_size_m")
    if not bin_m:
        raise ValueError("build_cmp recorded no bin size; the trace spacing is unknown.")
    cdps = np.asarray(sufile.read_header_columns(stack_path, ["cdp"], geom)["cdp"])
    steps = np.diff(cdps)
    if cdps.size < 8 or not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError("The stack must hold at least 8 traces sorted by cdp.")
    step = float(np.median(np.abs(steps)))
    dx = float(bin_m) * step
    ns, dt, ntr = geom["ns"], geom["dt_s"], geom["ntr"]
    t = np.arange(ns) * dt

    loc_vrms = [location_rms(l["function"], t) for l in locs]
    loc_cdps = [int(l["cdp"]) for l in locs]
    if method == "phase_shift_smooth":
        loc_vrms = m7_velocities(locs, t, dt)          # v0.31 M7
        grid = grid_from(loc_cdps, loc_vrms, cdps)
    else:
        grid = rms_grid(locs, cdps, t)
    loc_vint = [dix(v, dt) for v in loc_vrms]
    median_vrms = np.median(grid, axis=0)
    median_vint = dix(median_vrms, dt)
    vel_ev = (evidence.get_capability(manifest, "velocity.validated") or {}).get("evidence", {}) or {}
    supported = {int(c): v for c, v in (vel_ev.get("supported_to_s") or {}).items()}
    spread = lateral_spread(locs, supported, t)

    data = sufile.read_traces(stack_path, np.arange(ntr), geom).astype(np.float64)
    f0 = dominant_frequency(data, dt)
    period = 1.0 / f0
    tmp = config.WORK_DIR / dataset_id / f"_migrate_tmp_{run_id}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        run = _Runner(stack_path, geom, tmp, dx)
        # M1: the same operator and velocities on diffractions alone
        record_end = ns * dt
        apexes = [(int(round(fx * (ntr - 1))), round(ft * record_end / dt) * dt)
                  for fx, ft in zip(IMPULSE_X, IMPULSE_T)]
        if method == "phase_shift":
            vrms_at = lambda i, t0: float(np.interp(t0, t, median_vrms))
        else:
            vrms_at = lambda i, t0: float(np.interp(t0, t, grid[i]))
        imp = impulse_section(ntr, ns, dt, dx, f0, apexes, vrms_at)
        imp_mig = _migrate(run, run.write(imp), method, locs, loc_vint, median_vint, cdps)
        foci = [focus(imp_mig, i0, t0, dt, period, dx, vrms_at(i0, t0)) for i0, t0 in apexes]
        m1_ok = all(f["ok"] for f in foci)
        release = m1_ok or governance.off()      # baseline01 C0: always released

        src = run.write(data)
        mig = _migrate(run, src, method, locs, loc_vint, median_vint, cdps)
        t_direct = float(stack_ev.get("velocity_support", {}).get("last_direct_arrival_s") or 0.0)
        i0 = min(ns - 1, int(round(t_direct / dt)))
        sens = {}
        alts = []
        for sc in SENSITIVITY_SCALES:
            alt = _migrate(run, src, method, locs, loc_vint, median_vint, cdps, scale=sc)
            sens[f"x{sc:.2f}"] = _median_trace_corr(mig, alt, i0)
            alts.append(alt)
        stab = stability_windows(mig, alts, t, t_direct)       # v0.31 M8
        del alts
        dst = safe_output_path(as_rel(config.RESULT_DIR / f"{dataset_id}_mig_{method}.su"),
                               overwrite=overwrite)
        audit = config.WORK_DIR / dataset_id / f"{dataset_id}_mig_{method}_rejected.su"
        target = dst if release else audit
        target.write_bytes(K.write_block(run.raw, mig, geom))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rel = stack_ev.get("reliability") or {}
    quality = list(rel.get("quality_reasons") or [])
    provenance_r = list(rel.get("provenance_reasons") or [])
    if "quality_reasons" not in rel and rel.get("level") == "WARN":
        quality = list(rel.get("reasons") or [])       # a stack older than v0.23 tiers
    # v0.25: M3 is a report; M5 warns when the aperture runs off the line
    edge = edge_fraction(ntr, dx, t, median_vrms, t_direct)
    if edge.get("fraction") is not None and edge["fraction"] > EDGE_FRACTION_MAX:
        quality.append(f"M5 migration aperture truncated by the line ends over "
                       f"{100 * edge['fraction']:.0f}% of the section (> {100 * EDGE_FRACTION_MAX:.0f}%)")
    unstable = [w for w in stab if w["stability"] is not None and w["stability"] < STABILITY_MIN]
    if unstable:
        quality.append(f"M8 image unstable to +-5% velocity below {unstable[0]['from_s']:.1f} s "
                       f"(stability {unstable[0]['stability']:.2f} < {STABILITY_MIN}); read the "
                       "stack there")
    level = "WARN" if quality else ("CAUTION" if provenance_r else "OK")
    reliability = {"level": level, "quality_reasons": quality,
                   "provenance_reasons": provenance_r,
                   "reasons": quality + provenance_r, "rule": "v0.31 inherited + M5 + M8"}
    ev = {"method": method, "program": "sumigps", "dx_m": round(dx, 3),
          "dominant_hz": round(f0, 2), "impulse_gate": {"rule": "M1 (windows scale with T)", "focus_min": FOCUS_MIN,
                                                        "apexes": foci, "verdict": "PASS" if m1_ok else "FAIL"},
          "velocity_sensitivity": {"rule": "M2 (report)", "median_trace_corr": sens},
          "stability": {"rule": "M8: per 1 s window, the lower median trace correlation with the "
                                "+-5% velocity images; WARN below 0.5", "windows": stab},
          "lateral_variation": {"rule": "M3 (report)", **spread},
          "aperture": {"rule": "M5", **edge, "limit": EDGE_FRACTION_MAX},
          "locations": [int(l["cdp"]) for l in locs],
          **({"migration_velocity": {
              "rule": "M6 (v0.27): sample-by-sample median of the v_rms of the "
                      f"{min(SMOOTH_LOCATIONS, len(locs))} nearest analysis locations; "
                      "the stacking velocity is unchanged",
              "window_locations": min(SMOOTH_LOCATIONS, len(locs)),
              "migrations": 1 if len(locs) <= SMOOTH_LOCATIONS else len(locs),
              "time_smoothing": "M7 (v0.31): v_rms smoothed over each location's control-point "
                                "spacing before Dix",
              "time_smoothing_s": [round(knot_spacing(l["function"]), 3) for l in locs]}}
             if method == "phase_shift_smooth" else {}),
          "velocity_support": stack_ev.get("velocity_support"),
          "reliability": reliability, "stack": as_rel(stack_path),
          "output": as_rel(target), "released": bool(release)}
    notes = ([] if m1_ok else ["M1 FAIL: synthetic diffractions did not focus with this "
                               "operator and velocity; the migrated section is kept for "
                               "audit and not released."]) + \
            ([f"Reliability {level}: " + "; ".join(reliability["reasons"])] if level != "OK" else [])
    if release:
        # v0.33.3 I1b: the depth image stretched from the previous time migration no longer refers to anything
        evidence.invalidate_after_migration(manifest, "the time migration was recomputed", MIGRATE_VERSION, run_id)
    evidence.record_product_run(manifest, "migration.completed", bool(release), ev,
                                MIGRATE_VERSION, run_id, artifact=as_rel(target), notes=notes)
    evidence.add_artifact(manifest, f"migration_{method}" if release else f"migration_{method}_rejected",
                          target, "migrated-stack" if release else "migration-rejected",
                          parents=[as_rel(stack_path)], run_id=run_id)
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id, "method": method,
            "released": bool(release), "output": as_rel(target),
            "impulse_gate": ev["impulse_gate"], "velocity_sensitivity": ev["velocity_sensitivity"],
            "stability": ev["stability"],
            "lateral_variation": ev["lateral_variation"], "aperture": ev["aperture"],
            **({"migration_velocity": ev["migration_velocity"]} if "migration_velocity" in ev else {}),
            "reliability": reliability,
            "dx_m": ev["dx_m"], "dominant_hz": ev["dominant_hz"],
            "capabilities": {"migration.completed": evidence.capability_status(
                manifest, "migration.completed")},
            "algorithm_version": MIGRATE_VERSION}
