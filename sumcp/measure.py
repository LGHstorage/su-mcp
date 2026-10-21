"""Measuring what the data does, rather than inferring it from headers."""

from __future__ import annotations

import numpy as np

from . import claims as C
from . import sufile

__all__ = ["MEASURE_VERSION", "DEFAULT_BANDS", "apparent_velocity",
           "arrival_time_trend", "coherence_scan", "cross_check_velocity"]

MEASURE_VERSION = "measure-0.4"

# raw plus three bands; an event that is real shows the same slope in several.
DEFAULT_BANDS = ((None, None), (10, 60), (40, 120), (100, 300))

WATER_VELOCITY = 1500.0


def _bandpass(panel: np.ndarray, dt: float, lo, hi) -> np.ndarray:
    if lo is None:
        return panel
    spec = np.fft.rfft(panel, axis=-1)
    freq = np.fft.rfftfreq(panel.shape[-1], dt)
    spec[..., (freq < lo) | (freq > hi)] = 0
    return np.fft.irfft(spec, n=panel.shape[-1], axis=-1)


def _semblance_over_slopes(panel: np.ndarray, dt: float, slopes_ms: np.ndarray) -> np.ndarray:
    """Energy of the aligned sum over the summed energy of the traces."""
    n, nt = panel.shape
    out = np.empty(slopes_ms.size)
    for i, slope in enumerate(slopes_ms):
        stack = np.zeros(nt)
        energy = 0.0
        for k in range(n):
            shift = int(round(k * slope / 1000.0 / dt))
            trace = np.roll(panel[k], -shift)
            stack += trace
            energy += float((trace ** 2).sum())
        out[i] = float((stack ** 2).sum()) / (n * energy + 1e-30)
    return out


def _ensemble(path, geom, key, value):
    values = sufile.read_key(path, key, geom)
    idx = np.flatnonzero(values == value)
    if idx.size < 4:
        raise ValueError(f"{key}={value} has {idx.size} traces; need at least 4.")
    order = sufile.read_key(path, "tracf", geom)[idx]
    return idx[np.argsort(order)]


