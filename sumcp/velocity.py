"""Stacking velocity analysis, and the checks that decide whether to trust it."""

from __future__ import annotations

import numpy as np

from . import claims as C
from . import reflection as R

VELOCITY_VERSION = "velocity-0.9"

# A stacking velocity outside this range is not a velocity, it is a pick in the noise.
V_MIN, V_MAX = 1400.0, 6500.0

# Dix interval velocities are far more sensitive than the RMS function they come from, so they get their own,
# wider bounds before being called broken.
V_INT_MIN, V_INT_MAX = 1350.0, 7500.0

# Below this many measured control points there is no trend to pick, and the path through the panel is the
# monotonicity constraint talking.
MIN_SUPPORTED_POINTS = 3

__all__ = ["VELOCITY_VERSION", "V_MIN", "V_MAX", "MIN_SUPPORTED_POINTS",
           "scan", "pick_constrained", "thin", "support", "hold_below_support",
           "dix_interval", "validate", "analyse_gather"]


def scan(data, offsets, dt, t0, t0_grid, v_grid, f_lo=5.0, f_hi=90.0,
         window_s=0.04):
    """Semblance over (t0, velocity), on an equalised gather."""
    panel = R.bandpass(np.asarray(data, dtype=np.float64), dt, f_lo, f_hi)
    gain = R.agc_gain(panel, dt)
    return R.velocity_semblance(panel / gain, offsets, dt, t0, t0_grid, v_grid,
                                window_s=window_s)


def pick_constrained(semblance, t0_grid, v_grid, max_rate_m_s2=2500.0):
    """The non-decreasing velocity path through the panel with the most support."""
    n_t, n_v = semblance.shape
    step = float(t0_grid[1] - t0_grid[0]) if n_t > 1 else 1.0
    dv = float(v_grid[1] - v_grid[0]) if n_v > 1 else 1.0
    max_jump = max(1, int(round(max_rate_m_s2 * step / dv)))

    best = semblance[0].astype(np.float64).copy()
    came_from = np.zeros((n_t, n_v), dtype=np.int32)
    for a in range(1, n_t):
        # For each velocity j, the best predecessor is the largest value in best[j - max_jump : j + 1],
        # non-decreasing, bounded rate.
        padded = np.full(n_v + max_jump, -np.inf)
        padded[max_jump:] = best
        windows = np.lib.stride_tricks.sliding_window_view(padded, max_jump + 1)
        source = windows.argmax(axis=1)
        prev = np.arange(n_v) - max_jump + source
        came_from[a] = prev
        best = semblance[a] + windows.max(axis=1)

    path = np.empty(n_t, dtype=np.int64)
    path[-1] = int(np.argmax(best))
    for a in range(n_t - 1, 0, -1):
        path[a - 1] = came_from[a][path[a]]
    return [{"t0_s": float(t0_grid[a]), "v_m_s": float(v_grid[path[a]]),
             "semblance": float(semblance[a, path[a]])}
            for a in range(n_t)]


def thin(function, n_points=10, min_separation_s=0.25):
    """Represent the picked path by control points evenly spaced in time."""
    if len(function) <= 2:
        return list(function)
    times = np.asarray([p["t0_s"] for p in function])
    span = float(times[-1] - times[0])
    usable = max(2, min(int(n_points), int(span / min_separation_s) + 1))
    targets = np.linspace(times[0], times[-1], usable)
    keep = sorted({int(np.abs(times - t).argmin()) for t in targets})
    return [function[i] for i in keep]


def dix_interval(function):
    """Interval velocities between consecutive picks."""
    out = []
    for near, far in zip(function, function[1:]):
        dt = far["t0_s"] - near["t0_s"]
        if dt <= 0:
            continue
        squared = (far["v_m_s"] ** 2 * far["t0_s"]
                   - near["v_m_s"] ** 2 * near["t0_s"]) / dt
        out.append({
            "from_t0_s": round(near["t0_s"], 3), "to_t0_s": round(far["t0_s"], 3),
            "v_interval_m_s": round(float(np.sqrt(squared)), 1) if squared > 0
            else None,
            "v_squared": round(float(squared), 1),
            "physical": bool(squared > 0),
        })
    return out


