"""Is the channel moveout a spacing error or a recording delay?"""

from __future__ import annotations

import numpy as np

from . import claims as C
from . import geometry as G
from . import reflection as R
from . import sufile

ARRAYFIT_VERSION = "arrayfit-0.9"

WATER = 1492.0
# Below this spread in dd the two terms are the same column in all but name.
MIN_DD_SPREAD_M = 0.25
MIN_SHOTS = 20

__all__ = ["ARRAYFIT_VERSION", "MIN_DD_SPREAD_M", "measure_slopes",
           "huber", "fit", "assess", "source_tracking",
           "TRACKS", "NO_TRACK", "TRACK_INCONCLUSIVE"]


# ------------------------------------------------------------------ measure
def measure_slopes(path, *, f_lo=30.0, f_hi=250.0, window_s=0.05,
                   slope_limit_ms=5.0, slope_step_ms=0.05, search_s=0.10,
                   water=WATER, max_shots=None):
    """Per-shot arrival slope and intercept, fitted across the whole array."""
    geom = sufile.geometry(path)
    resolved = G.resolve_coordinates(path, geom)
    s, raw = resolved["_scaled"], resolved["_raw"]
    sx, sy = np.asarray(s["sx"], float), np.asarray(s["sy"], float)
    gx, gy = np.asarray(s["gx"], float), np.asarray(s["gy"], float)
    channel = np.asarray(raw["tracf"], dtype=np.int64)
    shot = np.asarray(raw["fldr"], dtype=np.int64)
    distance = np.hypot(gx - sx, gy - sy)
    dt, t0 = geom["dt_s"], geom["t_start_s"]

    slopes = np.arange(-slope_limit_ms, slope_limit_ms + 1e-9,
                       slope_step_ms) * 1e-3
    half = int(window_s / dt / 2)
    shots = np.unique(shot)
    if max_shots:
        shots = shots[np.linspace(0, shots.size - 1,
                                  min(max_shots, shots.size)).round().astype(int)]

    rows = []
    for value in shots:
        index = np.flatnonzero(shot == value)
        index = index[np.argsort(channel[index])]
        if index.size < 8:
            continue
        c = channel[index].astype(float)
        d = distance[index]
        block = R.bandpass(np.nan_to_num(
            sufile.read_traces(path, index, geom).astype(np.float64)),
            dt, f_lo, f_hi)
        block /= (np.sqrt((block ** 2).mean(axis=1))[:, None] + 1e-30)
        n = block.shape[1]

        rel = c - c.mean()
        centre = float(np.median(d)) / water
        margin = int(np.abs(rel).max() * np.abs(slopes).max() / dt) + 2
        lo = max(0, int((centre - search_s - t0) / dt) - half - margin)
        hi = min(n, int((centre + search_s - t0) / dt) + half + margin)
        if hi - lo < 4 * half:
            continue
        segment = block[:, lo:hi]
        width = segment.shape[1]
        base = np.arange(width)
        size = 2 * half

        best = (-np.inf, None, None)
        for slope in slopes:
            shift = np.round(rel * slope / dt).astype(int)
            gathered = np.take_along_axis(
                segment, np.clip(base[None, :] + shift[:, None], 0, width - 1),
                axis=1)
            stack = gathered.sum(axis=0)
            num = np.concatenate(([0.0], np.cumsum(stack ** 2)))
            den = np.concatenate(([0.0], np.cumsum((gathered ** 2).sum(axis=0))))
            score = ((num[size:] - num[:-size])
                     / (gathered.shape[0] * (den[size:] - den[:-size]) + 1e-30))
            j = int(score.argmax())
            if score[j] > best[0]:
                best = (float(score[j]), float(slope),
                        t0 + (lo + j + half) * dt)
        if best[1] is None:
            continue
        rows.append({
            "shot": int(value), "semblance": best[0],
            "slope_s_per_channel": best[1], "intercept_s": best[2],
            "dd_per_channel_m": float(np.polyfit(c, d, 1)[0]),
            "distance_mean_m": float(d.mean()),
            "channels": int(index.size),
        })
    return rows


# ---------------------------------------------------------------------- fit
def huber(A, y, delta, iterations=12):
    weight = np.ones(y.size)
    params = None
    for _ in range(iterations):
        w = np.sqrt(weight)[:, None]
        params, *_ = np.linalg.lstsq(A * w, y * w.ravel(), rcond=None)
        residual = y - A @ params
        scale = max(1.4826 * np.median(np.abs(residual - np.median(residual))),
                    1e-9)
        z = np.maximum(np.abs(residual) / scale, 1e-12)
        weight = np.where(z <= delta / scale, 1.0, (delta / scale) / z)
    return params, y - A @ params


