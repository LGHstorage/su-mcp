"""Depth imaging behind gates (v0.28)."""

from __future__ import annotations

import json
import shutil

import numpy as np

from . import config, evidence, governance, provenance, runner, sufile
from . import conditioning as K
from . import migrate as M
from .paths import as_rel, safe_input_path, safe_output_path

DEPTH_VERSION = "depth-0.3"
DEPTH_METHODS = ("depth_convert", "depth_pspi")
DZ_M = 5.0                               # Z5: the largest depth step


def depth_step(v_min, f_dom):
    """v0.31 Z5: a quarter of the shortest wavelet length in depth (v T / 2 / 4), at most DZ_M and at least 1 m."""
    if not (v_min and f_dom) or v_min <= 0 or f_dom <= 0:
        return DZ_M
    return float(min(DZ_M, max(1.0, np.floor(v_min / (8.0 * f_dom)))))
VINT_MIN, VINT_MAX = 1000.0, 7000.0      # Z2
DEPTH_TOLERANCE = 0.05                   # Z3 (the M2 velocity scale)

__all__ = ["DEPTH_VERSION", "DEPTH_METHODS", "depth_axis", "convert_trace",
           "velocity_depth_grid", "focus_depth", "interval_check", "dmo_accepted",
           "depth_image"]


def depth_axis(vint_t, dt):
    """z at each time sample (two-way time): z(t) = sum v_int dt / 2, z(0) = 0."""
    v = np.asarray(vint_t, dtype=float)
    return np.concatenate([[0.0], np.cumsum(v[:-1] * dt / 2.0)])


def convert_trace(trace, z_of_t, zg):
    """A time trace on the depth grid zg (linear interpolation of t(z); zero below the record)."""
    t_idx = np.arange(len(trace), dtype=float)
    k = np.interp(zg, z_of_t, t_idx, right=np.nan)
    out = np.interp(k, t_idx, trace)
    out[np.isnan(k)] = 0.0
    return out


def velocity_depth_grid(vint_tx, z_tx, zg):
    """v_int(z) for every trace (rows) on zg, held below the record."""
    return np.stack([np.interp(zg, z, v) for v, z in zip(vint_tx, z_tx)])


def interval_check(loc_cdps, loc_vint, supported, t, t_from):
    """Z2: every interval velocity from t_from to each location's supported depth within VINT_MIN-VINT_MAX."""
    bad = []
    for c, v in zip(loc_cdps, loc_vint):
        s = supported.get(int(c))
        if not s:
            continue
        sel = (t >= t_from) & (t <= s)
        if sel.any():
            lo, hi = float(v[sel].min()), float(v[sel].max())
            if lo < VINT_MIN or hi > VINT_MAX:
                bad.append({"cdp": int(c), "min_m_s": round(lo, 1), "max_m_s": round(hi, 1)})
    return {"rule": f"Z2: interval velocity within {VINT_MIN:.0f}-{VINT_MAX:.0f} m/s "
                    "from the last direct arrival to the supported depth",
            "violations": bad, "verdict": "FAIL" if bad else "PASS"}


def dmo_accepted(manifest):
    return any(e.get("accepted") and any((o or {}).get("op") == "dmo"
                                         for o in (e.get("operations") or []))
               for e in manifest.get("conditioning") or [])


