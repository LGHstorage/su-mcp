"""Is the trace time axis anchored at the shot instant?"""

from __future__ import annotations

import numpy as np

TIME_ZERO_VERSION = "timezero-0.1"

# Search range for the flattening velocity around the one the direct wave was detected at, and for the intercept.
VELOCITY_SPAN = 0.05
VELOCITY_SAMPLES = 21
MAX_LAG_S = 0.5

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

__all__ = ["TIME_ZERO_VERSION", "measure", "PASS", "FAIL", "UNKNOWN"]


def _envelope(x):
    n = x.size
    spec = np.fft.fft(x)
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    return np.abs(np.fft.ifft(spec * h))


def _aligned_stack(data, offsets, dt, t0, v, lags):
    """Trace-normalised stack of the traces read at offset / v + lag."""
    ntr, ns = data.shape
    times = offsets[:, None] / v + lags[None, :]
    idx = (times - t0) / dt
    i0 = np.floor(idx).astype(int)
    w = idx - i0
    valid = (i0 >= 0) & (i0 + 1 < ns)
    rows = np.repeat(np.arange(ntr)[:, None], lags.size, axis=1)
    a = np.where(valid, data[rows, np.clip(i0, 0, ns - 1)], 0.0)
    b = np.where(valid, data[rows, np.clip(i0 + 1, 0, ns - 1)], 0.0)
    return ((1 - w) * a + w * b).mean(axis=0)


def measure(raw, offsets, dt, t0, velocity, direct_verdict):
    """Direct-wave intercept against the SEG-Y time axis, and its verdict."""
    if direct_verdict != "ROBUST":
        return {"status": UNKNOWN, "algorithm_version": TIME_ZERO_VERSION,
                "reason": (f"the direct wave is {direct_verdict} at "
                           f"{velocity:.0f} m/s on this gather, so what peaks "
                           f"after flattening need not be the direct wave")}
    raw = np.asarray(raw, dtype=np.float64)
    offsets = np.abs(np.asarray(offsets, dtype=np.float64))
    # The direct wave arrives first at the near offsets; further out a refraction can overtake it and would supply
    # a non-zero intercept of its own.
    near = offsets <= np.median(offsets)
    data = raw[near] - raw[near].mean(axis=1, keepdims=True)
    x = offsets[near]
    if data.shape[0] < 8:
        return {"status": UNKNOWN, "algorithm_version": TIME_ZERO_VERSION,
                "reason": f"only {data.shape[0]} near-offset traces"}
    rms = np.sqrt((data ** 2).mean(axis=1))
    data = data / np.where(rms > 0, rms, 1.0)[:, None]
    lags = np.arange(-MAX_LAG_S, MAX_LAG_S + dt / 2, dt)
    best = None
    for v in np.linspace(velocity * (1 - VELOCITY_SPAN),
                         velocity * (1 + VELOCITY_SPAN), VELOCITY_SAMPLES):
        stack = _aligned_stack(data, x, dt, t0, v, lags)
        env = _envelope(stack)
        k = int(np.argmax(env))
        if best is None or env[k] > best[0]:
            best = (float(env[k]), float(v), float(lags[k]), stack)
    peak, v_best, intercept, stack = best
    # Dominant frequency of the flattened direct wave, from its own spectrum.
    n = 4 * stack.size
    spec = np.abs(np.fft.rfft(stack * np.hanning(stack.size), n=n))
    freqs = np.fft.rfftfreq(n, dt)
    spec[0] = 0.0
    f_dom = float(freqs[int(np.argmax(spec))])
    period = 1.0 / f_dom if f_dom > 0 else float("inf")
    ok = abs(intercept) <= period
    return {
        "status": PASS if ok else FAIL,
        "algorithm_version": TIME_ZERO_VERSION,
        "intercept_s": round(intercept, 4),
        "direct_velocity_m_s": round(v_best, 1),
        "dominant_hz": round(f_dom, 2),
        "tolerance_s": round(period, 4),
        "near_offset_traces": int(data.shape[0]),
        "near_offset_range_m": [round(float(x.min()), 1), round(float(x.max()), 1)],
        "reason": (f"the flattened direct wave peaks {1000 * intercept:+.0f} ms "
                   f"from the SEG-Y time zero, "
                   + ("within" if ok else "beyond")
                   + f" one dominant period ({1000 * period:.0f} ms at "
                   f"{f_dom:.1f} Hz)"
                   + ("" if ok else "; the time axis is not anchored at the "
                      "shot, and every hyperbolic velocity read from it is "
                      "biased")),
    }
