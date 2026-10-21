"""Velocity analysis, NMO and stack, each behind what the last one proved."""

from __future__ import annotations

import json
import shutil

import numpy as np

from . import acqstatics, config, evidence, governance, provenance, runner, sanity, sufile, velocity
from . import reflection as R
from .paths import as_rel, safe_input_path, safe_output_path

STACK_VERSION = "stack-0.16"

__all__ = ["STACK_VERSION", "pick_velocity", "apply_nmo", "stack_cmp", "time_datum", "signal_to_noise", "half_stack_correlations", "velocity_support", "reflection_window", "support_fraction",
           "choose_analysis_locations", "grade_velocity_locations",
           "BudgetExhausted", "MAX_VELOCITY_ANALYSES", "reliability_warning",
           "feasibility_disclosure", "W1_CEILING", "W3_FRACTION", "W4_FRACTION", "lateral_fraction",
           "DENSITY_SPACING_M", "MAX_LOCATIONS", "density_count", "required_valid",
           "area_support_fraction"]

# v0.19: every velocity analysis is another chance to pass by luck, so a dataset gets a fixed number of them
# (pick_velocity and refine_velocity calls).
MAX_VELOCITY_ANALYSES = 6   # v0.26: DMO adds one velocity model (pick + refine)


class BudgetExhausted(ValueError):
    """A pre-declared iteration budget is spent (results/v0190/CRITERIA.md)."""


def _set(manifest, name, ok, evidence_dict, run_id, notes=(), artifact=None):
    status = {True: evidence.PASS, False: evidence.FAIL, None: evidence.UNKNOWN}[ok]
    return evidence.set_capability(manifest, name, status, evidence_dict,
                                   STACK_VERSION, run_id, artifact=artifact,
                                   notes=list(notes))


def _gathers(path, geom, cdp_values):
    columns = sufile.read_header_columns(path, ["cdp", "offset"], geom)
    cdp = np.asarray(columns["cdp"])
    offset = np.abs(np.asarray(columns["offset"], dtype=float))
    for value in cdp_values:
        index = np.flatnonzero(cdp == value)
        if index.size:
            yield int(value), index, offset[index]


def _apply_header_statics(manifest, dataset_id, src, run_id):
    """Kept for callers of the v0.14 name; v0.32 S1 lives in acqstatics.apply (SEG-Y direction, gated by the
    first-break intercept)."""
    return acqstatics.apply(manifest, dataset_id, src, run_id)


# v0.22 D1: one analysis location per 500 m of the eligible span at least (the conventional 2D interval), never
# fewer than the caller asked for, at most 15.
DENSITY_SPACING_M = 500.0
MAX_LOCATIONS = 15
# v0.22 K1: the per-location chance that noise passes the path-null test.
LOCATION_ALPHA = 0.05
SPARSE_LOCATIONS = 5

def density_count(span_m, n_locations):
    """v0.22 D1: how many locations a span of span_m metres gets."""
    if not span_m or span_m <= 0:
        return int(n_locations)
    return int(min(MAX_LOCATIONS, max(int(n_locations),
                                      int(np.floor(span_m / DENSITY_SPACING_M)) + 1)))


def _binom_tail(n, k, p=LOCATION_ALPHA):
    from math import comb
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def required_valid(n):
    """v0.22 K1: valid locations a model of n analysed locations needs."""
    n = int(n)
    if n <= SPARSE_LOCATIONS:
        return min(3, n)
    ref = _binom_tail(SPARSE_LOCATIONS, 3)
    return next(k for k in range(3, n + 1) if _binom_tail(n, k) <= ref)


def choose_analysis_locations(all_cdp, fold, n_locations):
    """Where to measure a velocity, when the caller did not say."""
    all_cdp = np.asarray(all_cdp)
    fold = np.asarray(fold)
    margin = max(1, int(round(0.05 * all_cdp.size)))
    inner_mask = np.zeros(all_cdp.size, dtype=bool)
    inner_mask[margin:all_cdp.size - margin] = True
    if not inner_mask.any():
        inner_mask[:] = True
    fold_ok = fold >= R.MIN_SEMBLANCE_TRACES
    eligible_mask = inner_mask & fold_ok
    preferred_fold = int(R.MIN_SEMBLANCE_TRACES)
    if eligible_mask.any():
        # A bin that only just reaches the estimator's absolute minimum is a poor control point when the same line
        # has a broad full-fold plateau.
        preferred_fold = max(
            int(R.MIN_SEMBLANCE_TRACES),
            int(np.ceil(np.quantile(fold[eligible_mask], 0.9))))
        stable_mask = eligible_mask & (fold >= preferred_fold)
        enough = stable_mask.sum() >= min(int(n_locations), eligible_mask.sum())
        if enough:
            eligible_mask = stable_mask
            basis = ("inner_and_stable_fold" if stable_mask.sum() <
                     (inner_mask & fold_ok).sum() else "inner_and_min_fold")
        else:
            basis = "inner_and_min_fold"
        eligible = all_cdp[eligible_mask]
    elif fold_ok.any():
        eligible, basis = all_cdp[fold_ok], "min_fold_only_no_inner_bin_qualified"
    else:
        eligible, basis = all_cdp[inner_mask], "inner_only_no_bin_reaches_min_fold"
    n = max(1, min(int(n_locations), eligible.size))
    wanted = [int(eligible[i]) for i in
              np.linspace(0, eligible.size - 1, n).round().astype(int)]
    selection = {
        "basis": basis,
        "min_fold_required": int(R.MIN_SEMBLANCE_TRACES),
        "min_fold_source": "reflection.velocity_semblance min_traces",
        "preferred_fold_required": int(preferred_fold),
        "bins_total": int(all_cdp.size),
        "edge_margin_bins": int(margin),
        "bins_inside_margin": int(inner_mask.sum()),
        "bins_meeting_min_fold": int(fold_ok.sum()),
        "bins_eligible": int(eligible.size),
        "eligible_range": [int(eligible.min()), int(eligible.max())],
        "fold_at_selected": [int(fold[all_cdp == c][0]) for c in wanted],
    }
    return wanted, selection