def focus_depth(img, i0, z0, dz, wavelength, dx, v_apex):
    """Z1 for one apex, in depth: M1's windows with the wavelet length v T / 2 in place of the period T (half of
    it in depth, v T / 4 laterally)."""
    hz = max(1, int(round(0.5 * wavelength / dz)))
    hx = max(M.FOCUS_HALF_TRACES, int(round(wavelength / 2.0 / dx)))   # v T / 4
    sz = max(int(round(2 * wavelength / dz)), 4 * hz)
    sx = max(M.SEARCH_HALF_TRACES, 4 * hx)
    k0 = int(round(z0 / dz))
    a, b = max(0, i0 - sx), min(img.shape[0], i0 + sx + 1)
    c, d = max(0, k0 - sz), min(img.shape[1], k0 + sz + 1)
    win = img[a:b, c:d]
    e = win ** 2
    total = float(e.sum())
    if total <= 0:
        return {"apex_trace": int(i0), "apex_z_m": round(float(z0), 1), "focus": 0.0, "ok": False}
    j, m = np.unravel_index(int(np.argmax(np.abs(win))), win.shape)
    near = float(e[max(0, j - hx):j + hx + 1, max(0, m - hz):m + hz + 1].sum())
    dtr, dzz = int(a + j - i0), (c + m - k0) * dz
    ratio = near / total
    ok = ratio >= M.FOCUS_MIN and abs(dtr) <= max(1, hx // 2) and abs(dzz) <= wavelength / 4
    return {"apex_trace": int(i0), "apex_z_m": round(float(z0), 1), "focus": round(ratio, 3),
            "peak_shift_traces": dtr, "peak_shift_m": round(float(dzz), 1),
            "window_traces": int(hx), "window_samples": int(hz), "ok": bool(ok)}


def _depth_block(raw, data, geom, dz):
    """Trace bytes: the stack's headers with ns = nz, dt = dz in mm, d1 = dz (m)."""
    order = geom.get("_order", "<")
    ntr, nz = data.shape
    hdr = raw[:, :sufile.HEADER_BYTES].copy()
    hdr[:, 114:116] = np.frombuffer(np.array([nz], dtype=order + "u2").tobytes(), np.uint8)
    hdr[:, 116:118] = np.frombuffer(np.array([int(round(dz * 1000))], dtype=order + "u2").tobytes(),
                                    np.uint8)
    hdr[:, 180:184] = np.frombuffer(np.array([dz], dtype=order + "f4").tobytes(), np.uint8)
    samples = np.asarray(data, dtype=order + "f4").view(np.uint8).reshape(ntr, -1)
    return np.concatenate([hdr, samples], axis=1).tobytes()


def _pspi(tmp, src, vxz, nz, dz, dx, tag):
    vf = tmp / f"vz_{tag}.bin"
    np.asarray(vxz, dtype="=f4").tofile(vf)       # vfile[iz][ix]: x fastest
    out = tmp / f"pspi_{tag}.su"
    args = runner.validate_params({"nz": int(nz), "dz": round(float(dz), 3), "dx": round(float(dx), 3)})
    args.append(f"vfile={vf}")                     # built here, never from a caller's string
    runner.run_trusted("sumigpspi", args, stdout_path=out, stdin_path=src)
    g = sufile.geometry(out)
    return sufile.read_traces(out, np.arange(g["ntr"]), g).astype(np.float64)


def depth_image(dataset_id: str, method: str, overwrite: bool = False) -> dict:
    if method not in DEPTH_METHODS:
        raise ValueError(f"method must be one of {DEPTH_METHODS}")
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["velocity.validated", "stack.completed"], "Depth imaging")
    stack_ev = (evidence.get_capability(manifest, "stack.completed") or {}).get("evidence") or {}
    stack_path = safe_input_path(evidence.get_artifact(manifest, "stack")["path"])
    geom = sufile.geometry(stack_path)
    M._refuse_corrupt(stack_path, geom)
    if abs(geom["t_start_s"]) > 1e-9:
        raise ValueError(f"The stack starts at {geom['t_start_s']} s; depth imaging assumes t = 0 "
                         "at the first sample. Refused.")
    tmig_path = None
    if method == "depth_convert":
        art = (manifest.get("artifacts") or {}).get("migration_phase_shift_smooth")
        if not art:
            raise ValueError("depth_convert stretches the released M6 time migration; run "
                             "migrate_stack with method 'phase_shift_smooth' first (it must pass M1).")
        stale = evidence.superseded(manifest, "migration_phase_shift_smooth")
        if stale and not governance.off():
            raise ValueError("depth_convert stretches the released M6 time migration, and the one on file was "
                             f"made before {stale['reason']} (I1); run migrate_stack with method "
                             "'phase_shift_smooth' again on the current stack first.")
        tmig_path = safe_input_path(art["path"])
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
    dx = float(bin_m) * float(np.median(np.abs(steps)))
    ns, dt, ntr = geom["ns"], geom["dt_s"], geom["ntr"]
    t = np.arange(ns) * dt

    # M6 + M7 velocity (v0.31), Dix, z(t)
    loc_cdps = [int(l["cdp"]) for l in locs]
    loc_vrms = M.m7_velocities(locs, t, dt)
    loc_vint = [M.dix(v, dt) for v in loc_vrms]
    grid = M.grid_from(loc_cdps, loc_vrms, cdps)                 # (ntr, ns) v_rms
    vint_tx = np.stack([M.dix(v, dt) for v in grid])
    z_tx = np.stack([depth_axis(v, dt) for v in vint_tx])

    vel_ev = (evidence.get_capability(manifest, "velocity.validated") or {}).get("evidence", {}) or {}
    supported = {int(c): v for c, v in (vel_ev.get("supported_to_s") or {}).items()}
    t_direct = float((stack_ev.get("velocity_support") or {}).get("last_direct_arrival_s") or 0.0)
    data = sufile.read_traces(stack_path, np.arange(ntr), geom).astype(np.float64)
    f0 = M.dominant_frequency(data, dt)
    below = t >= t_direct
    v_min = float(vint_tx[:, below].min()) if below.any() else float(vint_tx.min())
    dz = depth_step(v_min, f0)                                   # Z5
    nz = int(np.ceil(float(z_tx[:, -1].max()) / dz)) + 1
    zg = np.arange(nz) * dz
    z2 = interval_check(loc_cdps, loc_vint, supported, t, t_direct)
    if z2["verdict"] == "FAIL" and not governance.off():
        raise ValueError("Z2: interval velocities outside "
                         f"{VINT_MIN:.0f}-{VINT_MAX:.0f} m/s inside the supported window at "
                         f"{[b['cdp'] for b in z2['violations']]}; Dix has blown up and a depth "
                         "section would be fiction. Refused.")

    raw = np.fromfile(stack_path, dtype=np.uint8).reshape(ntr, geom["trace_bytes"])
    tmp = config.WORK_DIR / dataset_id / f"_depth_tmp_{run_id}"
    tmp.mkdir(parents=True, exist_ok=True)
    z1 = None
    try:
        if method == "depth_convert":
            tg = sufile.geometry(tmig_path)
            tmig = sufile.read_traces(tmig_path, np.arange(tg["ntr"]), tg).astype(np.float64)
            if tmig.shape != (ntr, ns):
                raise ValueError("The released time migration does not match the stack's shape.")
            img = np.stack([convert_trace(tr, z, zg) for tr, z in zip(tmig, z_tx)])
            released = True
        else:
            period = 1.0 / f0
            med_vrms = np.median(grid, axis=0)
            med_vint = M.dix(med_vrms, dt)
            med_z = depth_axis(med_vint, dt)
            med_vz = np.interp(zg, med_z, med_vint)
            record_end = ns * dt
            apexes = [(int(round(fx * (ntr - 1))), round(ft * record_end / dt) * dt)
                      for fx, ft in zip(M.IMPULSE_X, M.IMPULSE_T)]
            imp = M.impulse_section(ntr, ns, dt, dx, f0, apexes,
                                    lambda i, t0: float(np.interp(t0, t, med_vrms)))
            src_imp = tmp / "imp.su"
            src_imp.write_bytes(K.write_block(raw, imp, geom))
            imp_img = _pspi(tmp, src_imp, np.repeat(med_vz[:, None], ntr, axis=1), nz, dz, dx, "imp")
            foci = []
            for i0, t0 in apexes:
                z0 = float(np.interp(t0, t, med_z))
                v0 = float(np.interp(t0, t, med_vint))
                foci.append(focus_depth(imp_img, i0, z0, dz, v0 * period / 2.0, dx, v0))
            released = all(f["ok"] for f in foci) or governance.off()
            z1 = {"rule": "Z1 (depth impulse, M1 windows in depth)", "focus_min": M.FOCUS_MIN,
                  "apexes": foci, "verdict": "PASS" if released else "FAIL"}
            vxz = velocity_depth_grid(vint_tx, z_tx, zg).T            # (nz, ntr)
            img = _pspi(tmp, stack_path, vxz, nz, dz, dx, "data")
        dst = safe_output_path(as_rel(config.RESULT_DIR / f"{dataset_id}_mig_{method}.su"),
                               overwrite=overwrite)
        audit = config.WORK_DIR / dataset_id / f"{dataset_id}_mig_{method}_rejected.su"
        target = dst if released else audit
        target.write_bytes(_depth_block(raw, img, geom, dz))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rel = stack_ev.get("reliability") or {}
    quality = list(rel.get("quality_reasons") or [])
    provenance_r = list(rel.get("provenance_reasons") or [])
    # v0.28.1: the aperture of a depth product runs off the line exactly as the time migration's does, so M5
    # applies to it too
    edge = M.edge_fraction(ntr, dx, t, np.median(grid, axis=0), t_direct)
    if edge.get("fraction") is not None and edge["fraction"] > M.EDGE_FRACTION_MAX:
        quality.append(f"M5 migration aperture truncated by the line ends over "
                       f"{100 * edge['fraction']:.0f}% of the section (> {100 * M.EDGE_FRACTION_MAX:.0f}%)")
    if not dmo_accepted(manifest):
        quality.append("Z4 no DMO pass was accepted on this dataset: stacking velocities on dipping "
                       "reflectors exceed the migration velocity, and depth is biased deep")
    level = "WARN" if quality else ("CAUTION" if provenance_r else "OK")
    reliability = {"level": level, "quality_reasons": quality, "provenance_reasons": provenance_r,
                   "reasons": quality + provenance_r, "rule": "stack reliability + M5 + Z4"}
    deepest = max((v for v in supported.values() if v), default=None)
    z_supported = None
    if deepest:
        z_supported = round(float(np.median([np.interp(deepest, t, z) for z in z_tx])), 1)
    tolerance = {"rule": "Z3 (report)", "fraction": DEPTH_TOLERANCE,
                 "statement": (f"Depths are good to about +-{100 * DEPTH_TOLERANCE:.0f}% of depth where the "
                               "velocity is measured" + (f" (to about {z_supported:.0f} m)" if z_supported else "")
                               + "; deeper, the velocity is held and depth is extrapolated.")}
    ev = {"method": method, "dz_m": dz, "depth_step_rule": "Z5: min(5 m, floor(v_min / (8 f_dom))), >= 1 m", "v_min_m_s": round(v_min, 1), "dominant_hz": round(f0, 2), "nz": nz, "dx_m": round(dx, 3),
          "velocity": "M6 + M7 smoothed v_rms, Dix, z = sum(v_int dt/2)",
          "interval_velocity": z2, "depth_tolerance": tolerance, "aperture": {"rule": "M5", **edge},
          **({"impulse_gate": z1} if z1 else {"inherits": "M1 of the released phase_shift_smooth migration",
                                              "time_migration": as_rel(tmig_path)}),
          "dmo_accepted": dmo_accepted(manifest), "reliability": reliability,
          "output": as_rel(target), "released": bool(released)}
    notes = ([] if released else ["Z1 FAIL: synthetic diffractions did not focus in depth; kept for audit."]) + \
        ([f"Reliability {level}: " + "; ".join(reliability["reasons"])] if level != "OK" else [])
    evidence.record_product_run(manifest, "depth.completed", bool(released), ev, DEPTH_VERSION,
                                run_id, artifact=as_rel(target), notes=notes)
    evidence.add_artifact(manifest, f"depth_{method}" if released else f"depth_{method}_rejected",
                          target, "depth-image" if released else "depth-rejected",
                          parents=[as_rel(stack_path)], run_id=run_id)
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id, "method": method, "released": bool(released),
            "output": as_rel(target), **({"impulse_gate": z1} if z1 else {}),
            "interval_velocity": z2, "depth_tolerance": tolerance, "reliability": reliability,
            "dz_m": dz, "nz": nz, "dmo_accepted": ev["dmo_accepted"],
            "capabilities": {"depth.completed": evidence.capability_status(manifest, "depth.completed")},
            "algorithm_version": DEPTH_VERSION}
