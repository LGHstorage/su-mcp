"""Is there a reflection in here at all, and would we have seen one?"""

from __future__ import annotations

import time

import numpy as np

from . import claims as C
from . import leverage as LEV
from . import timezero as TZ

REFLECTION_VERSION = "reflection-0.8"

DEFAULT_WATER = 1492.0
CORRIDOR_S = 0.12

# How much of the aperture must separate a candidate from the direct wave before it counts as a different event.
SEPARATION_FRACTION = 0.65

# Verdicts.
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"

# Above this injected amplitude the gather is not sensitive enough for a negative result to mean anything.
INFORMATIVE_THRESHOLD_X_RMS = 0.5
# v0.16: an absence found in the analysis band speaks for the record only when the band holds most of the record's
# energy.
MIN_BAND_ENERGY_FRACTION = 0.5

# A velocity semblance scan reads a velocity from the CURVATURE of an event across offset.
MIN_VELOCITY_LEVERAGE_SAMPLES = 2.0

ROBUST, FRAGILE, ABSENT = "ROBUST", "FRAGILE", "ABSENT"

# A branch only gets a vote if it left alone the part of the record it was not asked to touch.
MIN_OUTSIDE_KEPT_NO_DIRECT = 0.85
MIN_VOTERS = 2
# The live-trace count below which velocity_semblance returns an identically zero row.
MIN_SEMBLANCE_TRACES = 20

# A branch is not simply in or out of the vote.
BRANCH_VALID = "VALID"
BRANCH_BROKEN = "BROKEN"
BRANCH_NOT_APPLICABLE = "NOT_APPLICABLE"

__all__ = ["REFLECTION_VERSION", "assess", "band_energy_fraction", "band_limited_absence", "mute_predicted",
           "subtract_template", "suppress_slant", "velocity_semblance",
           "MIN_SEMBLANCE_TRACES",
           "direct_stack_peak", "agc", "agc_gain"]


# ---------------------------------------------------------------- utilities
def bandpass(a, dt, lo, hi):
    spec = np.fft.rfft(a, axis=-1)
    freq = np.fft.rfftfreq(a.shape[-1], dt)
    spec[..., (freq < lo) | (freq > hi)] = 0
    return np.fft.irfft(spec, n=a.shape[-1], axis=-1)


def shift_lin(data, seconds, dt):
    """Non-circular sub-sample shift: pad to 2n, phase shift, crop back."""
    n = data.shape[-1]
    pad = np.zeros(data.shape[:-1] + (2 * n,))
    pad[..., :n] = data
    spec = np.fft.rfft(pad, axis=-1)
    freq = np.fft.rfftfreq(2 * n, dt)
    sec = np.atleast_1d(seconds)[:, None] if data.ndim == 2 else seconds
    return np.fft.irfft(spec * np.exp(-2j * np.pi * freq * sec), n=2 * n,
                        axis=-1)[..., :n]


def agc_gain(data, dt, window_s=0.5, floor=0.05):
    """Sliding-RMS gain computed once, from the gather before any suppression."""
    k = max(1, int(window_s / dt))
    kern = np.ones(k) / k
    power = np.apply_along_axis(lambda r: np.convolve(r, kern, mode="same"),
                                1, data ** 2)
    rms = np.sqrt(power)
    return rms + floor * float(np.sqrt((data ** 2).mean()))


def agc(data, dt, window_s=0.5, floor=0.05):
    return data / agc_gain(data, dt, window_s, floor)


# ---------------------------------------------------------------- branch 1
def mute_predicted(data, offsets, dt, t0, water=DEFAULT_WATER,
                   half_s=0.06, taper_s=0.03):
    """Zero a window centred on the coordinate-predicted arrival."""
    t = t0 + np.arange(data.shape[1]) * dt
    gap = np.abs(t[None, :] - (offsets[:, None] / water))
    window = np.ones_like(gap)
    window[gap <= half_s] = 0.0
    ramp = (gap > half_s) & (gap < half_s + taper_s)
    window[ramp] = 0.5 * (1 - np.cos(np.pi * (gap[ramp] - half_s) / taper_s))
    return data * window


# ---------------------------------------------------------------- branch 2
def subtract_template(data, offsets, dt, t0, water=DEFAULT_WATER, t_ref=None,
                      window_s=0.12, passes=4, max_scale=2.0):
    """Adaptive subtraction of a leave-one-out template in the flattened domain."""
    n, ntr = data.shape[1], data.shape[0]
    if t_ref is None:
        t_ref = t0 + 0.5 * n * dt
    delay = t_ref - (offsets / water - t0)
    aligned = shift_lin(data, delay, dt)
    half = int(window_s / dt / 2)
    centre = int((t_ref - t0) / dt)
    lo, hi = max(0, centre - half), min(n, centre + half)
    gain = np.sqrt((aligned[:, lo:hi] ** 2).mean(axis=1)) + 1e-30
    work = aligned / gain[:, None]
    for _ in range(passes):
        # Every trace's template is the mean of the other ntr-1, and all of them are formed from the pass's
        # starting sum, so the whole pass is one set of array operations, not 194 small dot products.
        seg = work[:, lo:hi]
        template = (seg.sum(axis=0)[None, :] - seg) / max(1, ntr - 1)
        energy = (template * template).sum(axis=1)
        scale = np.where(energy > 0,
                         (seg * template).sum(axis=1) / np.where(energy > 0, energy, 1.0),
                         0.0)
        scale = np.clip(scale, 0.0, max_scale)
        work[:, lo:hi] = seg - scale[:, None] * template
    return shift_lin(work * gain[:, None], -delay, dt)