def grade_velocity_locations(reports):
    """Can the valid locations support interpolation across the analysed line?"""
    valid = [r for r in reports if r["valid"]]
    failed = [r for r in reports if not r["valid"]]
    required = required_valid(len(reports))
    all_cdp = [int(r["cdp"]) for r in reports]
    valid_cdp = sorted(int(r["cdp"]) for r in valid)
    span = max(all_cdp) - min(all_cdp) if all_cdp else 0
    covered = max(valid_cdp) - min(valid_cdp) if len(valid_cdp) >= 2 else 0
    coverage = 1.0 if span == 0 and valid else covered / span if span else 0.0
    dense = len(reports) > SPARSE_LOCATIONS
    max_gap = max(np.diff(valid_cdp)) if len(valid_cdp) >= 2 else None
    # locations sit on whole bins, so the limit is rounded up to one (addendum)
    gap_limit = int(np.ceil(span / 4.0)) if dense else None
    gap_ok = (not dense) or (max_gap is not None and max_gap <= gap_limit)
    ok = len(valid) >= required and coverage >= 0.8 and gap_ok
    problems = []
    if len(valid) < required:
        problems.append(
            f"only {len(valid)} of {len(reports)} analysed velocity locations "
            f"passed; at least {required} are required")
    if coverage < 0.8:
        problems.append(
            f"valid velocity locations cover only {coverage:.0%} of the analysed "
            f"CDP span; at least 80% is required")
    if not gap_ok and max_gap is not None:
        problems.append(
            f"valid velocity locations leave a gap of {int(max_gap)} cdp, longer "
            f"than a quarter of the analysed span ({gap_limit} cdp, v0.22 K2)")
    out = {
        "valid": valid,
        "failed": failed,
        "required_valid": required,
        "coverage_fraction": round(float(coverage), 3),
        "ok": bool(ok),
        "problems": problems,
    }
    if dense:
        out.update(max_gap_cdp=None if max_gap is None else int(max_gap),
                   gap_limit_cdp=int(gap_limit))
    return out


