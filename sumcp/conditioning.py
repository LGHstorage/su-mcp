"""Pre-stack conditioning from a fixed menu, behind a signal-preservation gate."""
from __future__ import annotations

import numpy as np

from . import sufile

__all__ = ["REGISTRY", "menu", "resolve", "inject_events", "inject_sets", "preservation",
           "PRESERVATION_MIN", "MAX_OPERATIONS", "MAX_PASSES", "SOLO_OPERATIONS",
           "reliability", "RELIABILITY_MIN"]

PRESERVATION_MIN = 0.9
MAX_OPERATIONS = 3
MAX_PASSES = 3   # v0.26: DMO adds one conditioning pass
QC_GATHERS = 5
INJECT_FRACTIONS = (0.25, 0.5, 0.75)
INJECT_VELOCITY_FACTORS = (1.1, 1.3, 1.5)
INJECT_AMPLITUDE_X_RMS = 0.5   # CRITERIA v0.19: 0.5 x the gather RMS
MIN_QC_WINDOW_S = 0.3
RELIABILITY_MIN = 0.9          # v0.20 RS: Spearman-Brown split-half reliability


def _num(params, key, lo, hi, default=None):
    value = params.get(key, default)
    if value is None:
        raise ValueError(f"parameter {key!r} is required")
    value = float(value)
    if not lo <= value <= hi:
        raise ValueError(f"{key}={value:g} outside {lo:g}-{hi:g}")
    return value


def _bandpass(params, ctx):
    f = params.get("f")
    if not isinstance(f, (list, tuple)) or len(f) != 4:
        raise ValueError("bandpass needs f=[f1,f2,f3,f4] in Hz")
    f = [float(v) for v in f]
    nyq = 0.5 / ctx["dt_s"]
    if not (0 <= f[0] < f[1] < f[2] < f[3] <= nyq):
        raise ValueError(f"bandpass corners must rise within 0-{nyq:g} Hz")
    return [("sufilter", {"f": [round(v, 3) for v in f]}, False)]


def _agc(params, ctx):
    w = _num(params, "window_s", 0.05, 2.0, 0.5)
    return [("sugain", {"agc": 1, "wagc": round(w, 4)}, False)]


def _mute_direct(params, ctx):
    v = ctx.get("direct_velocity_m_s")
    t0 = float(ctx.get("direct_intercept_s") or 0.0)
    fa = ctx.get("first_arrivals")
    if not v and fa:
        # v0.33 L1: on land, the measured first arrivals (intercept + offset / velocity)
        v, t0 = float(fa["velocity_m_s"]), float(fa["intercept_s"])
    if not v:
        raise ValueError("mute_direct needs R1's measured direct-wave velocity or, on land, "
                         "the first arrivals measured at sort_cmp (L1); neither exists on this "
                         "dataset")
    extra = _num(params, "extra_s", 0.0, 0.5, 0.1)
    taper = _num(params, "taper_s", 0.0, 0.2, 0.05)
    x = float(ctx["max_offset_m"])
    t = t0 + x / float(v) + extra
    return [("sumute", {"key": "offset", "xmute": [round(-x, 1), 0, round(x, 1)],
                        "tmute": [round(t, 4), round(t0 + extra, 4), round(t, 4)],
                        "ntaper": int(round(taper / ctx["dt_s"]))}, False)]


def _dip_filter(params, ctx):
    v = _num(params, "reject_below_m_s", 300.0, 5000.0)
    s_pass = 1.0 / (1.25 * v)     # full pass for apparent velocity >= 1.25 v
    s_stop = 1.0 / v              # full reject for apparent velocity <= v
    return [("sudipfilt", {"dt": ctx["dt_s"], "dx": "GATHER",
                           "slopes": [-s_stop, -s_pass, s_pass, s_stop],
                           "amps": [0, 1, 1, 0]}, True)]


def _predictive_decon(params, ctx):
    lo = _num(params, "minlag_s", ctx["dt_s"], 0.5, None)
    hi = _num(params, "maxlag_s", lo + ctx["dt_s"], 1.0, None)
    pn = _num(params, "pnoise", 1e-4, 0.1, 0.001)
    return [("supef", {"minlag": round(lo, 4), "maxlag": round(hi, 4),
                       "pnoise": pn}, False)]


def _datum_shift(params, ctx):
    if params:
        raise ValueError("datum_shift takes no parameters: the shift is R1's measured lag")
    return [("datum_shift", {}, False)]