def apparent_velocity(path, *, fldr=None, cdp=None, tmin=None, tmax=None,
                      max_slope_ms=8.0, slope_step_ms=0.25,
                      bands=DEFAULT_BANDS, geom=None,
                      channel_spacing_m=None, predicted_slope_ms=None,
                      spacing_claim=None) -> dict:
    """Slant-stack one ensemble and report the slope where it is most coherent."""
    geom = geom or sufile.geometry(path)
    if fldr is None and cdp is None:
        raise ValueError("Give fldr= or cdp= to choose an ensemble.")
    key, value = ("fldr", fldr) if fldr is not None else ("cdp", cdp)
    idx = _ensemble(path, geom, key, int(value))

    dt = geom["dt_s"] or 0.004
    t0 = geom["t_start_s"]
    start = 0 if tmin is None else max(0, int(round((tmin - t0) / dt)))
    stop = geom["ns"] if tmax is None else min(geom["ns"], int(round((tmax - t0) / dt)))
    if stop - start < 32:
        raise ValueError("The time window is too short to measure anything.")

    rows = []
    for i in idx:
        data, _ = sufile.read_gather(path, int(i), 1, geom)
        rows.append(data[0, start:stop])
    panel = np.asarray(rows, dtype=np.float64)
    panel = np.nan_to_num(panel)

    slopes = np.arange(-max_slope_ms, max_slope_ms + 1e-9, slope_step_ms)
    flat_index = int(np.argmin(np.abs(slopes)))

    per_band = []
    for lo, hi in bands:
        filtered = _bandpass(panel, dt, lo, hi)
        scale = filtered.std(axis=1, keepdims=True)
        scale[scale == 0] = 1.0
        filtered = filtered / scale
        semblance = _semblance_over_slopes(filtered, dt, slopes)
        best = int(np.argmax(semblance))
        per_band.append({
            "band_hz": None if lo is None else [lo, hi],
            "best_slope_ms_per_channel": float(slopes[best]),
            "semblance_at_best": float(semblance[best]),
            "semblance_flat": float(semblance[flat_index]),
            "contrast": float(semblance[best] / (semblance[flat_index] + 1e-30)),
        })

    informative = [b for b in per_band if b["contrast"] >= 1.5]
    best_slopes = np.array([b["best_slope_ms_per_channel"] for b in informative]) \
        if informative else np.array([])
    if best_slopes.size >= 2 and (best_slopes.max() - best_slopes.min()) <= 2 * slope_step_ms:
        consistent = True
        slope = float(np.median(best_slopes))
    elif best_slopes.size >= 2:
        consistent = False
        slope = float(np.median(best_slopes))
    else:
        consistent = False
        slope = float(np.median([b["best_slope_ms_per_channel"] for b in per_band]))

    result = {
        "algorithm_version": MEASURE_VERSION,
        "ensemble": {key: int(value), "n_traces": int(idx.size)},
        "window_s": [float(t0 + start * dt), float(t0 + stop * dt)],
        "per_band": per_band,
        "bands_with_contrast": len(informative),
        "slope_consistent_across_bands": consistent,
        "slope_ms_per_channel": slope,
    }

    # The slope is read off the data; the velocity is the slope divided by a spacing that may have been measured
    # or may have been handed in.
    claims = {"slope_ms_per_channel": C.derived(
        slope, "semblance maximum over slopes, across frequency bands")}

    if channel_spacing_m:
        result["channel_spacing_m"] = float(channel_spacing_m)
        spacing = spacing_claim or C.assumed(
            float(channel_spacing_m), "caller-supplied channel spacing")
        claims["channel_spacing_m"] = spacing
        if abs(slope) > 1e-9:
            result["apparent_velocity_m_s"] = float(channel_spacing_m / (abs(slope) / 1000.0))
            claims["apparent_velocity_m_s"] = C.derived(
                result["apparent_velocity_m_s"],
                "channel spacing divided by the measured slope",
                inputs=[spacing, claims["slope_ms_per_channel"]])
    if predicted_slope_ms is not None:
        result["predicted_slope_ms_per_channel"] = float(predicted_slope_ms)
        if abs(predicted_slope_ms) > 1e-9:
            ratio = slope / predicted_slope_ms
            result["measured_over_predicted"] = float(ratio)
            result["matches_prediction"] = bool(0.85 <= ratio <= 1.15)
            if channel_spacing_m:
                result["predicted_velocity_m_s"] = float(
                    channel_spacing_m / (abs(predicted_slope_ms) / 1000.0))
                claims["predicted_velocity_m_s"] = C.derived(
                    result["predicted_velocity_m_s"],
                    "channel spacing divided by the slope the coordinates predict",
                    inputs=[claims["channel_spacing_m"]])
    result["claims"] = claims
    return result


def _envelope(x: np.ndarray) -> np.ndarray:
    n = x.shape[-1]
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    return np.abs(np.fft.ifft(np.fft.fft(x, axis=-1) * h, axis=-1))


def _pick_by_slope(panel, dt, slope_ms, window_s, step_s, t0):
    """Slide a window and return the time where this slope is most coherent."""
    nwin = max(8, int(round(window_s / dt)))
    hop = max(1, int(round(step_s / dt)))
    best_time, best_contrast = None, -1.0
    for start in range(0, max(1, panel.shape[1] - nwin), hop):
        block = panel[:, start:start + nwin]
        values = _semblance_over_slopes(block, dt, np.array([slope_ms, 0.0]))
        contrast = values[0] / (values[1] + 1e-30)
        if contrast > best_contrast:
            best_contrast = float(contrast)
            best_time = float(t0 + (start + nwin / 2) * dt)
    return best_time, best_contrast