def pick_velocity(dataset_id: str, *, n_locations: int = 5,
                  cdp_list=None, v_min: float = 1400.0, v_max: float = 5500.0,
                  v_step: float = 50.0, t_step: float = 0.04,
                  band_low: float = 5.0, band_high: float = 90.0,
                  n_points: int = 10, max_rate_m_s2: float = 2500.0) -> dict:
    """Measure a stacking velocity at several CMPs and grade every one."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["geometry.cmp_assigned", "geometry.fold_valid"],
                     "Velocity analysis")
    used = int(manifest.get("budgets", {}).get("velocity_analyses", 0))
    if used >= MAX_VELOCITY_ANALYSES:
        raise BudgetExhausted(
            f"{used} velocity analyses already run on {dataset_id!r}; the limit "
            f"is {MAX_VELOCITY_ANALYSES} per dataset. Use a new dataset id to "
            "start over.")

    cmp_path = safe_input_path(evidence.get_artifact(manifest, "cmp_sorted")["path"])
    # v0.32 S1: statics are applied at sort_cmp; a file sorted before v0.32 still carrying them goes through the
    # same gated application here
    su_path, statics = acqstatics.apply(manifest, dataset_id, cmp_path, run_id)
    geom = sufile.geometry(su_path)
    all_cdp, fold = np.unique(np.asarray(
        sufile.read_header_columns(su_path, ["cdp"], geom)["cdp"]),
        return_counts=True)
    selection = None
    if cdp_list:
        wanted = [int(c) for c in cdp_list]
    else:
        wanted, selection = choose_analysis_locations(
            all_cdp, fold, n_locations)
        # v0.22 D1: at least one location per 500 m of the eligible span.
        bin_m = ((evidence.get_capability(manifest, "geometry.cmp_assigned") or {})
                 .get("evidence", {}) or {}).get("bin_size_m")
        lo, hi = selection["eligible_range"]
        bins = int(np.count_nonzero((all_cdp >= lo) & (all_cdp <= hi))) - 1
        span_m = bins * float(bin_m) if bin_m else None
        n_dense = density_count(span_m, n_locations)
        if n_dense > len(wanted):
            wanted, selection = choose_analysis_locations(all_cdp, fold, n_dense)
        selection["density"] = {
            "rule": "v0.22 D1", "spacing_m": DENSITY_SPACING_M,
            "eligible_span_m": None if span_m is None else round(span_m, 1),
            "bin_size_m": bin_m, "n_requested": int(n_locations),
            "n_locations": len(wanted), "max_locations": MAX_LOCATIONS}
    # v0.17 R2b: the direct wave R1 measured, if it measured one.
    tz_ev = (evidence.get_capability(manifest, "acquisition.time_zero_consistent")
             or {}).get("evidence", {}) or {}
    direct_wave = ({"velocity_m_s": tz_ev["direct_velocity_m_s"],
                    "period_s": tz_ev["tolerance_s"]}
                   if tz_ev.get("direct_velocity_m_s") and tz_ev.get("tolerance_s")
                   else None)
    functions, reports = [], []
    for value, index, offsets in _gathers(su_path, geom, wanted):
        data = sufile.read_traces(su_path, index, geom).astype(np.float64)
        report = velocity.analyse_gather(
            data, offsets, geom["dt_s"], geom["t_start_s"],
            v_min=v_min, v_max=v_max, v_step=v_step, t_step=t_step,
            f_lo=band_low, f_hi=band_high, n_points=n_points,
            max_rate_m_s2=max_rate_m_s2, label=f"cdp {value}",
            direct_wave=direct_wave)
        report["cdp"] = value
        report["traces"] = int(index.size)
        reports.append(report)
        functions.append({"cdp": value, "function": report["function"]})

    if not reports:
        raise ValueError(
            f"None of the requested CMPs exist in {as_rel(su_path)}. "
            f"It holds cdp {int(all_cdp.min())}-{int(all_cdp.max())}.")

    grade = grade_velocity_locations(reports)
    # v0.15: a time axis that is not anchored at the shot biases every hyperbolic velocity, however well the picks
    # agree with each other.
    tz = evidence.get_capability(manifest, "acquisition.time_zero_consistent")
    if tz and tz.get("status") == evidence.FAIL:
        grade["ok"] = False
        grade["problems"] = [
            "acquisition.time_zero_consistent is FAIL (measured on gather "
            f"{tz.get('evidence', {}).get('gather')}): "
            f"{tz.get('evidence', {}).get('reason', '')}. The picks below are "
            "reported but cannot validate a velocity model."] + grade["problems"]
    # v0.15, report only: how far down every location stays free of Dix violations.
    windows = [r["dix_valid_window"] for r in reports if r.get("dix_valid_window")]
    dix_valid_to = None
    if windows:
        ends = [w["valid_to_s"] for w in windows]
        dix_valid_to = None if any(e is None for e in ends) else min(ends)
    failed = grade["failed"]
    valid_cdps = {int(r["cdp"]) for r in grade["valid"]}
    model_functions = [f for f in functions if int(f["cdp"]) in valid_cdps]
    if governance.off():
        # baseline01 C0: no location is omitted as invalid; every analysed function is used
        model_functions = [f for f in functions if f.get("function")]
    location_notes = [
        f"cdp {r['cdp']} omitted from interpolation: {'; '.join(r['problems'])}"
        for r in failed]
    problems = grade["problems"] + location_notes

    out_dir = config.WORK_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "velocity_model.json"
    model_path.write_text(json.dumps(
        {"dataset_id": dataset_id, "run_id": run_id,
         "algorithm_version": velocity.VELOCITY_VERSION,
         "input": as_rel(su_path), "acquisition_statics": statics,
         "location_selection": (selection if selection is not None
                                else {"basis": "caller_supplied_cdp_list"}),
         "location_grade": {k: v for k, v in grade.items()
                            if k not in ("valid", "failed")},
         "locations": model_functions, "reports": reports,
         # v0.19: refine_velocity re-analyses with exactly these settings.
         "pick_parameters": {"v_min": v_min, "v_max": v_max, "v_step": v_step,
                             "t_step": t_step, "band_low": band_low,
                             "band_high": band_high, "n_points": n_points,
                             "max_rate_m_s2": max_rate_m_s2}},
        indent=2, default=str),
        encoding="utf-8")
    budgets = manifest.setdefault("budgets", {})
    budgets["velocity_analyses"] = int(budgets.get("velocity_analyses", 0)) + 1

    _set(manifest, "velocity.model_available", True,
         {"locations": [f["cdp"] for f in model_functions],
          "locations_analysed": [f["cdp"] for f in functions],
          "locations_omitted": [r["cdp"] for r in failed],
          "control_points_each": n_points,
          "location_selection": (selection if selection is not None
                                 else {"basis": "caller_supplied_cdp_list"}),
          "model": as_rel(model_path)},
         run_id, artifact=as_rel(model_path))
    _set(manifest, "velocity.validated", grade["ok"],
         {"locations_analysed": len(reports),
          "locations_valid": [r["cdp"] for r in grade["valid"]],
          "locations_failed": [r["cdp"] for r in failed],
          "required_valid": grade["required_valid"],
          "coverage_fraction": grade["coverage_fraction"],
          "supported_to_s": {r["cdp"]: r["supported_to_s"] for r in reports},
          "median_semblance": {r["cdp"]: r["median_semblance"] for r in reports},
          "dix_checked": True,
          "time_zero_status": (tz or {}).get("status", evidence.UNKNOWN),
          "scan_edge_picks": {r["cdp"]: r.get("scan_edge_picks") for r in reports},
          "dix_valid_to_s_report_only": dix_valid_to,
          "velocity_attempts": 1},
         run_id, notes=problems)
    # A newly measured model makes every product from the previous model stale, even when the new model also
    # passes.
    _set(manifest, "nmo.applied", None,
         {"reason": "velocity model was recomputed",
          "velocity_run_id": run_id}, run_id,
         notes=["Any earlier NMO artifact belongs to a superseded velocity model."])
    _set(manifest, "stack.completed", None,
         {"reason": "velocity model was recomputed",
          "velocity_run_id": run_id}, run_id,
         notes=["Any earlier stack artifact belongs to a superseded velocity model."])
    evidence.invalidate_downstream(manifest, "stack.completed", "the velocity model was recomputed",
                                   STACK_VERSION, run_id)
    evidence.add_artifact(manifest, "velocity_model", model_path,
                          "velocity-model", parents=[as_rel(su_path)],
                          run_id=run_id)
    evidence.save(manifest)

    return {
        "run_id": run_id, "dataset_id": dataset_id,
        "model": as_rel(model_path),
        "locations": [{"cdp": r["cdp"], "valid": r["valid"],
                       "supported_to_s": r["supported_to_s"],
                       "median_semblance": r["median_semblance"],
                       "velocity_range_m_s": r["velocity_range_m_s"],
                       "function": r["function"],
                       "intervals": r["intervals"],
                       "scan_edge_picks": r.get("scan_edge_picks"),
                       "dix_valid_window": r.get("dix_valid_window"),
                       "problems": r["problems"]}
                      for r in reports],
        "capabilities": {
            "velocity.model_available": evidence.capability_status(
                manifest, "velocity.model_available"),
            "velocity.validated": evidence.capability_status(
                manifest, "velocity.validated"),
        },
        "location_selection": (selection if selection is not None
                               else {"basis": "caller_supplied_cdp_list"}),
        "acquisition_statics": statics,
        "location_grade": {k: v for k, v in grade.items()
                           if k not in ("valid", "failed")},
        "time_zero": (tz or {}).get("status", evidence.UNKNOWN),
        "dix_valid_to_s_report_only": dix_valid_to,
        "notes": problems,
        "algorithm_version": velocity.VELOCITY_VERSION,
    }


def apply_nmo(dataset_id: str, *, smute: float = 1.5, overwrite: bool = False) -> dict:
    """NMO with the measured velocity model, behind velocity.validated."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["geometry.cmp_assigned", "geometry.fold_valid",
                                "velocity.model_available", "velocity.validated"],
                     "NMO correction")

    model = json.loads(safe_input_path(
        evidence.get_artifact(manifest, "velocity_model")["path"]
    ).read_text(encoding="utf-8"))
    src = safe_input_path(model.get(
        "input", evidence.get_artifact(manifest, "cmp_sorted")["path"]))

    cdps = [loc["cdp"] for loc in model["locations"]]
    tnmo = [[round(p["t0_s"], 3) for p in loc["function"]]
            for loc in model["locations"]]
    vnmo = [[round(p["v_m_s"], 1) for p in loc["function"]]
            for loc in model["locations"]]

    dst = safe_output_path(as_rel(config.WORK_DIR / dataset_id /
                                  f"{dataset_id}_nmo.su"), overwrite=overwrite)
    # Built through the same parameter validation the agent-facing tools use.
    args = runner.validate_params({"cdp": cdps, "tnmo": tnmo, "vnmo": vnmo,
                                   "smute": smute})
    result = runner.run_trusted("sunmo", args, stdout_path=dst, stdin_path=src)

    # v0.33.2 I1: a new NMO file makes the stack, and anything imaged from it, refer to superseded gathers
    evidence.invalidate_downstream(manifest, "nmo.applied", "the NMO correction was recomputed",
                                   STACK_VERSION, run_id)
    _set(manifest, "nmo.applied", True,
         {"velocity_locations": cdps, "smute": smute,
          "acquisition_statics": model.get("acquisition_statics",
                                             {"applied": False}),
          "output": as_rel(dst),
          "note": ("sunmo interpolates 1/velocity^2 between the analysed CMPs "
                   "and holds the end values constant outside them")},
         run_id, artifact=as_rel(dst))
    evidence.add_artifact(manifest, "nmo", dst, "nmo-corrected",
                          parents=[as_rel(src)], run_id=run_id)
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id,
            "input": as_rel(src), "output": as_rel(dst),
            "output_bytes": dst.stat().st_size,
            "velocity_locations": cdps, "smute": smute,
            "elapsed_s": result.get("elapsed_s")}