def support(path, significance_level):
    """How much of the picked path the data actually supports, and to what depth."""
    levels = np.asarray(significance_level, dtype=float)
    if levels.ndim == 0:
        levels = np.full(len(path), float(levels))
    if levels.size != len(path):
        raise ValueError("one significance level is required per path point")
    clearing = [p for p, level in zip(path, levels)
                if p["semblance"] > level]
    # A single late crossing is expected occasionally even under an exact pointwise permutation envelope.
    clustered_to = None
    if len(clearing) >= 2 and len(path) >= 2:
        step = float(np.median(np.diff([p["t0_s"] for p in path])))
        group = [clearing[0]]
        groups = []
        for point in clearing[1:]:
            if point["t0_s"] - group[-1]["t0_s"] <= 2.01 * step:
                group.append(point)
            else:
                groups.append(group)
                group = [point]
        groups.append(group)
        dense = [g for g in groups if len(g) >= 2]
        if dense:
            clustered_to = max(g[-1]["t0_s"] for g in dense)
    return {
        "points": len(clearing),
        "fraction": round(len(clearing) / max(1, len(path)), 3),
        "to_s": clustered_to,
    }


def hold_below_support(function, significance_level, supported_to=None):
    """Stop the velocity climbing once the data stops supporting it."""
    if supported_to is None:
        clearing = [p for p in function if p["semblance"] > significance_level]
        if not clearing:
            return [dict(p) for p in function], None
        supported_to = max(p["t0_s"] for p in clearing)
    deepest = max((p for p in function if p["t0_s"] <= supported_to + 1e-9),
                  key=lambda p: p["t0_s"], default=None)
    if deepest is None:
        return [dict(p) for p in function], None
    held = []
    for point in function:
        if point["t0_s"] > deepest["t0_s"]:
            held.append({**point, "v_m_s": deepest["v_m_s"], "held": True})
        else:
            held.append(dict(point))
    return held, deepest["t0_s"]


def _dix_window(function, intervals, dense_cleared):
    """How far down the function is free of any Dix violation (v0.15, report only)."""
    bad = [i for i in intervals if i.get("measured") and
           (not i["physical"] or not (V_INT_MIN <= i["v_interval_m_s"] <= V_INT_MAX))]
    if not bad:
        return None
    first = min(i["from_t0_s"] for i in bad)
    above = [p["t0_s"] for p in function if p["t0_s"] < first - 1e-9]
    end = max(above) if above else None
    supported = (None if dense_cleared is None or end is None else
                 sum(1 for t, ok in dense_cleared if ok and t <= end + 1e-9))
    usable = (end is not None and supported is not None
              and supported >= MIN_SUPPORTED_POINTS)
    return {"first_violation_from_s": round(first, 3),
            "valid_to_s": round(end, 3) if usable else None,
            "supported_points_above": supported,
            "rule": ("last control point that is not an endpoint of any "
                     "violating Dix interval, with at least "
                     f"{MIN_SUPPORTED_POINTS} supported path points above it"),
            "status": "REPORT_ONLY"}


def in_direct_wave_zone(pick, direct_wave, offsets) -> bool:
    """v0.17 R2b."""
    if not direct_wave or offsets is None:
        return False
    v_d, period = direct_wave.get("velocity_m_s"), direct_wave.get("period_s")
    if not v_d or not period:
        return False
    x = np.abs(np.asarray(offsets, dtype=np.float64))
    frac, _ = R._direct_separation(pick["t0_s"], pick["v_m_s"], x, v_d, period)
    return frac < R.SEPARATION_FRACTION


