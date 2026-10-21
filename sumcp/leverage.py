"""Moveout leverage: one formula, two callers."""

from __future__ import annotations

import numpy as np

__all__ = ["LEVERAGE_VERSION", "NONE", "MARGINAL", "USABLE",
           "NONE_BELOW_MS", "MARGINAL_BELOW_MS", "MIN_VELOCITY_LEVERAGE_SAMPLES",
           "aperture", "moveout_spread_s", "hyperbola_leverage",
           "velocity_axis_leverage", "grade"]

LEVERAGE_VERSION = "leverage-0.1"

NONE, MARGINAL, USABLE = "NONE", "MARGINAL", "USABLE"

# Unchanged from cmp/geometry: below 2 ms of moveout across the aperture the traces are at effectively one
# moveout; below 20 ms a velocity scan is poorly constrained.
NONE_BELOW_MS = 2.0
MARGINAL_BELOW_MS = 20.0

# Unchanged from reflection: the velocity axis has to move the arrival by at least two samples across its whole
# range to be readable at all.
MIN_VELOCITY_LEVERAGE_SAMPLES = 2.0


def aperture(offsets, quantiles=(0.05, 0.95)) -> dict:
    """The offset aperture of a gather, exactly and robustly."""
    x = np.abs(np.asarray(offsets, dtype=np.float64).ravel())
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"traces": 0, "offset_min_m": 0.0, "offset_max_m": 0.0,
                "offset_robust_lo_m": 0.0, "offset_robust_hi_m": 0.0,
                "offset_squared_span_m2": 0.0, "distinct_offsets": 0}
    lo, hi = float(x.min()), float(x.max())
    rlo, rhi = (float(np.quantile(x, quantiles[0])),
                float(np.quantile(x, quantiles[1]))) if x.size > 2 else (lo, hi)
    return {
        "traces": int(x.size),
        "offset_min_m": round(lo, 3),
        "offset_max_m": round(hi, 3),
        "offset_robust_lo_m": round(rlo, 3),
        "offset_robust_hi_m": round(rhi, 3),
        "offset_squared_span_m2": round(hi ** 2 - lo ** 2, 3),
        "distinct_offsets": int(np.unique(np.round(x, 3)).size),
    }


def moveout_spread_s(x_lo: float, x_hi: float, velocity: float,
                     t0: float) -> float:
    """Traveltime difference between the ends of the aperture, on one hyperbola."""
    if velocity <= 0:
        return 0.0
    return float(np.sqrt(t0 ** 2 + (x_hi / velocity) ** 2)
                 - np.sqrt(t0 ** 2 + (x_lo / velocity) ** 2))


def grade(spread_ms: float) -> str:
    if spread_ms < NONE_BELOW_MS:
        return NONE
    if spread_ms < MARGINAL_BELOW_MS:
        return MARGINAL
    return USABLE


def hyperbola_leverage(offsets, velocity_m_s: float, t0_s: float,
                       dt: float | None = None) -> dict:
    """Moveout the aperture produces on one reference hyperbola."""
    ap = aperture(offsets)
    spread = moveout_spread_s(ap["offset_min_m"], ap["offset_max_m"],
                              velocity_m_s, t0_s)
    ms = spread * 1e3
    out = {
        "algorithm_version": LEVERAGE_VERSION,
        "form": "single_hyperbola",
        "reference_velocity_m_s": float(velocity_m_s),
        "reference_t0_s": float(t0_s),
        **ap,
        "moveout_spread_ms": round(ms, 4),
        "moveout_spread_samples": round(spread / dt, 3) if dt else None,
        "status": grade(ms),
    }
    if out["status"] == NONE:
        out["reason"] = (
            f"the traces span {ap['offset_min_m']:.1f}-{ap['offset_max_m']:.1f} m "
            f"of offset, which at {velocity_m_s:g} m/s and {t0_s:g} s is "
            f"{ms:.2f} ms of moveout -- effectively one moveout")
    return out


def velocity_axis_leverage(offsets, dt: float, t0_s: float,
                           v_min: float, v_max: float) -> dict:
    """How much the velocity axis can change what this gather looks like."""
    ap = aperture(offsets)
    lo, hi = ap["offset_min_m"], ap["offset_max_m"]
    at_v_min = moveout_spread_s(lo, hi, v_min, t0_s)
    at_v_max = moveout_spread_s(lo, hi, v_max, t0_s)
    spread = abs(at_v_min - at_v_max)
    samples = spread / dt if dt else 0.0
    resolvable = bool(samples >= MIN_VELOCITY_LEVERAGE_SAMPLES)
    out = {
        "algorithm_version": LEVERAGE_VERSION,
        "form": "velocity_axis",
        "reference_t0_s": round(float(t0_s), 4),
        "velocity_grid_m_s": [round(float(v_min), 1), round(float(v_max), 1)],
        **ap,
        "aperture_moveout_at_v_min_ms": round(at_v_min * 1e3, 4),
        "aperture_moveout_at_v_max_ms": round(at_v_max * 1e3, 4),
        "moveout_spread_ms": round(spread * 1e3, 4),
        "moveout_spread_samples": round(float(samples), 3),
        "status": grade(spread * 1e3),
        "resolvable": resolvable,
        # Kept because it is what the previous version read, and a reader comparing the two should see why the
        # answer moved.
        "max_offset_m": ap["offset_max_m"],
    }
    if not resolvable:
        if ap["offset_max_m"] - ap["offset_min_m"] <= 0:
            why = (f"every trace sits at {ap['offset_max_m']:.1f} m, so every "
                   f"velocity flattens them equally and the semblance panel "
                   f"says the same thing everywhere")
        else:
            why = (f"the aperture is {ap['offset_min_m']:.1f}-"
                   f"{ap['offset_max_m']:.1f} m, and across the whole velocity "
                   f"grid ({v_min:.0f}-{v_max:.0f} m/s) that changes the "
                   f"traveltime difference across the gather by only "
                   f"{spread * 1e3:.3f} ms, {samples:.2f} samples")
        out["reason"] = (
            f"No velocity leverage: {why}. The scan cannot tell one velocity "
            f"from another, so any semblance it reports is a statement about "
            f"flatness, not about velocity.")
    return out