def time_datum(tz: dict | None) -> dict:
    """v0.16 D1, report only: where the stack's time axis stands."""
    ev = (tz or {}).get("evidence", {}) or {}
    lag, period = ev.get("intercept_s"), ev.get("tolerance_s")
    if lag is None or not period:
        return {"status": "UNKNOWN",
                "reason": ("R1 did not measure the direct-wave lag: "
                           + (ev.get("reason") or (tz or {}).get("status")
                              or "acquisition.time_zero_consistent not recorded")),
                "gather": ev.get("gather")}
    quarter = period / 4.0
    within = abs(lag) <= quarter
    level = "WITHIN_RESOLUTION" if within else "DISPLACED"
    shift = ev.get("datum_shift_applied_s")
    applied = ({} if shift is None else {
        "datum_shift_applied_ms": round(1000 * shift, 1),
        "lag_before_shift_ms": round(1000 * (ev.get("before_datum_shift") or {})
                                     .get("intercept_s", 0.0), 1),
        "shift_statement": (
            f" The time axis was moved by {1000 * shift:+.0f} ms before velocity "
            f"analysis (v0.20 T1), from R1's measured direct-wave lag; a late clock "
            f"and a causal wavelet give that same lag, so the shift sets a "
            f"zero-phase-equivalent datum rather than proving the shot instant.")})
    out = {
        "status": "MEASURED", "level": level, "gather": ev.get("gather"),
        "lag_ms": round(1000 * lag, 1),
        "dominant_period_ms": round(1000 * period, 1),
        "lag_periods": round(lag / period, 2),
        "vertical_resolution_ms": round(1000 * quarter, 1),
        "statement": (
            f"Events in this stack sit {1000 * lag:+.0f} ms from where a "
            f"zero-phase, shot-anchored reference would place them "
            f"({lag / period:+.2f} dominant periods; "
            + ("within" if within else "beyond")
            + f" the {1000 * quarter:.0f} ms vertical resolution). A late clock "
            f"and a causal source wavelet give the same lag; the data cannot "
            f"tell which. Shift by {-1000 * lag:+.0f} ms to compare with a "
            f"zero-phase reference.")}
    if applied:
        out.update(applied)
        out["statement"] += applied["shift_statement"]
    return out