# ---------------------------------------------------------------- branch 3
def _sinc_apply(z, x, dx, a):
    """Apply sinc(a_f (x_k - x_l)) to z_f for every frequency at once."""
    off_diag = ~np.eye(x.size, dtype=bool)
    closest = float(np.abs(dx[off_diag]).min()) if x.size > 1 else 0.0
    if closest < 1e-6 * max(1.0, float(np.abs(x).max())):
        return np.stack([np.sinc(a[f] * dx) @ z[f] for f in range(a.size)])
    gram = np.zeros_like(dx)
    gram[off_diag] = 1.0 / dx[off_diag]
    phase = np.pi * np.outer(a, x)
    sin_p, cos_p = np.sin(phase), np.cos(phase)
    return (sin_p * ((cos_p * z) @ gram.T)
            - cos_p * ((sin_p * z) @ gram.T)) / (np.pi * a)[:, None] + z


def suppress_slant(data, offsets, dt, t0, water=DEFAULT_WATER, dv=200.0,
                   damping=0.02, f_lo=30.0, f_hi=250.0):
    """Least-squares tau-p centred on the direct-wave slowness, band-reject."""
    n = data.shape[1]
    x = offsets - offsets.mean()
    dx = x[:, None] - x[None, :]
    step = float(np.median(np.abs(np.diff(np.sort(offsets))))) or 1.0
    aperture = float(offsets.max() - offsets.min()) or 1.0
    spec = np.fft.rfft(data, axis=1)
    freq = np.fft.rfftfreq(n, dt)
    band = np.flatnonzero((freq >= f_lo) & (freq <= f_hi))
    if band.size == 0:
        return data.copy()

    p0 = 1.0 / water
    f = freq[band]
    half_range = 1.0 / (2.0 * f * step)
    w = np.minimum(np.maximum(dv / water ** 2, 4.0 / (f * aperture)),
                   0.5 * half_range)
    inv_gram = np.linalg.inv(np.sinc(dx / step) + damping * np.eye(x.size))
    carrier = np.exp(-2j * np.pi * np.outer(f, x) * p0)
    z = (carrier.conj() * spec[:, band].T) @ inv_gram.T
    out = _sinc_apply(z, x, dx, 2.0 * w * f)

    model = np.zeros_like(spec)
    model[:, band] = ((w / half_range)[:, None] * carrier * out).T
    return data - np.fft.irfft(model, n=n, axis=1)


# ---------------------------------------------------------------- detector
def velocity_semblance(data, offsets, dt, t0, t0_grid, v_grid, window_s=0.04,
                       min_traces=MIN_SEMBLANCE_TRACES):
    """Semblance over a (t0, velocity) grid, one t0 row at a time."""
    ntr, n = data.shape
    # float32 for the detector only: semblance is a ratio, the extra precision buys nothing, and halving the
    # memory traffic through the gather is what the cost of this scan actually is.
    data = np.ascontiguousarray(data, dtype=np.float32)
    half = max(1, int(window_s / dt / 2))
    rel = np.arange(-half, half)
    trace = np.arange(ntr)[None, :, None]
    out = np.zeros((t0_grid.size, v_grid.size))
    for a, tz in enumerate(t0_grid):
        times = np.sqrt(tz ** 2 + (offsets[None, :] / v_grid[:, None]) ** 2)
        idx = ((times - t0) / dt).astype(np.int64)
        ok = (idx >= half) & (idx < n - half)
        count = ok.sum(axis=1)
        gather = data[trace, np.clip(idx, half, n - half - 1)[:, :, None] + rel]
        gather = gather * ok[:, :, None].astype(np.float32)
        num = (gather.sum(axis=1) ** 2).sum(axis=1)
        energy = (gather ** 2).sum(axis=(1, 2))
        good = count >= min_traces
        out[a, good] = num[good] / (count[good] * energy[good] + 1e-30)
    return out


def peaks(semb, t0_grid, v_grid, top=5, separation_s=0.15):
    found = []
    for k in np.argsort(semb.ravel())[::-1]:
        a, b = divmod(int(k), v_grid.size)
        if semb[a, b] <= 0:
            break
        if any(abs(t0_grid[a] - f["t0_s"]) < separation_s for f in found):
            continue
        found.append({"t0_s": float(t0_grid[a]), "v_m_s": float(v_grid[b]),
                      "semblance": float(semb[a, b])})
        if len(found) >= top:
            break
    return found


def corridor_mask(shape, offsets, dt, t0, water=DEFAULT_WATER,
                  half_s=CORRIDOR_S):
    """Samples within half_s of the predicted direct arrival."""
    t = t0 + np.arange(shape[1]) * dt
    return np.abs(t[None, :] - (offsets[:, None] / water)) < half_s


def direct_stack_peak(data, offsets, dt, t0, water=DEFAULT_WATER, t_ref=None,
                      half_s=0.08):
    """Peak of the trace-normalised stack after flattening at the water velocity."""
    n = data.shape[1]
    if t_ref is None:
        t_ref = t0 + 0.5 * n * dt
    delay = t_ref - (offsets / water - t0)
    aligned = shift_lin(data, delay, dt)
    norm = aligned / (np.sqrt((aligned ** 2).mean(axis=1))[:, None] + 1e-30)
    stack = norm.mean(axis=0)
    c, h = int((t_ref - t0) / dt), int(half_s / dt)
    return float(np.abs(stack[max(0, c - h):min(n, c + h)]).max())