def arrival_time_trend(path, shots, *, tmin, tmax, slope_ms, geom=None,
                       predicted_distance=None, velocity=WATER_VELOCITY,
                       pick_mode="window", band=(40, 120),
                       window_s=0.2, step_s=0.05) -> dict:
    """How the arrival time changes from shot to shot, and what that implies."""
    geom = geom or sufile.geometry(path)
    dt = geom["dt_s"] or 0.004
    t0 = geom["t_start_s"]
    start = max(0, int(round((tmin - t0) / dt)))
    stop = min(geom["ns"], int(round((tmax - t0) / dt)))

    fldr = sufile.read_key(path, "fldr", geom)
    tracf = sufile.read_key(path, "tracf", geom)

    measured = []
    for shot in shots:
        idx = np.flatnonzero(fldr == int(shot))
        if idx.size < 4:
            continue
        idx = idx[np.argsort(tracf[idx])]
        if pick_mode == "scan":
            rows = [np.nan_to_num(sufile.read_gather(path, int(i), 1, geom)[0][0])
                    for i in idx]
            panel = np.asarray(rows, dtype=np.float64)
            if band:
                panel = _bandpass(panel, dt, *band)
            sd = panel.std(axis=1, keepdims=True)
            sd[sd == 0] = 1.0
            time, contrast = _pick_by_slope(panel / sd, dt, slope_ms,
                                            window_s, step_s, t0)
            if time is not None:
                measured.append((int(shot), time, contrast))
            continue
        stack = np.zeros(stop - start)
        for k, i in enumerate(idx):
            data, _ = sufile.read_gather(path, int(i), 1, geom)
            trace = np.nan_to_num(data[0, start:stop]).astype(np.float64)
            sd = trace.std()
            if sd > 0:
                trace = trace / sd
            shift = int(round(k * slope_ms / 1000.0 / dt))
            stack += np.roll(trace, -shift)
        peak = int(np.argmax(_envelope(stack)))
        measured.append((int(shot), float(t0 + (start + peak) * dt), None))

    out = {"algorithm_version": MEASURE_VERSION,
           "pick_mode": pick_mode,
           "window_s": [float(t0 + start * dt), float(t0 + stop * dt)],
           "slope_used_ms_per_channel": float(slope_ms),
           "per_shot": [{"fldr": s, "peak_time_s": t, "contrast": c}
                        for s, t, c in measured]}
    if len(measured) < 3:
        out["note"] = "Too few shots to establish a trend."
        return out

    shot_numbers = np.array([s for s, _, _ in measured], dtype=float)
    times = np.array([t for _, t, _ in measured])
    out["measured_ms_per_shot"] = float(np.polyfit(shot_numbers, times, 1)[0] * 1000)

    if predicted_distance is not None:
        # Fit t = x/V + ti against distance, not shot number: the slope is a velocity measured from the source
        # coordinates alone, which is the independent check on the receiver coordinates.
        distances = np.array([predicted_distance[int(s)] for s, _, _ in measured])
        if distances.max() - distances.min() > 1.0:
            a, b = np.polyfit(distances, times, 1)
            out["source_side"] = {
                "fitted_velocity_m_s": float(1.0 / a) if abs(a) > 1e-12 else None,
                "intercept_s": float(b),
                "correlation_with_distance": float(np.corrcoef(distances, times)[0, 1]),
                "offset_range_m": [float(distances.min()), float(distances.max())],
                "n_shots": int(distances.size),
                "residual_rms_ms": float(np.std(times - (a * distances + b)) * 1000),
            }
        predicted = np.array([predicted_distance[int(s)] for s, _, _ in measured]) / velocity
        out["predicted_ms_per_shot"] = float(np.polyfit(shot_numbers, predicted, 1)[0] * 1000)
        out["correlation_with_prediction"] = float(np.corrcoef(times, predicted)[0, 1])
        ratio = out["measured_ms_per_shot"] / out["predicted_ms_per_shot"] \
            if abs(out["predicted_ms_per_shot"]) > 1e-9 else None
        out["measured_over_predicted"] = ratio
        out["tracks_source_motion"] = bool(
            out["correlation_with_prediction"] > 0.6
            and ratio is not None and 0.5 <= ratio <= 2.0)
    return out


