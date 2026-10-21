"""Q0: corrupt samples (v0.30)."""

from __future__ import annotations

import numpy as np

from . import sufile

SANITY_VERSION = "sanity-0.1"
CORRUPT_RATIO = 1.0e6
KILL_MAX_FRACTION = 0.01     # K0 (a)
BLOCK_TRACES = 4000

__all__ = ["SANITY_VERSION", "CORRUPT_RATIO", "KILL_MAX_FRACTION", "trace_stats",
           "scan", "corrupt_mask", "file_stats"]


def trace_stats(data):
    """Per-trace RMS, max |x| (finite part) and non-finite count, in float64."""
    d = np.asarray(data, dtype=np.float64)
    finite = np.isfinite(d)
    nonfinite = (~finite).sum(axis=1)
    dz = np.where(finite, d, 0.0)
    with np.errstate(over="ignore"):
        rms = np.sqrt(np.mean(dz * dz, axis=1))
    return rms, np.abs(dz).max(axis=1) if dz.shape[1] else np.zeros(dz.shape[0]), nonfinite


def corrupt_mask(rms, maxabs, nonfinite):
    """Corrupt traces from per-trace statistics (see module docstring)."""
    rms, maxabs, nonfinite = map(np.asarray, (rms, maxabs, nonfinite))
    live = np.isfinite(rms) & (rms > 0)
    # the median over live traces; a corrupt trace's own RMS is huge, but one in thousands does not move the
    # median
    scale = float(np.median(rms[live])) if live.any() else 0.0
    limit = CORRUPT_RATIO * scale
    bad = (nonfinite > 0) | ~np.isfinite(rms)
    if scale > 0:
        bad |= maxabs > limit
    return bad, scale, limit


def file_stats(path, geom=None):
    """Per-trace statistics of a whole SU file, block by block."""
    geom = geom or sufile.geometry(path)
    ntr = geom["ntr"]
    rms = np.empty(ntr)
    mx = np.empty(ntr)
    nf = np.empty(ntr, dtype=np.int64)
    for a in range(0, ntr, BLOCK_TRACES):
        idx = np.arange(a, min(ntr, a + BLOCK_TRACES))
        r, m, n = trace_stats(sufile.read_traces(path, idx, geom))
        rms[idx], mx[idx], nf[idx] = r, m, n
    return rms, mx, nf


def scan(path, geom=None) -> dict:
    """Q0 over a whole SU file, block by block."""
    geom = geom or sufile.geometry(path)
    ntr = geom["ntr"]
    rms, mx, nf = file_stats(path, geom)
    bad, scale, limit = corrupt_mask(rms, mx, nf)
    bad_idx = np.flatnonzero(bad)
    cdps = []
    if bad_idx.size:
        cdp = np.asarray(sufile.read_header_columns(path, ["cdp"], geom)["cdp"])
        cdps = sorted({int(c) for c in cdp[bad_idx]})
    ratio = float(np.nanmax(mx[~bad]) / scale) if scale > 0 and (~bad).any() else None
    return {"rule": "Q0: a non-finite sample, or |x| > 1e6 x the median live-trace RMS",
            "traces": int(ntr), "median_trace_rms": scale, "limit": limit,
            "corrupt_traces": [int(i) for i in bad_idx[:200]],
            "corrupt_count": int(bad_idx.size), "corrupt_cdps": cdps[:200],
            "corrupt_fraction": round(float(bad_idx.size) / max(1, ntr), 6),
            "max_clean_ratio": None if ratio is None else round(ratio, 1),
            "algorithm_version": SANITY_VERSION}