# ---------------------------------------------------------------- injection
def inject_reflection(data, offsets, dt, t0, t_ref, v_ref, amplitude, f0=60.0):
    """Add a hyperbolic reflection of known strength to the real gather."""
    t = t0 + np.arange(data.shape[1]) * dt
    rms = float(np.sqrt((data ** 2).mean()))
    out = data.copy()
    for i, x in enumerate(offsets):
        tc = float(np.sqrt(t_ref ** 2 + (x / v_ref) ** 2))
        a = (t - tc) * np.pi * f0
        out[i] += amplitude * rms * (t_ref / tc) * (1 - 2 * a ** 2) * np.exp(-a ** 2)
    return out


def _branches(data, offsets, dt, t0, water):
    return {
        "predicted_mute": mute_predicted(data, offsets, dt, t0, water),
        "template_subtraction": subtract_template(data, offsets, dt, t0, water),
        "slant_domain": suppress_slant(data, offsets, dt, t0, water),
    }


def _scan(panel, offsets, dt, t0, t0_grid, v_grid, gain, top=5):
    return peaks(velocity_semblance(panel / gain, offsets, dt, t0,
                                    t0_grid, v_grid), t0_grid, v_grid, top)


def _cell(semb, t0_grid, v_grid, t_ref, v_ref):
    a = int(np.abs(t0_grid - t_ref).argmin())
    b = int(np.abs(v_grid - v_ref).argmin())
    lo_a, hi_a = max(0, a - 5), min(t0_grid.size, a + 6)
    lo_b, hi_b = max(0, b - 6), min(v_grid.size, b + 7)
    return float(semb[lo_a:hi_a, lo_b:hi_b].max())


def _agreement(report, voters, level, offsets, water, min_sep, direct_present,
               v_step=50.0):
    """Candidates every qualified branch sees, and why the others were dropped."""
    lead = report[voters[0]]["peaks"]
    agreed, rejected, seen = [], [], set()
    for peak in lead:
        matches = [peak]
        for other in voters[1:]:
            found = [q for q in report[other]["peaks"]
                     if abs(q["t0_s"] - peak["t0_s"]) < 0.1
                     and abs(q["v_m_s"] - peak["v_m_s"]) < 300]
            if not found:
                break
            matches.append(max(found, key=lambda q: q["semblance"]))
        if len(matches) < len(voters):
            continue
        tag = (round(peak["t0_s"], 2), round(peak["v_m_s"]))
        if tag in seen:
            continue
        seen.add(tag)

        scores = [m["semblance"] for m in matches]
        sep_frac, sep_min = _direct_separation(peak["t0_s"], peak["v_m_s"],
                                               offsets, water, min_sep)
        candidate = {
            "t0_s": peak["t0_s"], "v_m_s": peak["v_m_s"],
            "semblance": scores, "agreed_by": list(voters),
            "separated_offset_fraction": round(sep_frac, 3),
            "closest_approach_to_direct_s": round(sep_min, 3),
        }
        if min(scores) <= level:
            candidate["rejected"] = (
                f"weakest voting branch semblance {min(scores):.4f} does not clear "
                f"the {level:.4f} level that moveout-destroyed noise reaches on "
                f"this gather")
            rejected.append(candidate)
        elif direct_present and peak["v_m_s"] < water - v_step:
            # v0.15: a primary reflection from beneath the layer the direct wave travels in cannot move out slower
            # than that layer.
            candidate["rejected"] = (
                f"its moveout velocity {peak['v_m_s']:.0f} m/s is below the "
                f"{water:.0f} m/s direct wave by more than one scan step "
                f"({v_step:.0f} m/s); a primary reflection from beneath the "
                f"layer the direct wave travels in cannot move out slower "
                f"than it, so this is residue or a near-surface mode")
            rejected.append(candidate)
        elif direct_present and sep_frac < SEPARATION_FRACTION:
            candidate["rejected"] = (
                f"its moveout stays within one {1000 * min_sep:.0f} ms period of "
                f"the direct wave over {(1 - sep_frac) * 100:.0f}% of the recorded "
                f"offsets (a real reflection separates over at least "
                f"{SEPARATION_FRACTION:.0%}), so it cannot be told from "
                f"direct-wave residue")
            rejected.append(candidate)
        else:
            agreed.append(candidate)
    return agreed, rejected


def _significance_level(data, offsets, dt, t0, t0_grid, v_grid, gain,
                        trials=8, quantile=0.9, seed=0):
    """How high does semblance get on this gather with the moveout destroyed?"""
    rng = np.random.default_rng(seed)
    ntr, n = data.shape
    equalised = data / gain
    rows = np.arange(ntr)[:, None]
    column = np.arange(n)[None, :]
    highs = []
    for _ in range(trials):
        # One gather rather than 194 separate np.roll calls per trial.
        shift = rng.integers(n, size=ntr)[:, None]
        shuffled = equalised[rows, (column - shift) % n]
        highs.append(float(velocity_semblance(shuffled, offsets, dt, t0,
                                              t0_grid, v_grid).max()))
    return float(np.quantile(highs, quantile)), highs


def _direct_separation(t_zero, v, offsets, water, min_sep):
    """How much of the aperture separates a candidate from the direct wave."""
    gap = np.abs(np.sqrt(t_zero ** 2 + (offsets / v) ** 2) - offsets / water)
    return float((gap > min_sep).mean()), float(gap.min())