ASSUMED_WATER_M_S = 1492.0
MIN_HALF_STACK_FOLD = 8
MIN_SNR_WINDOW_S = 0.2
MIN_SNR_CMPS = 10
CEILING_FLOOR = 0.9   # the "good" fraction of the judgement matrix (v0.16 criteria)


def reflection_window(manifest, max_offset_m) -> dict:
    """Where the reflection window starts: the last direct arrival (marine; R1's velocity or the ASSUMED water
    velocity), or on land (v0.33 L0/L1) where the measured first arrivals leave the spread."""
    fa = acqstatics.land_first_arrivals(manifest)
    if fa:
        same = abs(float(max_offset_m) - float(fa["max_offset_m"])) < 1.0
        t = (float(fa["t_a_s"]) if same
             else float(fa["intercept_s"]) + float(max_offset_m) * float(fa["slowness_s_per_m"]))
        return {"t_s": t, "velocity_m_s": float(fa["velocity_m_s"]), "class": "MEASURED",
                "intercept_s": float(fa["intercept_s"]),
                "land": {"window_rule": "v0.33 L1: land, measured first arrivals (not a direct wave)",
                         "first_arrival_intercept_s": float(fa["intercept_s"]),
                         "first_arrival_velocity_m_s": float(fa["velocity_m_s"])}}
    tz_ev = (evidence.get_capability(manifest, "acquisition.time_zero_consistent")
             or {}).get("evidence", {}) or {}
    v_d = tz_ev.get("direct_velocity_m_s")
    v_class = "MEASURED" if v_d else "ASSUMED"
    v_d = float(v_d or ASSUMED_WATER_M_S)
    return {"t_s": float(max_offset_m) / v_d, "velocity_m_s": v_d, "class": v_class,
            "intercept_s": 0.0}


def half_stack_correlations(data, cdp, off, min_fold=MIN_HALF_STACK_FOLD) -> list:
    """Per-CMP correlation of the two alternate-offset half-stacks."""
    cdp = np.asarray(cdp)
    order = np.lexsort((np.asarray(off), cdp))
    cdp_s = cdp[order]
    starts = np.flatnonzero(np.r_[True, cdp_s[1:] != cdp_s[:-1]])
    ends = np.r_[starts[1:], cdp_s.size]
    rs = []
    for a, b in zip(starts, ends):
        if b - a < min_fold:
            continue
        idx = order[a:b]
        h1 = data[idx[0::2]].mean(axis=0)
        h2 = data[idx[1::2]].mean(axis=0)
        n1, n2 = np.linalg.norm(h1), np.linalg.norm(h2)
        if n1 > 0 and n2 > 0:
            rs.append(float(h1 @ h2 / (n1 * n2)))
    return rs


MIN_MEASURED_FRACTION = 0.5   # "most of", as in F1