def _columns(rows, water):
    dd = np.asarray([r["dd_per_channel_m"] for r in rows])
    slope = np.asarray([r["slope_s_per_channel"] for r in rows])
    return np.column_stack([dd / water, np.ones(dd.size)]), slope, dd


def fit(rows, water=WATER, delta_s=0.20e-3, bootstrap=400, seed=0):
    A, slope, dd = _columns(rows, water)
    params, residual = huber(A, slope, delta_s)
    shots = np.asarray([r["shot"] for r in rows])
    line = np.asarray([r.get("_line", 0) for r in rows])
    key = line.astype(np.int64) * 1_000_000 + shots

    rng = np.random.default_rng(seed)
    unique = np.unique(key)
    draws = []
    for _ in range(bootstrap):
        chosen = rng.choice(unique, size=unique.size, replace=True)
        index = np.concatenate([np.flatnonzero(key == k) for k in chosen])
        got, _ = huber(A[index], slope[index], delta_s, iterations=8)
        draws.append(got)
    draws = np.asarray(draws).reshape(-1, 2)
    if draws.size:
        scale_ci = [float(np.percentile(draws[:, 0], 2.5)),
                    float(np.percentile(draws[:, 0], 97.5))]
        delay_ci = [float(np.percentile(draws[:, 1], 2.5) * 1e3),
                    float(np.percentile(draws[:, 1], 97.5) * 1e3)]
    else:
        scale_ci = delay_ci = None
    return {
        "spacing_scale": float(params[0]),
        "channel_delay_ms": float(params[1] * 1e3),
        "residual_rms_ms": float(np.std(residual) * 1e3),
        "spacing_scale_ci": scale_ci,
        "channel_delay_ms_ci": delay_ci,
        "shots_used": int(unique.size),
        "dd_spread_m": float(np.ptp(dd)),
    }


def _restricted(rows, water, delta_s, column):
    A, slope, _ = _columns(rows, water)
    params, residual = huber(A[:, [column]], slope, delta_s)
    return float(np.std(residual) * 1e3), float(params[0])