def validate(function, significance_level, record_length_s, label="",
             support_info=None, path_test=None, scan_edges=None,
             dense_cleared=None, direct_wave=None, offsets=None):
    """Is this a velocity function, or a path through noise?"""
    problems = []
    velocities = [p["v_m_s"] for p in function]
    times = [p["t0_s"] for p in function]

    out_of_range = [p for p in function if not (V_MIN <= p["v_m_s"] <= V_MAX)]
    if out_of_range:
        problems.append(
            f"{len(out_of_range)} pick(s) outside {V_MIN:.0f}-{V_MAX:.0f} m/s")

    falls = [(times[i], velocities[i], velocities[i + 1])
             for i in range(len(velocities) - 1)
             if velocities[i + 1] < velocities[i]]
    if falls:
        problems.append(
            f"the function decreases at {len(falls)} point(s), which the "
            f"constrained pick should have made impossible -- something has "
            f"edited it since")

    # Dix is checked where the velocity was measured.
    support_info = support_info or support(function, significance_level)
    supported_to = support_info["to_s"]
    intervals = dix_interval(function)
    measured = ([] if supported_to is None else
                [i for i in intervals
                 if i["to_t0_s"] <= supported_to + 1e-9])
    for entry in intervals:
        entry["measured"] = entry in measured
    broken = [i for i in measured if not i["physical"]]
    if broken:
        where = ", ".join("{}-{} s".format(i["from_t0_s"], i["to_t0_s"])
                          for i in broken[:3])
        more = "..." if len(broken) > 3 else ""
        problems.append(
            f"Dix gives an imaginary interval velocity over {len(broken)} "
            f"layer(s) ({where}{more}): the picks are individually plausible "
            f"and jointly impossible")
    wild = [i for i in measured if i["physical"]
            and not (V_INT_MIN <= i["v_interval_m_s"] <= V_INT_MAX)]
    if wild:
        problems.append(
            f"{len(wild)} interval velocity(ies) outside "
            f"{V_INT_MIN:.0f}-{V_INT_MAX:.0f} m/s")

    # v0.15: a maximum on the edge of the scan is censored, not measured.
    edge_supported, edge_unconstrained, edge_direct = [], [], []
    if scan_edges is not None:
        lo, hi = scan_edges
        cleared = dict((round(t, 6), ok) for t, ok in (dense_cleared or []))
        for p in function:
            if p.get("held") or not (p["v_m_s"] <= lo + 1e-6 or p["v_m_s"] >= hi - 1e-6):
                continue
            ok = cleared.get(round(p["t0_s"], 6), p["semblance"] > significance_level)
            if ok and in_direct_wave_zone(p, direct_wave, offsets):
                # v0.17 R2b: this hyperbola never leaves the direct wave, so its velocity is the direct wave's,
                # not a censored reflection.
                edge_direct.append(p)
                continue
            (edge_supported if ok else edge_unconstrained).append(p)
        if edge_supported:
            where = ", ".join(f"{p['t0_s']:.2f} s" for p in edge_supported[:4])
            problems.append(
                f"{len(edge_supported)} supported pick(s) sit on the edge of the "
                f"velocity scan ({lo:.0f}-{hi:.0f} m/s) at {where}: the semblance "
                f"maximum lies at or beyond what was searched, so the velocity "
                f"there is censored, not measured")

    # A velocity function has to be defined over the whole record, including the quiet parts, so demanding that
    # every control point clear the noise level would fail every real gather.
    n_supported = support_info["points"]
    if path_test is not None and not path_test["significant"]:
        problems.append(
            f"the constrained path mean semblance {path_test['observed_mean']:.4f} "
            f"does not exceed the moveout-destroyed path null "
            f"(p={path_test['p_value']:.3f}, alpha={path_test['alpha']:.3f}); "
            f"the constraint talking through noise is louder than the data")
    if n_supported < MIN_SUPPORTED_POINTS:
        problems.append(
            f"only {n_supported} point(s) on the picked path clear their "
            f"time-local moveout-destroyed path thresholds; there is no velocity "
            f"trend here to pick, and the path through the panel is the constraint "
            f"talking, not the data")
    elif supported_to is None:
        problems.append(
            "the path clears its time-local null at isolated samples only; "
            "no adjacent support identifies a depth to which the velocity was "
            "measured")
    elif supported_to is not None and supported_to < 0.5 * record_length_s:
        problems.append(
            f"the velocity is only supported to {supported_to:.2f} s of a "
            f"{record_length_s:.2f} s record; stacking below that would run on "
            f"an extrapolated velocity")

    return {
        "label": label,
        "valid": not problems,
        "problems": problems,
        "supported_points": n_supported,
        "supported_fraction": support_info["fraction"],
        "supported_to_s": round(supported_to, 3) if supported_to else None,
        "extrapolated_below_s": (round(supported_to, 3)
                                 if supported_to and supported_to < times[-1]
                                 else None),
        "n_points": len(function),
        "time_range_s": [round(times[0], 3), round(times[-1], 3)],
        "velocity_range_m_s": [round(min(velocities), 1), round(max(velocities), 1)],
        "median_semblance": round(float(np.median([p["semblance"] for p in function])), 4),
        "intervals": intervals,
        "scan_edge_picks": {
            "supported_t0_s": [round(p["t0_s"], 3) for p in edge_supported],
            "unconstrained_t0_s": [round(p["t0_s"], 3) for p in edge_unconstrained],
            "direct_wave_zone_t0_s": [round(p["t0_s"], 3) for p in edge_direct],
        } if scan_edges is not None else None,
        "dix_valid_window": _dix_window(function, intervals, dense_cleared),
        **({"path_test": path_test} if path_test is not None else {}),
    }