def _detected(semb, t0_grid, v_grid, t_ref, v_ref, baseline, floor, margin=2.0):
    """Did injecting the event light up its own cell, relative to before?"""
    got = _cell(semb, t0_grid, v_grid, t_ref, v_ref)
    return got > max(margin * baseline, 2.0 * floor), got


def _pick_probe(semb, t0_grid, v_grid, water, dv=200.0, edge=6):
    """Put the test event where the gather is quietest."""
    ok_v = np.flatnonzero(v_grid > water + 3.0 * dv)
    if ok_v.size == 0:
        ok_v = np.arange(v_grid.size)
    # Neighbourhood maximum by sliding the grid rather than by a Python loop over every cell: same answer, one
    # pass instead of several thousand tiny array slices.
    local = semb.copy()
    for shift in range(1, 6):
        local = np.maximum(local, np.roll(semb, shift, axis=0))
        local = np.maximum(local, np.roll(semb, -shift, axis=0))
    rows = local.copy()
    for shift in range(1, 7):
        local = np.maximum(local, np.roll(rows, shift, axis=1))
        local = np.maximum(local, np.roll(rows, -shift, axis=1))
    blocked = np.full(semb.shape, np.inf)
    a_lo, a_hi = edge, max(edge + 1, t0_grid.size - edge)
    keep_v = ok_v[(ok_v >= edge) & (ok_v < v_grid.size - edge)]
    if keep_v.size == 0:
        keep_v = ok_v
    blocked[a_lo:a_hi, keep_v] = local[a_lo:a_hi, keep_v]
    a, b = np.unravel_index(int(blocked.argmin()), blocked.shape)
    return float(t0_grid[a]), float(v_grid[b])


def _perturbations(raw, offsets, dt, f_lo, f_hi):
    """A fixed set of ways to ask the same question with less data."""
    ntr = raw.shape[0]
    mid_f = 0.5 * (f_lo + f_hi)
    half = ntr // 2
    everything = np.arange(ntr)
    return [
        ("all traces, full band", everything, (f_lo, f_hi)),
        ("near half of the offsets", everything[:half], (f_lo, f_hi)),
        ("far half of the offsets", everything[half:], (f_lo, f_hi)),
        ("every other trace", everything[::2], (f_lo, f_hi)),
        ("lower half of the band", everything, (f_lo, mid_f)),
        ("upper half of the band", everything, (mid_f, f_hi)),
    ]


def direct_wave_evidence(raw, offsets, dt, t0, water, f_lo, f_hi):
    """How reliably the direct wave is detectable, not whether it is."""
    trials = []
    for label, sel, (lo, hi) in _perturbations(raw, offsets, dt, f_lo, f_hi):
        if sel.size < 8 or hi <= lo:
            continue
        panel = bandpass(raw[sel], dt, lo, hi)
        present, peak, decoys = _direct_wave_present(panel, offsets[sel], dt,
                                                     t0, water)
        trials.append({"condition": label, "traces": int(sel.size),
                       "band_hz": [round(lo, 1), round(hi, 1)],
                       "detected": bool(present),
                       "stack_peak": round(peak, 4), "decoy_peaks": decoys})
    hits = sum(t["detected"] for t in trials)
    total = max(1, len(trials))
    verdict = (ROBUST if hits >= 0.75 * total
               else ABSENT if hits <= 0.15 * total
               else FRAGILE)
    return {
        "verdict": verdict,
        "detected_in": f"{hits} of {total} conditions",
        "trials": trials,
        "note": {
            ROBUST: "The direct wave is detectable under every condition tried; "
                    "the suppression figures below are meaningful.",
            FRAGILE: "Detection depends on how much of the gather and how much "
                     "bandwidth the test is given. The direct wave is there, but "
                     "any figure derived from it is only as good as the data it "
                     "was measured on -- do not quote it from a subset.",
            ABSENT: "No direct wave is detectable at this velocity under any "
                    "condition tried. The three branches had nothing to "
                    "suppress, so their suppression figures are not meaningful.",
        }[verdict],
    }


def _direct_wave_present(data, offsets, dt, t0, water):
    """Is there a direct wave here at all?"""
    real = direct_stack_peak(data, offsets, dt, t0, water)
    decoys = [direct_stack_peak(data, offsets, dt, t0, v)
              for v in (0.75 * water, 1.4 * water)]
    return real > 1.5 * max(decoys), real, [round(d, 4) for d in decoys]


# ---------------------------------------------------------------- the answer
def velocity_leverage(offsets, dt, t0_grid, v_grid) -> dict:
    """Can this gather tell one velocity from another at all?"""
    t_ref = float(np.min(t0_grid))
    return LEV.velocity_axis_leverage(offsets, dt, t_ref,
                                      float(np.min(v_grid)),
                                      float(np.max(v_grid)))


# --------------------------------------------------------------------------- Evidence of
# absence,-------------------------------------------------------------------------
def _detector_validity(raw_semb, level, leverage) -> dict:
    """Is the raw semblance detector itself usable on this gather?"""
    panel = np.asarray(raw_semb, dtype=np.float64)
    checks = {
        "velocity_axis_readable": bool(leverage.get("resolvable")),
        "panel_finite": bool(panel.size and np.isfinite(panel).all()),
        "panel_varies": bool(panel.size
                             and float(np.nanmax(panel) - np.nanmin(panel)) > 0),
        "significance_level_measured": bool(np.isfinite(level) and level > 0),
    }
    failed = [k for k, v in checks.items() if not v]
    return {
        "valid": not failed,
        "checks": checks,
        "failed": failed,
        "reason": ("the semblance detector is sound on this gather"
                   if not failed else
                   "the semblance detector cannot be read here ("
                   + ", ".join(failed) + ")"),
    }