def coherence_scan(path, *, fldr=None, cdp=None, t_start=None, t_end=None,
                   window_s=0.2, step_s=0.05, max_slope_ms=8.0,
                   slope_step_ms=0.25, band=(40, 120), geom=None,
                   channel_spacing_m=None, min_contrast=1.8) -> dict:
    """Slide a window down the record and report every coherent arrival."""
    geom = geom or sufile.geometry(path)
    if fldr is None and cdp is None:
        raise ValueError("Give fldr= or cdp= to choose an ensemble.")
    key, value = ("fldr", fldr) if fldr is not None else ("cdp", cdp)
    idx = _ensemble(path, geom, key, int(value))

    dt = geom["dt_s"] or 0.004
    t0 = geom["t_start_s"]
    first = 0 if t_start is None else max(0, int(round((t_start - t0) / dt)))
    last = geom["ns"] if t_end is None else min(geom["ns"], int(round((t_end - t0) / dt)))

    rows = []
    for i in idx:
        data, _ = sufile.read_gather(path, int(i), 1, geom)
        rows.append(np.nan_to_num(data[0]))
    panel = np.asarray(rows, dtype=np.float64)
    panel = _bandpass(panel, dt, *band) if band else panel
    scale = panel.std(axis=1, keepdims=True)
    scale[scale == 0] = 1.0
    panel = panel / scale

    slopes = np.arange(-max_slope_ms, max_slope_ms + 1e-9, slope_step_ms)
    flat = int(np.argmin(np.abs(slopes)))
    nwin = int(round(window_s / dt))
    hop = max(1, int(round(step_s / dt)))

    grid, times = [], []
    for start in range(first, max(first + 1, last - nwin), hop):
        semblance = _semblance_over_slopes(panel[:, start:start + nwin], dt, slopes)
        grid.append(semblance)
        times.append(t0 + (start + nwin / 2) * dt)
    grid = np.asarray(grid)
    times = np.asarray(times)

    best_slope_index = np.argmax(grid, axis=1)
    best = grid[np.arange(grid.shape[0]), best_slope_index]
    contrast = best / (grid[:, flat] + 1e-30)

    events = []
    for i in range(grid.shape[0]):
        if contrast[i] < min_contrast:
            continue
        lo = max(0, i - 1)
        hi = min(grid.shape[0], i + 2)
        if best[i] < best[lo:hi].max() - 1e-12:
            continue                      # keep only local maxima in time
        slope = float(slopes[best_slope_index[i]])
        event = {"time_s": float(times[i]),
                 "slope_ms_per_channel": slope,
                 "semblance": float(best[i]),
                 "contrast": float(contrast[i])}
        if channel_spacing_m and abs(slope) > 1e-9:
            event["apparent_velocity_m_s"] = float(channel_spacing_m /
                                                   (abs(slope) / 1000.0))
        events.append(event)
    events.sort(key=lambda e: -e["contrast"])

    return {
        "algorithm_version": MEASURE_VERSION,
        "ensemble": {key: int(value), "n_traces": int(idx.size)},
        "scanned_s": [float(t0 + first * dt), float(t0 + last * dt)],
        "window_s": window_s, "step_s": step_s,
        "band_hz": list(band) if band else None,
        "min_contrast": min_contrast,
        "n_windows": int(grid.shape[0]),
        "n_events": len(events),
        "events": events[:20],
        "_grid": grid, "_times": times, "_slopes": slopes,
    }