# ------------------------------------------------------------------- assess
def assess(lines, water=WATER, min_semblance=0.30, bootstrap=400,
           delta_ms=0.20):
    """Answer the question, or say why this geometry cannot."""
    delta_s = delta_ms * 1e-3
    per_line, usable = {}, []
    for index, (name, rows) in enumerate(lines.items()):
        kept = [dict(r, _line=index) for r in rows
                if r["semblance"] >= min_semblance]
        dd = np.asarray([r["dd_per_channel_m"] for r in kept]) if kept else np.zeros(0)
        spread = float(np.ptp(dd)) if dd.size else 0.0
        entry = {
            "shots_measured": len(rows),
            "shots_kept": len(kept),
            "dd_per_channel_m": [round(float(dd.min()), 3),
                                 round(float(dd.max()), 3)] if dd.size else None,
            "dd_spread_m": round(spread, 3),
            "median_semblance": round(float(np.median(
                [r["semblance"] for r in rows])), 3) if rows else 0.0,
            "gives_leverage": bool(spread >= MIN_DD_SPREAD_M
                                   and len(kept) >= MIN_SHOTS),
        }
        if dd.size and entry["gives_leverage"]:
            slope = np.asarray([r["slope_s_per_channel"] for r in kept])
            entry["correlation_dd_slope"] = round(
                float(np.corrcoef(dd, slope)[0, 1]), 3)
            usable.append((name, kept))
        # Independent of the spacing-vs-delay question, and available from the same measurement: whether the
        # receiver coordinates are real at all.
        entry["source_tracking"] = source_tracking(
            rows, water=water, min_semblance=min_semblance,
            delta_ms=delta_ms, bootstrap=min(bootstrap, 200))
        per_line[name] = entry
        per_line[name]["_rows"] = kept

    leverage = sum(per_line[n]["dd_spread_m"] for n, _ in usable)
    if not usable:
        return {
            "algorithm_version": ARRAYFIT_VERSION,
            "verdict": "INDETERMINATE",
            "per_line": {k: {a: b for a, b in v.items() if a != "_rows"}
                         for k, v in per_line.items()},
            "reason": (
                "No line here separates a spacing error from a channel delay. "
                "Both add time in proportion to a channel's distance along the "
                "array, so they are one column of the design matrix unless the "
                f"source-receiver distance changes at different rates along the "
                f"array from shot to shot. That needs a spread in dd of at least "
                f"{MIN_DD_SPREAD_M} m; the widest here is "
                f"{max((v['dd_spread_m'] for v in per_line.values()), default=0):.3f} m."),
            "what_would_answer_it": (
                "A line whose source track crosses the array rather than running "
                "along it. Broadside the array is foreshortened by cos(theta) and "
                "the spacing term follows that; the delay does not."),
            "fitting_it_anyway": C.hypothesized(
                None, "withheld on purpose",
                note=("A fit is available from a collinear design matrix and is "
                      "meaningless: on this survey it returns a spacing scale of "
                      "-13.6 and a delay of -30 ms per channel.")),
        }

    rows = [r for _, kept in usable for r in kept]
    answer = fit(rows, water=water, delta_s=delta_s, bootstrap=bootstrap)

    both = answer["residual_rms_ms"]
    spacing_only, spacing_value = _restricted(rows, water, delta_s, 0)
    delay_only, delay_value = _restricted(rows, water, delta_s, 1)

    low, high = answer["spacing_scale_ci"]
    delay_low, delay_high = answer["channel_delay_ms_ci"]
    # An interval containing 1 does not establish the nominal spacing; it fails to reject it, and those are
    # different claims.
    spacing_rejected = not (low <= 1.0 <= high)
    delay_is_real = not (delay_low <= 0.0 <= delay_high)

    held_out = []
    if len(usable) >= 2:
        for train_name, train_rows in usable:
            rest = [r for name, kept in usable if name != train_name for r in kept]
            if not rest:
                continue
            got = fit(train_rows, water=water, delta_s=delta_s, bootstrap=0)
            A, slope, _ = _columns(rest, water)
            predicted = A @ np.array([got["spacing_scale"],
                                      got["channel_delay_ms"] * 1e-3])
            held_out.append({
                "trained_on": train_name,
                "spacing_scale": round(got["spacing_scale"], 4),
                "channel_delay_ms": round(got["channel_delay_ms"], 4),
                "held_out_rms_ms": round(float(np.std(slope - predicted) * 1e3), 3),
            })

    # the lines that carry no leverage never entered the fit, so predicting them is a test rather than a fit
    # statistic
    predictions = []
    for name, entry in per_line.items():
        if entry["gives_leverage"] or not entry["_rows"]:
            continue
        A, slope, _ = _columns(entry["_rows"], water)
        predicted = A @ np.array([answer["spacing_scale"],
                                  answer["channel_delay_ms"] * 1e-3])
        predictions.append({
            "line": name,
            "predicted_slope_ms_per_channel": round(float(np.median(predicted) * 1e3), 3),
            "observed_slope_ms_per_channel": round(float(np.median(slope) * 1e3), 3),
            "difference_ms_per_channel": round(
                float(np.median(slope - predicted) * 1e3), 3),
            "note": ("This line has no leverage on the question, so it was not "
                     "fitted. Its slope is predicted from lines that do."),
        })

    if not spacing_rejected and delay_is_real:
        cause = "per-channel recording delay"
    elif delay_is_real and spacing_rejected:
        cause = "both a spacing error and a per-channel recording delay"
    elif not spacing_rejected and not delay_is_real:
        cause = ("neither is supported: the header geometry is consistent with "
                 "the moveout")
    else:
        cause = "a spacing error"

    return {
        "algorithm_version": ARRAYFIT_VERSION,
        "verdict": "RESOLVED",
        "cause": cause,
        "water_velocity_m_s": C.assumed(water, "caller or default"),
        "spacing_scale": C.derived(
            round(answer["spacing_scale"], 4),
            "slope against dd/V over the lines that cross the array",
            ci_95=[round(low, 4), round(high, 4)],
            nominal_spacing_rejected=bool(spacing_rejected),
            meaning=(
                "The 95% interval excludes 1, so these data reject the nominal "
                "receiver spacing."
                if spacing_rejected else
                "The 95% interval contains 1, so these data provide no evidence "
                "to reject the nominal receiver spacing. That is weaker than "
                "establishing it, and is not the same claim.")),
        "channel_delay_ms": C.derived(
            round(answer["channel_delay_ms"], 4),
            "intercept of the same fit",
            ci_95=[round(delay_low, 4), round(delay_high, 4)],
            differs_from_zero=bool(delay_is_real)),
        "residual_rms_ms": round(both, 4),
        "shots_used": answer["shots_used"],
        "lines_fitted": [name for name, _ in usable],
        "model_comparison": {
            "both_free_rms_ms": round(both, 4),
            "spacing_only_rms_ms": round(spacing_only, 4),
            "spacing_only_scale": round(spacing_value, 4),
            "delay_only_rms_ms": round(delay_only, 4),
            "delay_only_ms_per_channel": round(delay_value * 1e3, 4),
        },
        "held_out": held_out,
        "predicted_for_degenerate_lines": predictions,
        "per_line": {k: {a: b for a, b in v.items() if a != "_rows"}
                     for k, v in per_line.items()},
    }