def negative_evidence_holds(direct_present, detector, strongest_real, level,
                            agreed, threshold, run_sensitivity) -> bool:
    """May an absence be reported as a FAIL rather than as INCONCLUSIVE?"""
    if direct_present or agreed or not run_sensitivity:
        return False
    if not detector["valid"]:
        return False
    if threshold is None or threshold > INFORMATIVE_THRESHOLD_X_RMS:
        return False
    return bool(strongest_real < level)


def _negative_path_blocker(direct_present, detector, strongest_real, level,
                           threshold, run_sensitivity) -> str:
    """Which of the conditions above was not met. For the refusal message."""
    if direct_present:
        return ("a direct wave IS present, so the branches were needed and "
                "their failure cannot be read as absence")
    if not run_sensitivity:
        return "the sensitivity ladder was skipped, so there is no detection limit"
    if not detector["valid"]:
        return detector["reason"]
    if threshold is None:
        return "no injected amplitude was recovered at all"
    if threshold > INFORMATIVE_THRESHOLD_X_RMS:
        return (f"detection needed {threshold:g}x the record RMS, above the "
                f"{INFORMATIVE_THRESHOLD_X_RMS:g}x at which absence means "
                f"something")
    if strongest_real >= level:
        return (f"the strongest peak, {strongest_real:.4f}, is not below the "
                f"{level:.4f} significance level, so the scan did find "
                f"something it cannot dismiss")
    return "all conditions were met"

def band_energy_fraction(raw, dt, lo, hi) -> float:
    """Share of the gather's energy (mean removed, DC excluded) inside [lo, hi]."""
    a = np.asarray(raw, dtype=np.float64)
    a = a - a.mean(axis=-1, keepdims=True)
    power = np.abs(np.fft.rfft(a, axis=-1)) ** 2
    freq = np.fft.rfftfreq(a.shape[-1], dt)
    total = float(power[..., freq > 0].sum())
    if total <= 0:
        return 0.0
    return float(power[..., (freq >= lo) & (freq <= hi) & (freq > 0)].sum() / total)


def band_limited_absence(verdict: str, fraction: float) -> tuple[str, bool]:
    """v0.16 F1."""
    if verdict == FAIL and fraction < MIN_BAND_ENERGY_FRACTION:
        return INCONCLUSIVE, True
    return verdict, False