def cross_check_velocity(receiver_side: dict, trend: dict, tolerance: float = 0.08,
                         array_ray_angle_range_deg=None) -> dict:
    """Do the receiver coordinates and the source coordinates describe one wavefront?"""
    across_channels = receiver_side.get("apparent_velocity_m_s")
    slope = receiver_side.get("slope_ms_per_channel")
    spacing = receiver_side.get("channel_spacing_m")
    source = (trend or {}).get("source_side") or {}
    across_shots = source.get("fitted_velocity_m_s")

    out = {
        "algorithm_version": MEASURE_VERSION,
        "observed": {
            "channel_moveout_ms_per_channel": slope,
            "velocity_across_shots_m_s": across_shots,
            "shot_fit_correlation": source.get("correlation_with_distance"),
            "shot_fit_offset_range_m": source.get("offset_range_m"),
        },
        "derived": {
            "velocity_across_channels_m_s": across_channels,
            "from_header_channel_spacing_m": spacing,
            "note": "A velocity across the channels is the moveout divided by a header "
                    "spacing, so it inherits whatever is wrong with that spacing.",
        },
        "tolerance": tolerance,
    }
    if not across_channels or not across_shots:
        out["agrees"] = None
        out["reason"] = ("One of the two velocities is missing; the check needs both an "
                         "ensemble measurement and a shot-to-shot fit.")
        return out

    ratio = across_channels / across_shots
    out["ratio"] = float(ratio)
    out["agrees"] = bool(abs(ratio - 1.0) <= tolerance)
    if out["agrees"]:
        out["reason"] = (f"The same arrival gives {across_channels:.0f} m/s across the "
                         f"channels and {across_shots:.0f} m/s across the shots; the two "
                         "coordinate sets describe one wavefront.")
        return out

    out["reason"] = (
        f"The same arrival gives {across_channels:.0f} m/s across the channels and "
        f"{across_shots:.0f} m/s against source-receiver distance, a "
        f"{abs(ratio - 1) * 100:.0f}% disagreement. The shot-to-shot fit uses only the "
        "source coordinates, so the receiver side is where the inconsistency lives - "
        "but which part of it is not established.")
    out["hypotheses"] = [
        {"cause": "channel spacing wrong",
         "candidate_spacing_m": (spacing / ratio) if spacing else None,
         "status": "HYPOTHESIZED"},
        {"cause": "per-channel timing delay", "status": "HYPOTHESIZED"},
        {"cause": "receiver positions wrong other than in spacing",
         "status": "HYPOTHESIZED"},
        {"cause": "out-of-plane geometry, or source/receiver depth",
         "status": "HYPOTHESIZED"},
        {"cause": "a different phase measured on different channels",
         "status": "HYPOTHESIZED"},
    ]
    out["cause"] = "UNKNOWN"

    # Spacing and a linear per-channel delay enter the travel time identically when the source stays in line with
    # the array, so an in-line line cannot separate them however well it is measured.
    if array_ray_angle_range_deg:
        lo, hi = array_ray_angle_range_deg
        spread = abs(np.cos(np.radians(lo)) - np.cos(np.radians(hi)))
        out["separability"] = {
            "array_ray_angle_deg": [float(lo), float(hi)],
            "cos_spread": float(spread),
            "can_separate_spacing_from_timing": bool(spread > 0.15),
            "note": ("A spacing error scales with cos(angle between the array axis and "
                     "the ray); a timing delay does not. Separating them needs lines "
                     "where that cosine varies."
                     if spread <= 0.15 else
                     "This line's geometry varies enough to tell a spacing error from a "
                     "timing delay."),
        }
    return out