def _residual_statics(params, ctx):
    if params:
        raise ValueError("residual_statics takes no parameters: the maximum shift is "
                         "half the dominant period R1 measured")
    return [("residual_statics", {}, False)]


def _dmo(params, ctx):
    if params:
        raise ValueError("dmo takes no parameters: velocity, spacing and offset mixing come "
                         "from the validated model and the geometry")
    return [("dmo", {}, False)]


def _kill_corrupt(params, ctx):
    if params:
        raise ValueError("kill_corrupt takes no parameters: the corrupt traces are the ones "
                         "the Q0 sample check finds")
    return [("kill_corrupt", {}, False)]


REGISTRY = {
    "bandpass": {"program": "sufilter", "build": _bandpass,
                 "parameters": {"f": "four corner frequencies in Hz, rising, below Nyquist"},
                 "purpose": "remove energy outside the signal band",
                 "caution": "noise inside the signal band is untouched"},
    "agc": {"program": "sugain", "build": _agc,
            "parameters": {"window_s": "AGC window, 0.05-2.0 s (default 0.5)"},
            "purpose": "balance amplitudes before velocity analysis",
            "caution": "destroys true relative amplitude"},
    "mute_direct": {"program": "sumute", "build": _mute_direct,
                    "parameters": {"extra_s": "mute this long after the direct wave, 0-0.5 s (default 0.1)",
                                   "taper_s": "taper length, 0-0.2 s (default 0.05)"},
                    "purpose": "remove the direct-wave corridor (on land: the first-arrival corridor)",
                    "caution": "needs R1's measured direct-wave velocity, or on land the first "
                               "arrivals measured at sort_cmp (v0.33 L1); also removes "
                               "shallow reflections inside the corridor"},
    "dip_filter": {"program": "sudipfilt (per CMP gather)", "build": _dip_filter,
                   "parameters": {"reject_below_m_s": "reject apparent velocities at or "
                                  "below this, pass from 1.25x it, 300-5000 m/s"},
                   "purpose": "reject slow linear noise (direct wave, guided waves)",
                   "caution": "f-k on irregular offsets; aliased energy above "
                              "v/(2 dx) is not handled"},
    "predictive_decon": {"program": "supef", "build": _predictive_decon,
                         "parameters": {"minlag_s": "prediction gap (s)",
                                        "maxlag_s": "operator end (s), up to 1.0",
                                        "pnoise": "prewhitening, 1e-4-0.1 (default 0.001)"},
                         "purpose": "shorten the wavelet / attenuate short-period reverberation",
                         "caution": "assumes a minimum-phase wavelet"},
    # v0.20: operations whose purpose is to move events in time.
    "datum_shift": {"program": "in-process sample shift (R1 lag)", "build": _datum_shift,
                    "parameters": {},
                    "purpose": "move the time axis to the shot instant by R1's measured "
                               "direct-wave lag, when |lag| > a quarter period",
                    "caution": "a late clock and a causal wavelet give the same lag; the "
                               "shift is disclosed on every later stack",
                    "gate": "R1 re-measured on the shifted data must be within a quarter "
                            "period"},
    "residual_statics": {"program": "suresstat (Ronen-Claerbout), applied in-process",
                         "build": _residual_statics, "parameters": {},
                         "purpose": "estimate surface-consistent source and receiver "
                                    "statics from NMO-corrected gathers and remove them",
                         "caution": "needs a validated velocity; invalidates it; "
                                    "integer-sample statics only",
                         "gate": "split-half reliability (random CMP halves) of source and "
                                 "receiver statics >= 0.9, material (would cost > 10% of "
                                 "stack amplitude), and rms <= a quarter period"},
    # v0.26
    "dmo": {"program": "sunmo | susort offset cdp | sudmofk | susort cdp offset | sunmo invert=1",
            "build": _dmo, "parameters": {},
            "purpose": "dip moveout: remove the dip dependence of the NMO velocity, so the "
                       "re-picked stacking velocity approaches the migration (RMS) velocity",
            "caution": "needs a validated velocity; invalidates it (re-pick after); the NMO "
                       "stretch-muted zone does not come back",
            "gate": "laterally continuous flat reflections through the chain must correlate "
                    ">= 0.9 with the same reflections through NMO and inverse NMO alone, and "
                    "the output must keep every trace in its (cdp, offset) order"},
    # v0.30
    "kill_corrupt": {"program": "in-process (samples of corrupt traces set to zero)",
                     "build": _kill_corrupt, "parameters": {},
                     "purpose": "remove traces holding a non-finite sample or a sample beyond "
                                "120 dB of the median trace RMS (Q0), e.g. a clamped IBM-float "
                                "overflow, before they spread through filters, stack and migration",
                     "caution": "zeroes whole traces; invalidates velocity, NMO and stack",
                     "gate": "K0: corrupt traces at most 1% of the file, every other trace "
                             "byte-identical in the output, no corrupt trace left"},
}
SOLO_OPERATIONS = ("datum_shift", "residual_statics", "dmo", "kill_corrupt")