def assess(data, offsets, dt, t0, water=DEFAULT_WATER, f_lo=30.0, f_hi=250.0,
           t0_range=(0.05, 2.0), v_range=(1350.0, 3200.0), probe=None,
           amplitudes=(0.05, 0.1, 0.2, 0.4, 0.8, 1.6), run_sensitivity=True):
    """Three-branch direct-wave suppression, one detector, one verdict."""
    clock, mark = {}, time.perf_counter()

    def lap(name):
        nonlocal mark
        now = time.perf_counter()
        clock[name] = round(clock.get(name, 0.0) + now - mark, 2)
        mark = now

    raw = np.asarray(data, dtype=np.float64)
    data = bandpass(raw, dt, f_lo, f_hi)
    offsets = np.asarray(offsets, dtype=np.float64)
    ntr = data.shape[0]
    band_fraction = band_energy_fraction(raw, dt, f_lo, f_hi)
    t0_grid = np.arange(t0_range[0], t0_range[1], 0.02)
    v_grid = np.arange(v_range[0], v_range[1], 50.0)
    rms = float(np.sqrt((data ** 2).mean()))

    # Before anything is read off the velocity axis, check there is one.
    leverage = velocity_leverage(offsets, dt, t0_grid, v_grid)
    if not leverage["resolvable"]:
        return {
            "algorithm_version": REFLECTION_VERSION,
            "traces": ntr,
            "offset_range_m": [round(float(offsets.min()), 1),
                               round(float(offsets.max()), 1)] if ntr else None,
            "velocity_leverage": leverage,
            "REFLECTION_PROCESSING_FEASIBLE": INCONCLUSIVE,
            "feasibility_reason": leverage["reason"],
            "agreed_candidates": [],
            "rejected_candidates": [],
            "detection_threshold_x_rms": C.observed(
                None, "not measured: the velocity axis carries no information "
                      "on this gather"),
            "direct_wave_stack_peak": C.observed(
                None, "not measured: see velocity_leverage"),
            "branches": {},
            "notes": [
                leverage["reason"],
                "Nothing further was computed. A semblance scan on these "
                "offsets would return a high score at every velocity, and "
                "reporting that as a reflection candidate is exactly the "
                "failure this check exists to prevent.",
            ],
        }

    direct = direct_wave_evidence(raw, offsets, dt, t0, water, f_lo, f_hi)
    # Time zero is read from the unfiltered gather: the direct wave's dominant period is the tolerance, and the
    # feasibility band would remove it.
    time_zero = TZ.measure(raw, offsets, dt, t0, water, direct["verdict"])
    present = direct["verdict"] in (ROBUST, FRAGILE)
    base = direct["trials"][0]["stack_peak"] if direct["trials"] else 0.0
    gain = agc_gain(data, dt)
    lap("prepare")
    raw_semb = velocity_semblance(data / gain, offsets, dt, t0, t0_grid, v_grid)
    raw_peaks = peaks(raw_semb, t0_grid, v_grid)
    lap("scan")

    step = float(np.median(np.abs(np.diff(np.sort(offsets))))) or 1.0
    alias_hz = water / (2.0 * step)

    branches = _branches(data, offsets, dt, t0, water)
    lap("suppress")
    outside = ~corridor_mask(data.shape, offsets, dt, t0, water)
    outside_energy = float((data[outside] ** 2).sum()) or 1.0
    report = {}
    for name, panel in branches.items():
        left = direct_stack_peak(panel, offsets, dt, t0, water) / (base or 1.0)
        report[name] = {
            "direct_wave_left_fraction": round(left, 3),
            "record_rms_kept_fraction": round(
                float(np.sqrt((panel ** 2).mean()) / (rms or 1.0)), 3),
            "outside_corridor_kept_fraction": round(
                float(np.sqrt((panel[outside] ** 2).sum() / outside_energy)), 3),
            "suppression_meaningful": bool(present),
            "peaks": _scan(panel, offsets, dt, t0, t0_grid, v_grid, gain),
        }
        lap("scan")
        if name == "slant_domain":
            report[name]["spatial_alias_hz"] = round(alias_hz, 1)
            aliased = f_hi > alias_hz
            report[name]["evidence_role"] = (
                "suppression only" if aliased else "suppression and slowness")
            if aliased:
                report[name].setdefault("warning", "")
                report[name]["warning"] += (
                    f"At {step:.1f} m trace spacing the direct wave is spatially "
                    f"aliased above {alias_hz:.0f} Hz, and the band runs to "
                    f"{f_hi:.0f} Hz. It still suppresses well up there, but "
                    f"suppressing an event is not the same as resolving its "
                    f"slowness: above the alias frequency this branch is an "
                    f"empirical operator, not a measurement. Any apparent "
                    f"velocity or geometry claim must come from the unaliased "
                    f"band or from a source-distance trend instead. ")
        if present and left > 1.0:
            report[name]["warning"] = report[name].get("warning", "") + (
                "This branch left more coherent energy on the direct-wave moveout "
                "than it started with; its output is an artefact here and any "
                "candidate it alone reports should be discarded.")

    level, null_highs = _significance_level(data, offsets, dt, t0,
                                            t0_grid, v_grid, gain)
    lap("null")
    min_sep = 2.0 / f_lo          # about one period of the lowest kept frequency

    voters, disqualified, branch_status = [], {}, {}
    for name, branch in report.items():
        kept = branch["outside_corridor_kept_fraction"]
        left = branch["direct_wave_left_fraction"]
        if present and left > 1.0:
            status = BRANCH_BROKEN
            why = (f"left {left:.2f}x the coherent energy it was asked to "
                   f"remove from the direct wave's moveout, so it is adding "
                   f"structure")
        elif not present and kept < MIN_OUTSIDE_KEPT_NO_DIRECT:
            # Not a malfunction.
            status = BRANCH_NOT_APPLICABLE
            why = (f"there is no direct wave here for it to suppress, so its "
                   f"premise does not hold; it rewrote {1 - kept:.0%} of the "
                   f"record anyway, which is what a dip filter does when it "
                   f"has nothing to aim at")
        else:
            status = BRANCH_VALID
            why = "evaluated normally"
            voters.append(name)
        branch_status[name] = status
        branch["status"] = status
        branch["status_reason"] = why
        if status != BRANCH_VALID:
            disqualified[name] = why

    agreed, rejected = [], []
    if len(voters) >= MIN_VOTERS:
        agreed, rejected = _agreement(report, voters, level, offsets, water,
                                      min_sep, present,
                                      v_step=float(v_grid[1] - v_grid[0]))

    if probe is None:
        probe = _pick_probe(raw_semb, t0_grid, v_grid, water)
    baseline = _cell(raw_semb, t0_grid, v_grid, *probe)

    threshold, ladder = None, []
    if run_sensitivity:
        for amp in amplitudes:
            spiked = inject_reflection(data, offsets, dt, t0, probe[0], probe[1], amp)
            spiked_gain = agc_gain(spiked, dt)
            got = {}
            for name, panel in _branches(spiked, offsets, dt, t0, water).items():
                semb = velocity_semblance(panel / spiked_gain, offsets, dt, t0,
                                          t0_grid, v_grid)
                got[name] = _detected(semb, t0_grid, v_grid, probe[0], probe[1],
                                      baseline, 1.0 / ntr)
            # Only the branches with standing are polled.
            polled = voters or list(got)
            ladder.append({"amplitude_x_rms": amp,
                           "polled": list(polled),
                           "detected_by": [k for k, v in got.items() if v[0]],
                           "detected_by_polled": [k for k in polled if got[k][0]],
                           "semblance": {k: round(v[1], 4) for k, v in got.items()}})
            if all(got[name][0] for name in polled):
                threshold = amp
                break
    lap("sensitivity")

    strongest_real = max([p["semblance"] for p in raw_peaks] or [0.0])
    noise_floor = 1.0 / ntr
    detector = _detector_validity(raw_semb, level, leverage)
    broken = [n for n, s in branch_status.items() if s == BRANCH_BROKEN]
    not_applicable = [n for n, s in branch_status.items()
                      if s == BRANCH_NOT_APPLICABLE]

    # Three verdicts.
    sensitive = (threshold is not None
                 and threshold <= INFORMATIVE_THRESHOLD_X_RMS)
    if agreed:
        verdict = PASS
        # semblance is one score per voting branch; the weakest is what the candidate actually cleared the level
        # on.
        strongest = max(min(c["semblance"]) for c in agreed)
        feasibility_reason = (
            f"{len(agreed)} candidate(s) survived all three suppression "
            f"branches; the strongest clears its weakest branch at "
            f"{strongest:.3f}.")
    elif negative_evidence_holds(present, detector, strongest_real, level,
                                 agreed, threshold, run_sensitivity):
        # The suppression vote is the wrong instrument here and says so: there is no direct wave, so the branches
        # that stood down are NOT_APPLICABLE rather than broken.
        verdict = FAIL
        feasibility_reason = (
            f"No reflection here. The direct wave is absent, so the "
            f"suppression branches have nothing to act on; the detector itself "
            f"is sound and its strongest peak, {strongest_real:.4f}, is below "
            f"the {level:.4f} that moveout-destroyed noise reaches on this "
            f"gather, while an injected reflection WOULD have been recovered "
            f"at {threshold:g}x the record RMS -- at or below the "
            f"{INFORMATIVE_THRESHOLD_X_RMS:g}x where a negative result is "
            f"informative.")
    elif len(voters) < MIN_VOTERS:
        verdict = INCONCLUSIVE
        why_short = ("all of them because there was no direct wave to suppress"
                     if not_applicable and not broken else
                     f"{len(broken)} of them because they malfunctioned")
        feasibility_reason = (
            f"Only {len(voters)} branch(es) left the record standing well "
            f"enough to have an opinion; {MIN_VOTERS} are required ("
            f"{why_short}). "
            + ("The detector itself is not sound here either, so nothing was "
               "decided: " + detector["reason"]
               if not detector["valid"] else
               "The negative-evidence path was not available: "
               + _negative_path_blocker(present, detector, strongest_real,
                                        level, threshold, run_sensitivity))
            + " Nothing was decided about reflections here.")
    elif not run_sensitivity:
        verdict = INCONCLUSIVE
        feasibility_reason = (
            "No candidate agreed, and the sensitivity ladder was skipped, so "
            "there is no detection limit to read that absence against.")
    elif sensitive:
        verdict = FAIL
        feasibility_reason = (
            f"No candidate survived all three branches, and an injected "
            f"reflection WOULD have been recovered at {threshold:g}x the "
            f"record RMS -- at or below the {INFORMATIVE_THRESHOLD_X_RMS:g}x "
            f"where a negative result is informative. Not detectable here.")
    else:
        verdict = INCONCLUSIVE
        feasibility_reason = (
            "No candidate agreed, but this gather could not have shown one: "
            + (f"detection needed {threshold:g}x the record RMS, above the "
               f"{INFORMATIVE_THRESHOLD_X_RMS:g}x at which absence means "
               "something."
               if threshold is not None else
               "no injected amplitude was recovered at all.")
            + " This is about the survey's sensitivity, not the subsurface.")

    # v0.16 F1: the verdict above is about the analysis band.
    in_band_verdict, in_band_reason = verdict, feasibility_reason
    verdict, band_demoted = band_limited_absence(verdict, band_fraction)
    if band_demoted:
        feasibility_reason = (
            f"Not decided for this record: the {f_lo:g}-{f_hi:g} Hz analysis "
            f"band holds only {100 * band_fraction:.2g}% of the gather's energy, "
            f"so an absence found there says little about the rest. In that band "
            f"alone the finding was: " + in_band_reason)

    notes = []
    if direct["verdict"] != ROBUST:
        notes.append(direct["note"])
    if broken:
        notes.append(
            "Branch(es) BROKEN on this gather: "
            + "; ".join(f"{k} ({branch_status and report[k]['status_reason']})"
                        for k in broken)
            + ". A branch that is broken must not be able to veto a real event.")
    if not_applicable:
        notes.append(
            "Branch(es) NOT_APPLICABLE: "
            + "; ".join(f"{k} ({report[k]['status_reason']})"
                        for k in not_applicable)
            + ". Their premise failed rather than their method, so their "
              "silence is not evidence either way -- and, when the detector "
              "itself is sound, it does not stand in the way of reporting an "
              "absence.")
    if len(voters) < MIN_VOTERS:
        notes.append(
            f"Only {len(voters)} branch(es) qualified, below the {MIN_VOTERS} "
            f"needed for an agreement to mean anything."
            + (" The verdict here does not rest on that agreement: with no "
               "direct wave present and the detector sound, the absence was "
               "read from the detector itself."
               if verdict == FAIL else
               " Nothing can be concluded from this gather with these "
               "settings."))
    if direct["verdict"] == ABSENT:
        notes.append(
            "With no direct wave to suppress, the three-way comparison is no "
            "longer guarding against suppression artefacts -- it is only "
            "checking that a candidate survives three different filters. Read "
            "the agreement accordingly.")
    if verdict == PASS:
        notes.append(
            f"{len(agreed)} candidate(s) found by all {len(voters)} qualified "
            f"branch(es) ({', '.join(voters)}), each above the {level:.4f} level "
            f"that moveout-destroyed noise reaches here and separable from the "
            f"direct wave. Candidates, not picks.")
    elif verdict == FAIL:
        notes.append(
            f"Nothing survives all {len(voters)} qualified branches, and this "
            f"gather would have "
            f"shown an injected reflection at {threshold:g}x the record RMS. The "
            f"absence is informative down to that level. What it does not rule "
            f"out is a reflection weaker than that, which at {offsets.min():.0f}-"
            f"{offsets.max():.0f} m offsets is exactly what a sub-seafloor return "
            f"would be.")
    elif band_demoted:
        notes.append(
            f"The branches found nothing in {f_lo:g}-{f_hi:g} Hz, and in that band "
            f"an injected reflection at {threshold:g}x the band RMS would have been "
            f"recovered. That band carries {100 * band_fraction:.2g}% of the "
            f"gather's energy; a reflection outside it was never tested. A "
            f"lower band is not a remedy by itself: where the record's energy "
            f"sits the direct wave may not be separable, and the three branches "
            f"then have nothing they can suppress.")
    elif threshold is None and run_sensitivity:
        notes.append(
            f"An injected reflection at t0={probe[0]:.2f} s, v={probe[1]:.0f} m/s "
            f"was not recovered by every qualified branch even at "
            f"{amplitudes[-1]:g}x "
            f"the record RMS. Nothing can be concluded about reflections here "
            f"until the gather, the geometry or the method changes -- this is not "
            f"evidence of absence.")
    elif not run_sensitivity:
        notes.append(
            "The sensitivity ladder was skipped, so there is no detection limit "
            "to read the result against. Re-run with run_sensitivity=true before "
            "treating the absence of candidates as a finding.")
    else:
        notes.append(
            f"The three branches agree only on an injected reflection at "
            f"{threshold:g}x the record RMS, above the {INFORMATIVE_THRESHOLD_X_RMS:g}x "
            f"at which a negative result starts to mean something. The strongest "
            f"event actually present scores {strongest_real:.4f} against a "
            f"{noise_floor:.4f} noise floor. This is a statement about the survey's "
            f"sensitivity, not about the subsurface.")
    if rejected:
        notes.append(
            f"{len(rejected)} candidate(s) were seen by every qualified branch and "
            f"rejected; read rejected_candidates for the reason before concluding "
            f"anything from the absence of agreed ones.")
    if present and report["template_subtraction"]["direct_wave_left_fraction"] > 0.4:
        notes.append(
            f"Template subtraction leaves "
            f"{report['template_subtraction']['direct_wave_left_fraction']:.0%} of the "
            f"direct wave. Only the part that repeats shot to shot can be subtracted, "
            f"so the shot-to-shot repeatability of this survey is poor -- which also "
            f"means candidates missed here are not evidence of absence.")

    return {
        "algorithm_version": REFLECTION_VERSION,
        "traces": ntr,
        "offset_range_m": [round(float(offsets.min()), 1), round(float(offsets.max()), 1)],
        "water_velocity_m_s": C.assumed(water, "caller or default"),
        "direct_wave": C.derived(
            direct["verdict"],
            "flattened stack peak against two decoy velocities, repeated under "
            "six predeclared perturbations of trace count and bandwidth",
            detected_in=direct["detected_in"], trials=direct["trials"]),
        "direct_wave_stack_peak": C.observed(round(base, 4),
                                             "flattened trace-normalised stack"),
        "noise_floor_semblance": C.derived(round(noise_floor, 4),
                                           "1/ntraces for uncorrelated noise"),
        "raw_peaks": raw_peaks,
        "branches": report,
        "agreed_candidates": agreed,
        "rejected_candidates": rejected,
        "voting_branches": C.derived(
            voters, "branches that left the record standing well enough to have "
                    "an opinion", disqualified=disqualified,
            rule=(f"with a direct wave present, a branch votes unless it added "
                  f"coherent energy to that wave's moveout; without one, unless "
                  f"it rewrote more than {1 - MIN_OUTSIDE_KEPT_NO_DIRECT:.0%} of "
                  f"the record it had no reason to touch. At least {MIN_VOTERS} "
                  f"must qualify")),
        "branch_status": branch_status,
        "branches_broken": broken,
        "branches_not_applicable": not_applicable,
        "raw_detector": detector,
        "significance_level": C.derived(
            round(level, 4),
            "90th percentile of the grid maximum over 8 moveout-destroyed "
            "realisations of this gather",
            trial_maxima=[round(h, 4) for h in null_highs]),
        "probe": {"t0_s": round(probe[0], 3), "v_m_s": round(probe[1], 1),
                  "baseline_semblance": round(baseline, 4)},
        "detection_limit_polled_branches": list(voters),
        "detection_threshold_x_rms": (
            C.derived(threshold, "synthetic reflection injected into the real "
                                 "gather, recovered by every branch with "
                                 "standing (" + ", ".join(voters) + ")")
            if threshold is not None
            else C.observed(None, "no injected amplitude was recovered by every "
                                  "branch with standing")),
        "sensitivity_ladder": ladder,
        "seconds": clock,
        "velocity_leverage": leverage,
        "time_zero": time_zero,
        "analysis_band": {
            "band_hz": [f_lo, f_hi],
            "energy_fraction": round(band_fraction, 6),
            "min_fraction_for_absence": MIN_BAND_ENERGY_FRACTION,
            "in_band_verdict": in_band_verdict,
            "demoted": band_demoted},
        "REFLECTION_PROCESSING_FEASIBLE": verdict,
        # One line stating the outcome, so a manifest reader quoting the evidence quotes the finding rather than
        # whichever caveat happened to be first in the notes.
        "feasibility_reason": feasibility_reason,
        "notes": notes,
    }