def channel_geometry_fit(path, *, shots=None, tmin_window_s=0.25, velocity=1492.0,
                         band=(40, 200), max_slope_ms=6.0, slope_step_ms=0.05,
                         min_contrast=1.5, geom=None, spacing_m=None,
                         sample_interval_s=None) -> dict:
    """Test what the channel moveout needs, beyond the header geometry, to fit."""
    geom = geom or sufile.geometry(path)
    dt = geom["dt_s"] or 0.004
    t0 = geom["t_start_s"]
    fldr = sufile.read_key(path, "fldr", geom)
    tracf = sufile.read_key(path, "tracf", geom)
    from . import geometry as _geometry
    resolved = _geometry.resolve_coordinates(path, geom)
    s = resolved["_scaled"]

    if shots is None:
        shots = [int(v) for v in np.unique(fldr)]
    slopes = np.arange(-max_slope_ms, max_slope_ms + 1e-9, slope_step_ms)
    flat = int(np.argmin(np.abs(slopes)))

    predicted, measured, used = [], [], []
    for shot in shots:
        idx = np.flatnonzero(fldr == int(shot))
        if idx.size < 8:
            continue
        idx = idx[np.argsort(tracf[idx])]
        rx, ry = s["gx"][idx], s["gy"][idx]
        sx, sy = s["sx"][idx][0], s["sy"][idx][0]
        dist = np.hypot(rx - sx, ry - sy)
        k = np.arange(idx.size)
        pred = float(np.polyfit(k, dist / velocity * 1000.0, 1)[0])

        centre = int(((float(np.median(dist)) / velocity) - t0) / dt)
        half = int(tmin_window_s / dt)
        lo, hi = max(0, centre - half), min(geom["ns"], centre + half)
        if hi - lo < 32:
            continue
        rows = [sufile.read_gather(path, int(i), 1, geom)[0][0][lo:hi] for i in idx]
        panel = np.nan_to_num(np.asarray(rows, dtype=np.float64))
        if band:
            panel = _bandpass(panel, dt, *band)
        sd = panel.std(axis=1, keepdims=True)
        sd[sd == 0] = 1.0
        values = _semblance_over_slopes(panel / sd, dt, slopes)
        best = int(np.argmax(values))
        if values[best] / (values[flat] + 1e-30) < min_contrast:
            continue
        predicted.append(pred)
        measured.append(float(slopes[best]))
        used.append(int(shot))

    predicted = np.asarray(predicted)
    measured = np.asarray(measured)
    spacing_m = spacing_m or 3.1246
    out = {"algorithm_version": MEASURE_VERSION,
           "n_shots_used": int(predicted.size),
           "assumed_velocity_m_s": float(velocity),
           "header_channel_spacing_m": float(spacing_m),
           "predicted_slope_range_ms": ([float(predicted.min()), float(predicted.max())]
                                        if predicted.size else None)}
    if predicted.size < 8:
        out["status"] = "INSUFFICIENT"
        out["reason"] = "Too few shots with a coherent arrival to fit anything."
        return out

    spread = float(predicted.max() - predicted.min())
    out["predicted_slope_spread_ms"] = spread
    if spread < 0.3:
        out["status"] = "DEGENERATE"
        out["reason"] = (
            f"The predicted moveout varies by only {spread:.3f} ms across these shots, so "
            "a geometry scale and a per-channel delay produce the same thing here and "
            "cannot be separated. A line where the source crosses the array's axis can "
            "separate them.")
        return out

    def _fit(fixed_b=None):
        if fixed_b is None:
            a, b = np.polyfit(predicted, measured, 1)
        else:
            b = float(fixed_b)
            a = float(predicted @ (measured - b) / (predicted @ predicted))
        resid = measured - (a * predicted + b)
        return {"a": float(a), "b_ms_per_channel": float(b),
                "residual_rms_ms": float(np.std(resid)),
                "implied_spacing_m": float(spacing_m * a)}

    free = _fit()
    no_delay = _fit(0.0)
    models = {"scale_and_delay": free, "scale_only": no_delay}
    if sample_interval_s:
        models["scale_and_one_sample_delay"] = _fit(sample_interval_s * 1000.0)

    n = predicted.size
    se = free["residual_rms_ms"] * np.sqrt(
        1.0 / n + predicted.mean() ** 2 / ((predicted - predicted.mean()) ** 2).sum())
    out.update({
        "status": "FITTED",
        "correlation": float(np.corrcoef(predicted, measured)[0, 1]),
        "models": models,
        "delay_standard_error_ms": float(se),
        "delay_significance_sigma": float(abs(free["b_ms_per_channel"]) / se) if se else None,
        "delay_needed": bool(no_delay["residual_rms_ms"] >
                             free["residual_rms_ms"] * 1.2),
    })
    out["observed"] = {"measured_slope_ms_per_channel": [round(float(v), 3) for v in measured[:8]],
                       "shots": used[:8]}
    out["derived"] = {"a": free["a"],
                      "note": "a is a scale on the geometry: the channel spacing and the "
                              "assumed velocity enter it identically and this fit cannot "
                              "separate them."}
    out["conclusion"] = (
        "A per-channel delay is required: dropping it makes the fit "
        f"{no_delay['residual_rms_ms'] / free['residual_rms_ms']:.2f} times worse."
        if out["delay_needed"] else
        "The header geometry with a single scale explains the moveout; no per-channel "
        "delay is needed.")
    return out