def menu() -> dict:
    return {name: {k: v for k, v in entry.items() if k != "build"}
            for name, entry in REGISTRY.items()}


def resolve(operations, ctx) -> list:
    """Validate a requested chain; returns [(name, program, params, per_gather)]."""
    if not isinstance(operations, (list, tuple)) or not operations:
        raise ValueError("operations must be a non-empty list of {op: ..., ...}")
    if len(operations) > MAX_OPERATIONS:
        raise ValueError(f"at most {MAX_OPERATIONS} operations per pass")
    solo = [o.get("op") for o in operations if isinstance(o, dict)
            and o.get("op") in SOLO_OPERATIONS]
    if solo and len(operations) > 1:
        raise ValueError(f"{solo[0]} moves events in time and has its own gate; "
                         "it must be the only operation in its pass")
    steps = []
    for item in operations:
        if not isinstance(item, dict) or item.get("op") not in REGISTRY:
            raise ValueError(f"unknown operation {item!r}; menu: {', '.join(REGISTRY)}")
        params = {k: v for k, v in item.items() if k != "op"}
        for program, args, per_gather in REGISTRY[item["op"]]["build"](params, ctx):
            steps.append((item["op"], program, args, per_gather))
    return steps


def ricker(t, f0):
    a = (np.pi * f0 * t) ** 2
    return (1 - 2 * a) * np.exp(-a)


def inject_events(data, offsets, dt, t_start, t_direct, record_end, v_direct, f_dom):
    """Three hyperbolic reflections below the last direct arrival."""
    if record_end - t_direct < MIN_QC_WINDOW_S:
        return None
    ns = data.shape[1]
    t = t_start + np.arange(ns) * dt
    x = np.abs(np.asarray(offsets, dtype=np.float64))
    amp = INJECT_AMPLITUDE_X_RMS * float(np.sqrt(np.mean(np.asarray(data, float) ** 2)) or 1.0)
    ev = np.zeros_like(np.asarray(data, dtype=np.float64))
    for frac, vf in zip(INJECT_FRACTIONS, INJECT_VELOCITY_FACTORS):
        t0 = t_direct + frac * (record_end - t_direct)
        tx = np.sqrt(t0 ** 2 + (x / (vf * v_direct)) ** 2)
        ev += amp * ricker(t[None, :] - tx[:, None], f_dom)
    return ev


def inject_sets(data, offsets, dt, t_start, t_direct, record_end, v_direct, f_dom):
    """v0.20 G2: the deep set (below the last direct arrival, as in v0.19) and a shallow set spanning record
    start to the last direct arrival, where a mute or a dip filter can remove reflections the deep set never
    sees."""
    deep = inject_events(data, offsets, dt, t_start, t_direct, record_end, v_direct, f_dom)
    shallow = inject_events(data, offsets, dt, t_start, t_start, t_direct, v_direct, f_dom)
    return {"deep": deep, "shallow": shallow}


def reliability(a, b):
    """Spearman-Brown reliability of the full estimate from two half estimates."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    r = float(np.corrcoef(a, b)[0, 1])
    return 2 * r / (1 + r) if r > -1 else 0.0


def preservation(processed_with, processed_without, injected) -> float:
    rec = np.asarray(processed_with, float) - np.asarray(processed_without, float)
    a, b = rec.ravel(), np.asarray(injected, float).ravel()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(a @ b / (na * nb))


def write_block(raw_block: np.ndarray, samples: np.ndarray, geom: dict) -> bytes:
    """Trace bytes with the samples replaced, in the file's own byte order."""
    order = geom.get("_order", "<")
    block = raw_block.copy()
    block[:, sufile.HEADER_BYTES:] = np.asarray(samples, dtype=order + "f4").view(np.uint8).reshape(
        block.shape[0], -1)
    return block.tobytes()