def support_fraction(t_direct, record_end, supported):
    """Share of the window below the last direct arrival whose velocity was measured: (s - t_d) / (T - t_d),
    clipped to 0-1."""
    if record_end <= t_direct:
        return None
    return float(min(1.0, max(0.0, (supported - t_direct) / (record_end - t_direct))))


def area_support_fraction(stack_cdps, loc_cdps, loc_depths, t_direct, record_end):
    """v0.22 E2: mean over the stacked CMPs of the support fraction, with the supported depth interpolated
    linearly in cdp between valid locations and held constant beyond them (as sunmo holds the velocity)."""
    order = np.argsort(loc_cdps)
    xs = np.asarray(loc_cdps, dtype=float)[order]
    ys = np.asarray(loc_depths, dtype=float)[order]
    depth = np.interp(np.asarray(stack_cdps, dtype=float), xs, ys)
    if record_end <= t_direct:
        return None
    frac = np.clip((depth - t_direct) / (record_end - t_direct), 0.0, 1.0)
    return float(frac.mean())


def velocity_support(nmo_path, manifest) -> dict:
    """v0.18 E1 / v0.22 E2: how much of this stack rests on a measured velocity."""
    geom = sufile.geometry(nmo_path)
    cols = sufile.read_header_columns(nmo_path, ["offset", "cdp"], geom)
    off = np.abs(np.asarray(cols["offset"], dtype=np.float64))
    stack_cdps = np.unique(np.asarray(cols["cdp"]))
    win = reflection_window(manifest, float(off.max()))
    v_d, v_class, t_d = win["velocity_m_s"], win["class"], win["t_s"]
    vel_ev = (evidence.get_capability(manifest, "velocity.validated")
              or {}).get("evidence", {}) or {}
    valid = {str(c) for c in vel_ev.get("locations_valid", [])}
    pairs = [(int(c), float(v)) for c, v in (vel_ev.get("supported_to_s") or {}).items()
             if str(c) in valid and v]
    T = geom["t_start_s"] + geom["ns"] * geom["dt_s"]
    out = {"direct_velocity_m_s": v_d, "direct_velocity_class": v_class,
           "last_direct_arrival_s": round(t_d, 3), "record_end_s": round(T, 3),
           **win.get("land", {})}
    if not pairs:
        return {**out, "status": "UNKNOWN", "reason": "no valid velocity location"}
    s = float(min(v for _, v in pairs))
    frac_min = support_fraction(t_d, T, s)
    if frac_min is None:
        return {**out, "status": "UNKNOWN",
                "reason": "the record ends before the direct wave leaves the spread"}
    frac = area_support_fraction(stack_cdps, [c for c, _ in pairs],
                                 [v for _, v in pairs], t_d, T)
    lateral = lateral_fraction(stack_cdps, [c for c, _ in pairs])
    level = "PARTIAL" if frac < MIN_MEASURED_FRACTION else "MEASURED"
    return {**out, "status": "REPORTED", "level": level, "rule": "v0.22 E2 (by area)",
            "shallowest_supported_s": round(s, 3),
            "measured_fraction": round(frac, 3),
            "measured_fraction_at_shallowest_location": round(frac_min, 3),
            "valid_locations": len(pairs),
            "lateral_fraction": round(lateral, 3),
            "lateral_rule": "v0.27 W4: stacked CMPs between the outermost valid locations",
            "statement": (
                f"Averaged over the {stack_cdps.size} stacked CMPs, the velocity is "
                f"measured over {100 * frac:.0f}% of the reflection window "
                f"({t_d:.2f}-{T:.2f} s); below each location's deepest supported "
                f"pick it is held constant (shallowest: {s:.2f} s)"
                + (" -- most of this section was stacked on an assumed "
                   "velocity, and its deeper part should not be read as "
                   "measured." if level == "PARTIAL" else "."))}


def lateral_fraction(stack_cdps, valid_cdps) -> float:
    """v0.27 W4: share of the stacked CMPs lying between the outermost valid velocity locations; outside them the
    velocity is held constant sideways."""
    c = np.asarray(stack_cdps)
    if c.size == 0 or not len(valid_cdps):
        return 0.0
    lo, hi = min(valid_cdps), max(valid_cdps)
    return float(np.mean((c >= lo) & (c <= hi)))