# --------------------------------------------------------- source tracking A line whose receiver coordinates
# never change is either a real fixed array or one record's positions copied into every trace, and the headers
# cannot tell those apart.
MIN_TRACK_SPAN_MS = 2.0      # absolute floor on the predicted time range
TRACK_SPAN_OVER_SCATTER = 10.0
MIN_TRACK_CORRELATION = 0.90
TRACK_SCALE_BOUNDS = (0.80, 1.25)   # implied velocity 1194-1865 m/s at V=1492

TRACKS, NO_TRACK, TRACK_INCONCLUSIVE = "TRACKS", "DOES_NOT_TRACK", "INCONCLUSIVE"


def source_tracking(rows, water=WATER, min_semblance=0.30, delta_ms=0.20,
                    bootstrap=400, seed=1):
    """Does the arrival time follow the distance the headers predict?"""
    kept = [r for r in rows if r["semblance"] >= min_semblance]
    out = {"shots_measured": len(rows), "shots_used": len(kept)}
    if len(kept) < MIN_SHOTS:
        out.update(verdict=TRACK_INCONCLUSIVE, reason=(
            f"{len(kept)} shots passed the coherence threshold; at least "
            f"{MIN_SHOTS} are needed to regress time on distance."))
        return out

    t = np.asarray([r["intercept_s"] for r in kept])
    d = np.asarray([r["distance_mean_m"] for r in kept]) / water
    A = np.column_stack([d, np.ones(d.size)])
    delta_s = delta_ms * 1e-3
    params, residual = huber(A, t, delta_s)
    scatter = float(np.std(residual) * 1e3)
    span = float(np.ptp(d) * 1e3)
    correlation = float(np.corrcoef(d, t)[0, 1]) if np.ptp(d) > 0 else 0.0

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(bootstrap):
        index = rng.integers(0, d.size, d.size)
        got, _ = huber(A[index], t[index], delta_s, iterations=8)
        draws.append(got)
    draws = np.asarray(draws).reshape(-1, 2)
    scale_ci = ([float(np.percentile(draws[:, 0], 2.5)),
                 float(np.percentile(draws[:, 0], 97.5))] if draws.size else None)

    scale = float(params[0])
    out.update({
        "distance_span_m": round(float(np.ptp(d) * water), 1),
        "predicted_time_span_ms": round(span, 2),
        "residual_rms_ms": round(scatter, 4),
        "correlation": round(correlation, 4),
        "scale": round(scale, 4),
        "scale_ci_95": [round(v, 4) for v in scale_ci] if scale_ci else None,
        "constant_offset_ms": round(float(params[1] * 1e3), 3),
    })
    if scale > 1e-6:
        out["implied_velocity_m_s"] = round(water / scale, 1)

    needed = max(MIN_TRACK_SPAN_MS, TRACK_SPAN_OVER_SCATTER * scatter)
    if span < needed:
        out.update(verdict=TRACK_INCONCLUSIVE, reason=(
            f"The source moved {out['distance_span_m']:.0f} m, which changes the "
            f"predicted arrival by {span:.2f} ms against a measurement scatter of "
            f"{scatter:.2f} ms. A shorter span than {needed:.2f} ms cannot show "
            "whether the time follows the positions or not."))
        return out

    scale_is_physical = (scale_ci is not None
                         and TRACK_SCALE_BOUNDS[0] <= scale <= TRACK_SCALE_BOUNDS[1]
                         and not (scale_ci[0] <= 0.0 <= scale_ci[1]))
    # A scale away from one, with the interval excluding it, does not make the positions untrustworthy, the time
    # still follows them.
    if (scale_ci is not None and not (scale_ci[0] <= 1.0 <= scale_ci[1])
            and scale > 1e-6):
        out["velocity_note"] = (
            f"The arrival timed travels at {water / scale:.0f} m/s, not the "
            f"{water:.0f} m/s assumed (rate {scale:.3f}, 95% interval "
            f"{scale_ci[0]:.3f}-{scale_ci[1]:.3f}, which excludes 1). The "
            "positions are still confirmed; which arrival this is has not "
            "been established.")

    if correlation >= MIN_TRACK_CORRELATION and scale_is_physical:
        out.update(verdict=TRACKS, reason=(
            f"Arrival time follows the header distance over {span:.0f} ms of "
            f"predicted range at {scale:.3f} of the predicted rate "
            f"(correlation {correlation:.3f}, residual {scatter:.2f} ms). The "
            "receiver positions describe a real array, not one record copied "
            "into the rest."))
    else:
        out.update(verdict=NO_TRACK, reason=(
            f"Arrival time does not follow the header distance: rate "
            f"{scale:.3f} of predicted, correlation {correlation:.3f}, over "
            f"{span:.0f} ms of predicted range. Either the receiver "
            "coordinates are not where the receivers were, or the arrival "
            "measured is not the one the distance predicts."))
    return out