def _path_null(equalised, offsets, dt, t0, t0_grid, v_grid, observed_path,
               max_rate_m_s2, trials=39, quantile=0.9, alpha=0.05, seed=0,
               local_trials=None):
    """Grade a selected velocity path against equally selected null paths."""
    rng = np.random.default_rng(seed)
    ntr, n = equalised.shape
    rows = np.arange(ntr)[:, None]
    columns = np.arange(n)[None, :]
    null_scores = []
    global_maxima = []
    for _ in range(trials):
        shift = rng.integers(n, size=ntr)[:, None]
        shuffled = equalised[rows, (columns - shift) % n]
        panel = R.velocity_semblance(shuffled, offsets, dt, t0,
                                     t0_grid, v_grid)
        path = pick_constrained(panel, t0_grid, v_grid,
                                max_rate_m_s2=max_rate_m_s2)
        null_scores.append([p["semblance"] for p in path])
        global_maxima.append(float(panel.max()))

    null_scores = np.asarray(null_scores, dtype=float)
    observed = np.asarray([p["semblance"] for p in observed_path], dtype=float)
    null_means = null_scores.mean(axis=1)
    observed_mean = float(observed.mean())
    p_value = float((1 + np.count_nonzero(null_means >= observed_mean))
                    / (trials + 1))
    # v0.20: a repeated test (refine_velocity) needs a smaller alpha and so more trials for the path test, but the
    # time-local support envelope keeps the first `local_trials` realisations so that "measured to" means what it
    # meant on the first pick.
    lt = trials if local_trials is None else min(int(local_trials), trials)
    return {
        # The upper envelope gives every time sample its own exact permutation threshold (1 / (trials + 1))
        # without borrowing the most extreme cell from unrelated times and velocities.
        "local_levels": np.max(null_scores[:lt], axis=0),
        "local_alpha": float(1.0 / (lt + 1)),
        "global_level": float(np.quantile(global_maxima, quantile)),
        "observed_mean": observed_mean,
        "null_mean_quantile": float(np.quantile(null_means, quantile)),
        "p_value": p_value,
        "alpha": float(alpha),
        "trials": int(trials),
        "quantile": float(quantile),
        "significant": bool(p_value <= alpha),
    }


def analyse_gather(data, offsets, dt, t0, *, v_min=1400.0, v_max=5500.0,
                   v_step=50.0, t_step=0.04, f_lo=5.0, f_hi=90.0,
                   n_points=10, max_rate_m_s2=2500.0, null_trials=39,
                   label="", direct_wave=None, path_alpha=0.05, local_trials=None):
    """Scan one CMP gather, pick a constrained function, and grade it."""
    data = np.asarray(data, dtype=np.float64)
    record_length_s = data.shape[1] * dt
    t0_grid = np.arange(t0 + t_step, t0 + record_length_s - t_step, t_step)
    v_grid = np.arange(v_min, v_max + v_step, v_step)

    panel = R.bandpass(data, dt, f_lo, f_hi)
    gain = R.agc_gain(panel, dt)
    semblance = R.velocity_semblance(panel / gain, offsets, dt, t0,
                                     t0_grid, v_grid)
    full = pick_constrained(semblance, t0_grid, v_grid,
                            max_rate_m_s2=max_rate_m_s2)
    null = _path_null(panel / gain, offsets, dt, t0, t0_grid, v_grid, full,
                      max_rate_m_s2, trials=null_trials, alpha=path_alpha,
                      local_trials=local_trials)
    level = null["global_level"]
    support_info = support(full, null["local_levels"])
    function = thin(full, n_points=n_points)
    function, held_from = hold_below_support(function, level,
                                             support_info["to_s"])
    path_test = {k: v for k, v in null.items() if k != "local_levels"}
    dense_cleared = [(float(p["t0_s"]), bool(p["semblance"] > lvl))
                     for p, lvl in zip(full, null["local_levels"])]
    report = validate(function, level, record_length_s, label=label,
                      support_info=support_info, path_test=path_test,
                      scan_edges=(float(v_grid[0]), float(v_grid[-1])),
                      dense_cleared=dense_cleared, direct_wave=direct_wave,
                      offsets=offsets)
    report["velocity_held_constant_below_s"] = (
        round(held_from, 3) if held_from is not None else None)
    report["significance_level"] = C.derived(
        round(level, 4),
        f"diagnostic 90th percentile of the grid maximum over {null_trials} "
        f"moveout-destroyed realisations; path support uses the time-local "
        f"selected-path null instead")
    report["local_path_threshold_range"] = [
        round(float(np.min(null["local_levels"])), 4),
        round(float(np.max(null["local_levels"])), 4),
    ]
    report["function"] = [{"t0_s": round(p["t0_s"], 3),
                           "v_m_s": round(p["v_m_s"], 1),
                           "semblance": round(p["semblance"], 4),
                           **({"held": True} if p.get("held") else {})}
                          for p in function]
    report["algorithm_version"] = VELOCITY_VERSION
    return report