def signal_to_noise(nmo_path, manifest) -> dict:
    """v0.17 N1, report only: the stack's own S/N from two half-stacks."""
    geom = sufile.geometry(nmo_path)
    cols = sufile.read_header_columns(nmo_path, ["cdp", "offset"], geom)
    cdp = np.asarray(cols["cdp"])
    off = np.abs(np.asarray(cols["offset"], dtype=np.float64))
    win = reflection_window(manifest, float(off.max()))
    v_d, v_class = win["velocity_m_s"], win["class"]
    vel_ev = (evidence.get_capability(manifest, "velocity.validated")
              or {}).get("evidence", {}) or {}
    valid = {str(c) for c in vel_ev.get("locations_valid", [])}
    depths = [v for c, v in (vel_ev.get("supported_to_s") or {}).items()
              if str(c) in valid and v]
    out = {"algorithm": "half-stack coherence", "direct_velocity_m_s": v_d,
           "direct_velocity_class": v_class, **win.get("land", {})}
    if not depths:
        return {**out, "status": "UNKNOWN",
                "reason": "no valid velocity location reports a supported depth"}
    t_a = win["t_s"]
    # v0.18: the window runs to the record end.
    t_b = geom["t_start_s"] + geom["ns"] * geom["dt_s"]
    out.update(window_s=[round(t_a, 3), round(t_b, 3)])
    if t_b - t_a < MIN_SNR_WINDOW_S:
        return {**out, "status": "UNKNOWN",
                "reason": (f"the window between the last direct arrival "
                           f"({t_a:.2f} s) and the record end ({t_b:.2f} s) is "
                           f"shorter than {MIN_SNR_WINDOW_S} s")}
    i0 = max(0, int(round((t_a - geom["t_start_s"]) / geom["dt_s"])))
    i1 = min(geom["ns"], int(round((t_b - geom["t_start_s"]) / geom["dt_s"])))
    data = sufile.read_traces(nmo_path, np.arange(geom["ntr"]), geom)[:, i0:i1]
    rs = half_stack_correlations(data, cdp, off)
    out["cmps_used"] = len(rs)
    if len(rs) < MIN_SNR_CMPS:
        return {**out, "status": "UNKNOWN",
                "reason": f"only {len(rs)} CMPs hold {MIN_HALF_STACK_FOLD}+ traces"}
    r = float(np.median(rs))
    if not np.isfinite(r):
        # v0.30 N0: a non-finite measurement is never a pass
        return {**out, "status": "UNMEASURABLE", "cmps_used": len(rs),
                "reason": "the half-stack correlation is not finite (non-finite or overflowing "
                          "samples in the NMO gathers)"}
    snr = 2 * r / (1 - r) if 0 < r < 1 else (0.0 if r <= 0 else float("inf"))
    ceiling = float(np.sqrt(snr / (1 + snr))) if np.isfinite(snr) else 1.0
    level = "NOISE_LIMITED" if ceiling < CEILING_FLOOR else "CLEAR"
    return {**out, "status": "MEASURED", "level": level,
            "half_stack_correlation": round(r, 3),
            "stack_snr_power": round(snr, 2) if np.isfinite(snr) else None,
            "correlation_ceiling": round(ceiling, 3),
            "statement": (
                f"Two independent half-stacks agree at r = {r:.2f} between "
                f"{t_a:.2f} and {t_b:.2f} s, a stack S/N of {snr:.1f} in power; "
                f"no reference can correlate with this stack better than "
                f"{ceiling:.2f}" + (" -- the section is limited by noise it "
                                    "carries, and events in it should be read "
                                    "with that in mind." if level == "NOISE_LIMITED"
                                    else "."))}


W1_CEILING = 0.95   # v0.20 W1
W3_FRACTION = 0.25  # v0.22 W3
W4_FRACTION = 0.25  # v0.27 W4: W3's fraction, sideways


def reliability_warning(snr: dict, support: dict, feasibility: dict | None = None,
                        sample_check: dict | None = None) -> dict:
    """v0.23 T2: a quality warning and a provenance caution, reported apart."""
    quality, provenance = [], []
    if snr.get("status") == "UNMEASURABLE":
        quality.append("N0 half-stack S/N not measurable (non-finite samples)")
    if sample_check and sample_check.get("corrupt_count"):
        quality.append(f"Q0 {sample_check['corrupt_count']} corrupt trace(s) in the stack at CDP "
                       f"{sample_check['corrupt_cdps'][:10]}; run condition_gathers "
                       f"[{{\"op\": \"kill_corrupt\"}}] and restack")
    ceiling = snr.get("correlation_ceiling")
    if ceiling is not None and ceiling < W1_CEILING:
        quality.append(f"N2 half-stack ceiling {ceiling:.3f} < {W1_CEILING}")
    frac = support.get("measured_fraction")
    if frac is not None and frac < W3_FRACTION:
        quality.append(f"E2 measured fraction {frac:.2f} < {W3_FRACTION}")
    lat = support.get("lateral_fraction")
    if lat is not None and lat < W4_FRACTION:
        quality.append(f"W4 only {100 * lat:.0f}% of the stacked CMPs lie between the valid "
                       f"velocity locations (< {100 * W4_FRACTION:.0f}%)")
    if feasibility:
        provenance.append(f"feasibility not established before binning ({feasibility['status']})")
    level = "WARN" if quality else ("CAUTION" if provenance else "OK")
    reasons = quality + provenance
    if level == "WARN":
        statement = ("The quality of this stack is at risk: " + "; ".join(quality) + "."
                     + (" Also: " + "; ".join(provenance) + "." if provenance else ""))
    elif level == "CAUTION":
        statement = ("No quality warning, but " + "; ".join(provenance)
                     + ": reflections are shown only by the velocity analysis.")
    else:
        statement = "No reliability warning (v0.30 N0+Q0+N2+W3+W4, W2 as caution)."
    return {"level": level, "reasons": reasons, "quality_reasons": quality,
            "provenance_reasons": provenance, "rule": "v0.30 N0+Q0+N2+W3+W4 / W2",
            "statement": statement}


def feasibility_disclosure(cap: dict | None) -> dict | None:
    """v0.20 G1: say so when reflections were never established before binning."""
    cap = cap or {}
    if cap.get("status") == evidence.PASS:
        return None
    verdict = (cap.get("evidence") or {}).get("verdict")
    return {"status": verdict or cap.get("status", "UNKNOWN"),
            "statement": ("Reflection feasibility was not established before binning "
                          f"({verdict or cap.get('status')}); the only evidence of "
                          "reflections in this stack is the velocity analysis "
                          "(path-null test at each location).")}


def stack_cmp(dataset_id: str, *, overwrite: bool = False) -> dict:
    """Sum each CMP gather into one trace, behind nmo.applied."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["nmo.applied"], "Stacking")

    src = safe_input_path(evidence.get_artifact(manifest, "nmo")["path"])
    dst = safe_output_path(as_rel(config.RESULT_DIR / f"{dataset_id}_stack.su"),
                           overwrite=overwrite)
    kept = None
    if dst.exists():
        # v0.31 B1: an overwritten stack is kept as <id>_stack.v<k>.su, never lost
        k = 1
        while (config.RESULT_DIR / f"{dataset_id}_stack.v{k}.su").exists():
            k += 1
        kept = config.RESULT_DIR / f"{dataset_id}_stack.v{k}.su"
        shutil.copyfile(dst, kept)
        evidence.add_artifact(manifest, f"stack_v{k}", kept, "stack-previous",
                              parents=[as_rel(dst)], run_id=run_id)
    # v0.20 S1: a scoped velocity model releases only the span it measured.
    vel_ev = (evidence.get_capability(manifest, "velocity.validated") or {}
              ).get("evidence", {}) or {}
    scope = vel_ev.get("scope_cdp")
    if scope:
        scoped = safe_output_path(as_rel(config.WORK_DIR / dataset_id /
                                         f"{dataset_id}_nmo_scoped.su"), overwrite=True)
        runner.run_trusted("suwind", runner.validate_params(
            {"key": "cdp", "min": int(scope[0]), "max": int(scope[1])}),
            stdout_path=scoped, stdin_path=src)
        src = scoped
    args = runner.validate_params({"key": "cdp"})
    result = runner.run_trusted("sustack", args, stdout_path=dst, stdin_path=src)

    geom = sufile.geometry(dst)
    datum = time_datum(evidence.get_capability(
        manifest, "acquisition.time_zero_consistent"))
    snr = signal_to_noise(src, manifest)
    support = velocity_support(src, manifest)
    attempts = int(vel_ev.get("velocity_attempts", 1))
    analyses_used = int((manifest.get("budgets") or {}).get("velocity_analyses", 0))
    feasibility = feasibility_disclosure(evidence.get_capability(
        manifest, "reflection.processing_feasible"))
    sample_check = sanity.scan(dst)
    reliability = reliability_warning(snr, support, feasibility, sample_check)
    extra = {"sample_check": sample_check,
             **({"previous_stack_kept_as": as_rel(kept)} if kept else {}),
             **({"scope_cdp": scope} if scope else {}),
             **({"feasibility": feasibility} if feasibility else {})}
    # v0.33.2 I1: a migration or depth image of the previous stack does not describe this one
    evidence.invalidate_downstream(manifest, "stack.completed", "the stack was recomputed",
                                   STACK_VERSION, run_id)
    _set(manifest, "stack.completed", True,
         {"traces": geom["ntr"], "ns": geom["ns"], "dt_us": geom["dt_us"],
          "output": as_rel(dst), "time_datum": datum, "signal_to_noise": snr,
          "velocity_support": support, "velocity_attempts": attempts,
          "velocity_analyses_used": analyses_used,
          "reliability": reliability, **extra},
         run_id, artifact=as_rel(dst),
         notes=([datum["statement"]] if (datum.get("level") == "DISPLACED"
                                         or datum.get("datum_shift_applied_ms") is not None)
                else [])
         + ([snr["statement"]] if snr.get("level") == "NOISE_LIMITED" else [])
         + ([support["statement"]] if support.get("level") == "PARTIAL" else [])
         + ([reliability["statement"]] if reliability["level"] != "OK" else [])
         + ([f"Scoped release: cdp {scope[0]}-{scope[1]} only."] if scope else [])
         + ([feasibility["statement"]] if feasibility else []))
    evidence.add_artifact(manifest, "stack", dst, "stack",
                          parents=[as_rel(src)], run_id=run_id)
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id,
            "input": as_rel(src), "output": as_rel(dst),
            "traces": geom["ntr"], "ns": geom["ns"],
            "record_length_s": geom["record_length_s"],
            "output_bytes": dst.stat().st_size,
            "time_datum": datum,
            "signal_to_noise": snr,
            "velocity_support": support,
            "velocity_attempts": attempts,
            "velocity_analyses_used": analyses_used,
            "reliability": reliability, **extra,
            "elapsed_s": result.get("elapsed_s")}
