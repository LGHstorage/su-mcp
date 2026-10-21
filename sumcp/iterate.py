"""Bounded iteration: pre-stack conditioning and velocity re-picking (v0.19)."""
from __future__ import annotations

import json
import shutil

import numpy as np

from . import conditioning as K
from . import acqstatics, config, evidence, governance, provenance, runner, sanity, sufile, timezero, velocity
from . import stack as S
from .paths import as_rel, safe_input_path, safe_output_path

ITERATE_VERSION = "iterate-0.5"

__all__ = ["ITERATE_VERSION", "condition_gathers", "refine_velocity",
           "conditioning_menu", "supergather_cdps", "relocation_candidates",
           "scope_from_grade", "shift_samples", "apply_trace_statics",
           "cmp_halves", "statics_material",
           "gather_runs", "MAX_REFINE_ATTEMPTS"]

MAX_REFINE_ATTEMPTS = 3
SUPERGATHER_HALF = 2
WIDE_SUPERGATHER_HALF = 4
RELOCATE_MAX_CANDIDATES = 3
RELOCATE_FRACTIONS = (0.125, 0.25)       # v0.20 R3
RELOCATE_SNAP_BINS = 2
SCOPE_MIN_FRACTION = 0.5                 # v0.20 S1
# v0.20 multiple testing: a failed location can be tested up to 5 times (supergather, 3 relocations, wide
# supergather).
REFINE_TESTS_PER_LOCATION = 5
REFINE_PATH_ALPHA = 0.05 / REFINE_TESTS_PER_LOCATION
REFINE_NULL_TRIALS = 99
# v0.21 RS2
RS_SPLIT_SEED = 0
RS_MIN_COMPARED = 10
RS_MATERIAL_FRACTION = float(np.sqrt(2 * np.log(1 / 0.9)) / (2 * np.pi))   # 0.0731
MIN_TRACES_PER_GATHER_FK = 4     # below this a per-gather f-k step passes the gather through

_DOWNSTREAM = ("velocity.model_available", "velocity.validated",
               "nmo.applied", "stack.completed")


def _set(manifest, name, ok, ev, run_id, notes=(), artifact=None):
    status = {True: evidence.PASS, False: evidence.FAIL, None: evidence.UNKNOWN}[ok]
    return evidence.set_capability(manifest, name, status, ev, ITERATE_VERSION,
                                   run_id, artifact=artifact, notes=list(notes))


def _budgets(manifest):
    return manifest.setdefault("budgets", {})


def _time_zero(manifest):
    cap = evidence.get_capability(manifest, "acquisition.time_zero_consistent") or {}
    return cap, (cap.get("evidence") or {})


# --------------------------------------------------------------------------- Gather bookkeeping (pure functions,
# unit-tested),-------------------------------------------------------------------------

def gather_runs(cdp):
    """[(cdp, start, stop)] for a file that holds each CMP as one contiguous run."""
    cdp = np.asarray(cdp)
    if cdp.size == 0:
        return []
    edges = np.flatnonzero(np.diff(cdp) != 0) + 1
    starts = np.concatenate([[0], edges])
    stops = np.concatenate([edges, [cdp.size]])
    values = cdp[starts]
    if np.unique(values).size != values.size:
        raise ValueError("the CMP file is not contiguous by cdp; run sort_cmp first")
    return [(int(v), int(a), int(b)) for v, a, b in zip(values, starts, stops)]


def supergather_cdps(all_cdp, centre, half):
    """The centre CMP and `half` bins either side of it that exist on the line."""
    all_cdp = np.sort(np.asarray(all_cdp))
    pos = int(np.searchsorted(all_cdp, centre))
    if pos >= all_cdp.size or all_cdp[pos] != centre:
        raise ValueError(f"cdp {centre} is not on the line")
    lo, hi = max(0, pos - half), min(all_cdp.size, pos + half + 1)
    return [int(c) for c in all_cdp[lo:hi]]


def relocation_candidates(centre, eligible, analysed, spacing,
                          fractions=RELOCATE_FRACTIONS, limit=RELOCATE_MAX_CANDIDATES,
                          snap=RELOCATE_SNAP_BINS):
    """v0.20 R3: candidates at +-s/8 and +-s/4 of the analysis spacing s, so that a relocated supergather reads
    different traces from the one that failed (v0.19 moved one or two CMPs and re-read the same data)."""
    eligible = np.asarray(sorted(int(c) for c in eligible))
    taken = {int(c) for c in analysed}
    inward = np.sign(float(np.median(list(taken))) - centre) or 1.0
    targets = []
    for frac in fractions:
        d = int(round(frac * float(spacing)))
        if d <= 0:
            continue
        for sign in (inward, -inward):
            targets.append((d, 0 if sign == inward else 1, int(centre + sign * d)))
    out = []
    for d, rank, target in sorted(targets):
        if eligible.size == 0:
            break
        near = eligible[np.abs(eligible - target) <= snap]
        near = [int(c) for c in near if int(c) not in taken and int(c) != centre
                and int(c) not in out]
        if near:
            out.append(min(near, key=lambda c: (abs(c - target), c)))
        if len(out) == limit:
            break
    return out


def scope_from_grade(grade, reports, min_fraction=None):
    """v0.20 S1: the measured span, when the only thing wrong is coverage."""
    min_fraction = SCOPE_MIN_FRACTION if min_fraction is None else min_fraction
    valid = [int(r["cdp"]) for r in reports if r["valid"]]
    if grade["ok"] or len(valid) < grade["required_valid"]:
        return None
    if grade["coverage_fraction"] < min_fraction:
        return None
    return [min(valid), max(valid)]


# ---------------------------------------------------------------------------
# condition_gathers,-------------------------------------------------------------------------

def conditioning_menu() -> dict:
    return {"operations": K.menu(), "max_operations_per_pass": K.MAX_OPERATIONS,
            "max_passes_per_dataset": K.MAX_PASSES,
            "qc_gate": {"preservation_min": K.PRESERVATION_MIN,
                        "qc_gathers": K.QC_GATHERS,
                        "injected_t0_fractions": list(K.INJECT_FRACTIONS),
                        "injected_velocity_factors": list(K.INJECT_VELOCITY_FACTORS),
                        "injected_amplitude_x_gather_rms": K.INJECT_AMPLITUDE_X_RMS},
            "note": ("A pass is accepted only when three injected reflections "
                     "survive the chain (median correlation >= 0.9). Accepted "
                     "gathers replace cmp_sorted and invalidate velocity, NMO "
                     "and stack; rejected gathers are kept for audit only.")}


def _run_file(program, args, src, dst):
    return runner.run_trusted(program, runner.validate_params(args),
                              stdout_path=dst, stdin_path=src)


def _gather_dx(offsets):
    off = np.sort(np.asarray(offsets, dtype=np.float64))
    steps = np.diff(off)
    steps = steps[steps > 0]
    return float(np.median(steps)) if steps.size else None


def _per_gather(program, args, src, dst, tmp):
    """Run one step gather by gather (f-k needs one gather at a time)."""
    geom = sufile.geometry(src)
    cols = sufile.read_header_columns(src, ["cdp", "offset"], geom)
    runs = gather_runs(cols["cdp"])
    off = np.asarray(cols["offset"], dtype=np.float64)
    stride = geom["trace_bytes"]
    passed_through, dxs = 0, []
    gin, gout = tmp / "g_in.su", tmp / "g_out.su"
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        for _, a, b in runs:
            fin.seek(a * stride)
            block = fin.read((b - a) * stride)
            dx = _gather_dx(off[a:b])
            if b - a < MIN_TRACES_PER_GATHER_FK or not dx:
                fout.write(block)
                passed_through += 1
                continue
            gin.write_bytes(block)
            _run_file(program, {k: (round(dx, 3) if v == "GATHER" else v)
                                for k, v in args.items()}, gin, gout)
            out = gout.read_bytes()
            if len(out) != len(block):
                raise runner.SURunError(
                    f"{program} changed the trace count of a gather "
                    f"({len(block) // stride} -> {len(out) // stride})")
            fout.write(out)
            dxs.append(dx)
    return {"gathers": len(runs), "passed_through_small_gathers": passed_through,
            "dx_m_range": ([round(min(dxs), 2), round(max(dxs), 2)] if dxs else None)}


def _apply_chain(steps, src, dst, tmp):
    """Apply resolved steps in order; returns a per-step record."""
    record, current = [], src
    for i, (name, program, args, per_gather) in enumerate(steps):
        out = dst if i == len(steps) - 1 else tmp / f"step{i}.su"
        if per_gather:
            info = _per_gather(program, args, current, out, tmp)
        else:
            res = _run_file(program, args, current, out)
            info = {"elapsed_s": res.get("elapsed_s")}
        record.append({"operation": name, "program": program,
                       "args": {k: v for k, v in args.items()}, **info})
        current = out
    return record


G1_SMOOTH_HZ = 5.0
G1_FLOOR = 0.1
G1_NOISE_FROM = 0.8     # fraction of Nyquist above which the spectrum is taken as noise floor


def gate_hz(samples, dt):
    """v0.33 G1: the Ricker-equivalent peak frequency of the traces."""
    x = np.asarray(samples, dtype=np.float64)
    spec = np.abs(np.fft.rfft(x, axis=1)).mean(axis=0)
    f = np.fft.rfftfreq(x.shape[1], dt)
    spec[f < 1.0] = 0.0
    k = max(1, int(round(G1_SMOOTH_HZ / (f[1] - f[0]))))
    sm = np.convolve(spec, np.ones(k) / k, "same")
    noise = float(np.median(sm[f >= G1_NOISE_FROM * f[-1]]))
    sig = np.clip(sm - noise, 0.0, None)
    if not np.isfinite(sig).all() or sig.max() <= 0:
        raise ValueError("G1: the traces have no spectrum above their noise floor")
    keep = sig >= G1_FLOOR * sig.max()
    centroid = float((f[keep] * sig[keep]).sum() / sig[keep].sum())
    return float(np.sqrt(np.pi) / 2.0 * centroid)


_dominant_hz = gate_hz      # every gate fallback goes through G1 (v0.33)


def gate_window(ctx):
    """(t_start_of_reflections, moveout velocity, class, rule) for the injection gates: v0.33 L1 on land, the
    last direct arrival (as before) otherwise."""
    fa = ctx.get("first_arrivals")
    if fa:
        return (float(fa["t_a_s"]), float(fa["velocity_m_s"]), "MEASURED",
                "v0.33 L1: land, measured first arrivals")
    v_d = ctx["direct_velocity_m_s"]
    v_inj = float(v_d or S.ASSUMED_WATER_M_S)
    return (ctx["max_offset_m"] / v_inj, v_inj, "MEASURED" if v_d else "ASSUMED",
            "last direct arrival")


def _header_statics_present(src, geom):
    cols = sufile.read_header_columns(src, ["sstat", "gstat"], geom)
    return bool(np.any(cols["sstat"]) or np.any(cols["gstat"]))


def shift_samples(samples, k):
    """Move every trace k samples earlier (k > 0) or later (k < 0), zero-filled."""
    samples = np.asarray(samples)
    out = np.zeros_like(samples)
    ns = samples.shape[-1]
    if k == 0:
        return samples.copy()
    if abs(k) >= ns:
        return out
    if k > 0:
        out[..., :ns - k] = samples[..., k:]
    else:
        out[..., -k:] = samples[..., :ns + k]
    return out


def apply_trace_statics(samples, k_per_trace):
    """shift_samples with one integer shift per trace (corrected(t) = raw(t + k dt))."""
    samples = np.asarray(samples)
    out = np.empty_like(samples)
    for i, k in enumerate(np.asarray(k_per_trace, dtype=int)):
        out[i] = shift_samples(samples[i], int(k))
    return out


def _rewrite_samples(src, dst, geom, fn, chunk=512):
    """Stream an SU file, replacing each chunk's samples by fn(samples, start)."""
    stride, ns = geom["trace_bytes"], geom["ns"]
    order = geom.get("_order", "<")
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        start = 0
        while True:
            buf = fin.read(chunk * stride)
            if not buf:
                break
            raw = np.frombuffer(buf, dtype=np.uint8).reshape(-1, stride)
            data = raw[:, sufile.HEADER_BYTES:].copy().view(order + "f4").reshape(
                raw.shape[0], ns)
            fout.write(K.write_block(raw, fn(data, start), geom))
            start += raw.shape[0]


def _gather_key(gather):
    """The feasibility gather spec as (header key, value)."""
    gather = gather or {}
    for key, header in (("fldr", "fldr"), ("cdp", "cdp"), ("channel", "tracf")):
        if gather.get(key) is not None:
            return header, int(gather[key])
    raise ValueError(f"cannot locate R1's gather {gather!r} in the CMP file")


def _injection_pass(steps, src, dst, tmp, geom, runs, offsets, ctx, tz):
    """v0.19 gate with the v0.20 G2 shallow set."""
    chain = _apply_chain(steps, src, dst, tmp)
    all_cdp = np.array([r[0] for r in runs])
    fold = np.array([r[2] - r[1] for r in runs])
    qc_cdps, _ = S.choose_analysis_locations(all_cdp, fold, K.QC_GATHERS)
    t_direct, v_inj, v_class, w_rule = gate_window(ctx)
    t_start = geom["t_start_s"]
    record_end = t_start + geom["ns"] * geom["dt_s"]
    stride = geom["trace_bytes"]
    by_cdp = {r[0]: r for r in runs}
    blocks = []
    with open(src, "rb") as fh:
        for c in qc_cdps:
            _, a, b = by_cdp[c]
            fh.seek(a * stride)
            blocks.append((c, np.frombuffer(fh.read((b - a) * stride),
                                            dtype=np.uint8).reshape(b - a, stride)))
    f_dom = tz.get("dominant_hz")
    f_class = "R1" if f_dom else "G1_RICKER_EQUIVALENT_FROM_QC_GATHERS"
    if not f_dom:
        f_dom = _dominant_hz(np.concatenate([
            sufile.read_traces(src, np.arange(by_cdp[c][1], by_cdp[c][2]), geom)
            for c, _ in blocks]).astype(np.float64), geom["dt_s"])
    order = geom.get("_order", "<")
    per_gather = []

    def run(name, raw, samples):
        (tmp / f"qc_{name}.su").write_bytes(K.write_block(raw, samples, geom))
        _apply_chain(steps, tmp / f"qc_{name}.su", tmp / f"qc_{name}_out.su", tmp)
        g = sufile.geometry(tmp / f"qc_{name}_out.su")
        return sufile.read_traces(tmp / f"qc_{name}_out.su", np.arange(g["ntr"]),
                                  g).astype(np.float64)

    for c, raw in blocks:
        data = raw[:, sufile.HEADER_BYTES:].copy().view(order + "f4").reshape(
            raw.shape[0], geom["ns"]).astype(np.float64)
        sets = K.inject_sets(data, offsets[by_cdp[c][1]:by_cdp[c][2]], geom["dt_s"],
                             t_start, t_direct, record_end, v_inj, f_dom)
        p0 = run("plain", raw, data)
        row = {"cdp": c, "traces": int(raw.shape[0])}
        for name, inj in sets.items():
            if inj is not None:
                row[name] = round(K.preservation(run(name, raw, data + inj), p0, inj), 4)
        per_gather.append(row)

    medians = {}
    for name in ("deep", "shallow"):
        vals = [g[name] for g in per_gather if name in g]
        medians[name] = round(float(np.median(vals)), 4) if vals else None
    note = None
    if medians["deep"] is None:
        note = (f"the window below the last direct arrival ({t_direct:.2f}-"
                f"{record_end:.2f} s) is shorter than {K.MIN_QC_WINDOW_S} s; "
                "nothing can be injected")
    used = [m for m in medians.values() if m is not None]
    worst = min(used) if used and medians["deep"] is not None else None
    if worst is not None and not np.isfinite(worst):
        note = ("N0: the preservation measurement is not finite (non-finite samples in the "
                "chain); a non-finite number is never a pass")
    accepted = worst is not None and worst >= K.PRESERVATION_MIN
    qc = {"preservation_median": worst, "preservation_by_window": medians,
          "preservation_min": K.PRESERVATION_MIN, "per_gather": per_gather,
          "injected_velocity_m_s": round(v_inj, 1), "velocity_class": v_class,
          "dominant_hz": round(float(f_dom), 2), "dominant_hz_source": f_class,
          "last_direct_arrival_s": round(t_direct, 3), "record_end_s": round(record_end, 3),
          **({"window_rule": w_rule} if ctx.get("first_arrivals") else {}),
          "gate": "injection (deep and shallow sets, v0.20 G2)",
          "verdict": "PASS" if accepted else ("UNKNOWN" if worst is None else "FAIL")}
    if note:
        qc["reason"] = note
    elif not accepted:
        low = [k for k, m in medians.items() if m is not None and m < K.PRESERVATION_MIN]
        qc["reason"] = (f"injected reflections kept only {worst:.2f} correlation in the "
                        f"{'/'.join(low)} window (< {K.PRESERVATION_MIN}); the product is "
                        "kept for audit and not used")
    return accepted, qc, chain, {}


def _datum_check(tz_cap, tz):
    lag, period = tz.get("intercept_s"), tz.get("tolerance_s")
    if tz_cap.get("status") not in (evidence.PASS, evidence.FAIL) or lag is None or not period:
        raise ValueError("datum_shift needs R1's measured direct-wave lag; "
                         "acquisition.time_zero_consistent has none "
                         f"({tz.get('reason') or tz_cap.get('status', 'not recorded')}).")
    if abs(lag) <= period / 4 and not governance.off():
        raise ValueError(f"R1's lag {1000 * lag:+.0f} ms is within a quarter period "
                         f"({250 * period:.0f} ms); there is nothing to correct.")
    return float(lag), float(period)


def _datum_pass(src, dst, geom, tz):
    lag, period = float(tz["intercept_s"]), float(tz["tolerance_s"])
    dt = geom["dt_s"]
    k = int(round(lag / dt))
    _rewrite_samples(src, dst, geom, lambda d, _s: shift_samples(d, k))
    key, value = _gather_key(tz.get("gather"))
    g2 = sufile.geometry(dst)
    cols = sufile.read_header_columns(dst, [key, "offset"], g2)
    idx = np.flatnonzero(np.asarray(cols[key]) == value)
    raw = sufile.read_traces(dst, idx, g2).astype(np.float64)
    again = timezero.measure(raw, np.asarray(cols["offset"], float)[idx], dt,
                             g2["t_start_s"], float(tz["direct_velocity_m_s"]), "ROBUST")
    new_lag, new_period = again.get("intercept_s"), again.get("tolerance_s")
    accepted = (new_lag is not None and bool(new_period)
                and abs(new_lag) <= new_period / 4)
    applied = round(-k * dt, 6)
    qc = {"gate": "R1 re-measured on the shifted data (v0.20 T1)",
          "lag_before_s": lag, "period_before_s": period,
          "shift_applied_s": applied, "shift_samples": -k,
          "remeasured": again, "quarter_period_s": (round(new_period / 4, 4)
                                                     if new_period else None),
          "verdict": "PASS" if accepted else "FAIL"}
    if not accepted:
        qc["reason"] = (f"after the shift R1 reads {again.get('intercept_s')} s "
                        f"({again.get('reason', '')}); the correction did not anchor "
                        "the time axis")
    new_tz = {**{k2: v for k2, v in tz.items() if k2 not in again},
              **again, "gather": tz.get("gather"),
              "datum_shift_applied_s": applied,
              "before_datum_shift": {"intercept_s": lag, "tolerance_s": period}}
    chain = [{"operation": "datum_shift", "program": K.REGISTRY["datum_shift"]["program"],
              "shift_samples": -k, "shift_s": applied}]
    return accepted, qc, chain, {"time_zero": new_tz}


def cmp_halves(cmp_rank):
    """v0.21 RS2: a fixed random half of the CMPs (True) and the rest (False), per trace."""
    cmp_rank = np.asarray(cmp_rank)
    half_of_cmp = np.random.default_rng(RS_SPLIT_SEED).random(int(cmp_rank.max())) < 0.5
    return half_of_cmp[cmp_rank - 1]


def statics_material(rms_s, period_s):
    """Expected stack amplitude factor of residual statics with this rms, and whether it is below the 0.9 'good'
    fraction (statics worth removing)."""
    factor = float(np.exp(-0.5 * (2 * np.pi * rms_s / period_s) ** 2))
    return factor, factor < K.PRESERVATION_MIN


def _statics_check(manifest):
    vcap = evidence.get_capability(manifest, "velocity.validated") or {}
    if vcap.get("status") != evidence.PASS and not governance.off():
        raise ValueError("residual_statics needs a validated velocity (NMO-corrected "
                         f"gathers); velocity.validated is {vcap.get('status', 'UNKNOWN')}.")
    return safe_input_path(evidence.get_artifact(manifest, "velocity_model")["path"])


def _ranks(values):
    _, inv = np.unique(values, return_inverse=True, axis=0)
    return inv.reshape(-1) + 1


def _suresstat(path, ranks, keep, ntpick, tmp, tag):
    """Run suresstat on the traces in `keep`; returns (source, receiver) statics in ms, indexed by rank (index 0
    unused), and the per-rank trace counts."""
    shot, station, cmp_ = ranks
    sub = tmp / f"rs_{tag}.su"
    sufile.write_header_columns(path, sub, {"fldr": shot, "tracf": station, "cdp": cmp_},
                                keep=keep)
    s_k, r_k, c_k = shot[keep], station[keep], cmp_[keep]
    nshot, nr, nc = int(shot.max()), int(station.max()), int(cmp_.max())
    counts = lambda v, n: np.bincount(v, minlength=n + 1)
    params = {"ntraces": int(keep.sum()), "ntpick": int(ntpick), "niter": 5,
              "nshot": nshot, "nr": nr, "nc": nc,
              "sfold": int(counts(s_k, nshot).max()), "rfold": int(counts(r_k, nr).max()),
              "cfold": int(counts(c_k, nc).max()), "mode": 0, "sub": 0}
    ssol, rsol = tmp / f"ssol_{tag}.bin", tmp / f"rsol_{tag}.bin"
    # ssol/rsol are file-valued: built here from paths this function chose, never from agent input, and passed
    # outside validate_params exactly as segyread's tape=.
    args = runner.validate_params(params) + [f"ssol={ssol}", f"rsol={rsol}"]
    runner.run_trusted("suresstat", args, stdin_path=sub,
                       stdout_path=tmp / f"rs_{tag}.out")
    src_s = np.fromfile(ssol, dtype="=f4")[: nshot + 1].astype(float)
    rec_s = np.fromfile(rsol, dtype="=f4")[: nr + 1].astype(float)
    return src_s, rec_s, counts(s_k, nshot), counts(r_k, nr), params


def _statics_pass(manifest, dataset_id, src, dst, tmp, geom, ctx, tz, pass_no, run_id):
    model_path = _statics_check(manifest)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    dt = geom["dt_s"]
    period = tz.get("tolerance_s")
    period_source = "R1"
    if not period:
        sample = np.arange(0, min(geom["ntr"], 400))
        period = 1.0 / gate_hz(sufile.read_traces(src, sample, geom).astype(float), dt)
        period_source = "G1_RICKER_EQUIVALENT_FROM_DATA"
    period = float(period)
    fa = ctx.get("first_arrivals")
    if fa:     # v0.33 L1: on land the mute follows the measured first arrivals
        mute_ctx = {**ctx, "direct_velocity_m_s": float(fa["velocity_m_s"]),
                    "direct_intercept_s": float(fa["intercept_s"])}
    else:
        mute_ctx = {**ctx, "direct_velocity_m_s": ctx["direct_velocity_m_s"] or S.ASSUMED_WATER_M_S}
    # 1. mute above the direct wave plus one period, 2. NMO with the validated model
    (prog, mute_args, _), = K.REGISTRY["mute_direct"]["build"](
        {"extra_s": min(period, 0.5), "taper_s": 0.05}, mute_ctx)
    _run_file(prog, mute_args, src, tmp / "rs_mute.su")
    cdps = [loc["cdp"] for loc in model["locations"]]
    tn = [[round(p["t0_s"], 3) for p in loc["function"]] for loc in model["locations"]]
    vn = [[round(p["v_m_s"], 1) for p in loc["function"]] for loc in model["locations"]]
    _run_file("sunmo", {"cdp": cdps, "tnmo": tn, "vnmo": vn, "smute": 1.5},
              tmp / "rs_mute.su", tmp / "rs_nmo.su")
    # 3. surface-consistent indices: shot = fldr rank, station = ground-position rank
    h = sufile.read_header_columns(src, ["fldr", "gx", "gy", "sx", "cdp"], geom)
    fldr = np.asarray(h["fldr"])
    shot = _ranks(fldr)
    station = _ranks(np.stack([np.asarray(h["gx"]), np.asarray(h["gy"])], axis=1))
    cmp_ = _ranks(np.asarray(h["cdp"]))
    ranks = (shot, station, cmp_)
    ntpick = max(1, int(round(period / 2 / dt)))
    every = np.ones(shot.size, dtype=bool)
    # v0.21 RS2: random CMP halves (fixed seed).
    odd = cmp_halves(cmp_)
    even = ~odd
    full = _suresstat(tmp / "rs_nmo.su", ranks, every, ntpick, tmp, "all")
    half_o = _suresstat(tmp / "rs_nmo.su", ranks, odd, ntpick, tmp, "odd")
    half_e = _suresstat(tmp / "rs_nmo.su", ranks, even, ntpick, tmp, "even")
    # 4. split-half reliability, over shots/stations seen at least twice in each half
    rel = {}
    for name, i in (("source", 0), ("receiver", 1)):
        both = (half_o[2 + i] >= 2) & (half_e[2 + i] >= 2)
        both[0] = False
        n = int(both.sum())
        rel[name] = {"reliability": (round(K.reliability(half_o[i][both], half_e[i][both]), 4)
                                     if n >= RS_MIN_COMPARED else None),
                     "compared": n}
    tau_ms = full[0][shot] + full[1][station]
    dt_ms = 1000 * dt
    tau_ms = tau_ms - dt_ms * round(float(np.mean(tau_ms)) / dt_ms)   # keep the datum
    rms_s = float(np.sqrt(np.mean(tau_ms ** 2))) / 1000
    ok_rel = all(v["reliability"] is not None and v["reliability"] >= K.RELIABILITY_MIN
                 for v in rel.values())
    ok_rms = rms_s <= period / 4
    # v0.21 materiality: expected stack amplitude factor of the statics left in
    amplitude_factor, ok_material = statics_material(rms_s, period)
    accepted = ok_rel and ok_rms and ok_material
    k = np.rint(tau_ms / dt_ms).astype(int)
    _rewrite_samples(src, dst, geom,
                     lambda d, start: apply_trace_statics(d, k[start:start + d.shape[0]]))
    # 5. the solution, keyed by what a reader can check it against
    sx = np.asarray(h["sx"])
    shots = {int(r): {"fldr": int(fldr[shot == r][0]), "sx": int(sx[shot == r][0]),
                      "static_ms": round(float(full[0][r]), 3)}
             for r in np.unique(shot)}
    gxy = np.stack([np.asarray(h["gx"]), np.asarray(h["gy"])], axis=1)
    stations = {int(r): {"gx": int(gxy[station == r][0][0]), "gy": int(gxy[station == r][0][1]),
                         "static_ms": round(float(full[1][r]), 3)}
                for r in np.unique(station)}
    solution = safe_output_path(as_rel(config.RESULT_DIR /
                                       f"{dataset_id}_residual_statics_p{pass_no}.json"),
                                overwrite=True)
    solution.write_text(json.dumps({
        "dataset_id": dataset_id, "run_id": run_id, "suresstat": full[4],
        "velocity_model": as_rel(model_path), "sign": "corrected(t) = recorded(t + static)",
        "shots": shots, "stations": stations,
        "halves": {"odd_cmp": {"source_ms": half_o[0].round(3).tolist(),
                               "receiver_ms": half_o[1].round(3).tolist()},
                   "even_cmp": {"source_ms": half_e[0].round(3).tolist(),
                                "receiver_ms": half_e[1].round(3).tolist()}},
        "reliability": rel, "rms_s": round(rms_s, 5),
        "stack_amplitude_factor": round(amplitude_factor, 4)}, indent=1), encoding="utf-8")
    qc = {"gate": "split-half reliability + materiality (v0.21 RS2)",
          "reliability": rel, "reliability_min": K.RELIABILITY_MIN,
          "split": f"random CMP halves, seed {RS_SPLIT_SEED}",
          "stack_amplitude_factor": round(amplitude_factor, 4),
          "materiality_rms_s": round(RS_MATERIAL_FRACTION * period, 5),
          "static_rms_s": round(rms_s, 5), "quarter_period_s": round(period / 4, 4),
          "period_source": period_source, "max_shift_samples": ntpick,
          "solution": as_rel(solution),
          "verdict": "PASS" if accepted else "FAIL"}
    if not accepted:
        why = []
        if not np.any(full[0][1:]) and not np.any(full[1][1:]):
            why.append("suresstat found no residual statics (every source and receiver "
                       "static is zero)")
        elif not ok_material:
            why.append(f"the statics are immaterial: rms {1000 * rms_s:.1f} ms would cost "
                       f"the stack only {100 * (1 - amplitude_factor):.0f}% of its amplitude "
                       f"(threshold {100 * (1 - K.PRESERVATION_MIN):.0f}%, i.e. rms > "
                       f"{1000 * RS_MATERIAL_FRACTION * period:.1f} ms)")
        if not ok_rel:
            parts = []
            for nm in ("source", "receiver"):
                v = rel[nm]
                parts.append(f"{nm} not comparable ({v['compared']} seen in both halves, "
                             f"< {RS_MIN_COMPARED})" if v["reliability"] is None else
                             f"{nm} reliability {v['reliability']:.2f}")
            why.append("statics from the two random CMP halves do not establish a repeatable "
                       f"solution ({'; '.join(parts)}; needed >= {K.RELIABILITY_MIN})")
        if not ok_rms:
            why.append(f"rms static {1000 * rms_s:.1f} ms exceeds a quarter period "
                       f"({250 * period:.0f} ms)")
        qc["reason"] = "; ".join(why) + "; the product is kept for audit and not used"
    chain = [{"operation": "residual_statics", "program": "suresstat",
              "args": full[4], "applied_in_process": True}]
    return accepted, qc, chain, {}


# --------------------------------------------------------------------------- v0.26
# DMO,-------------------------------------------------------------------------

DMO_TDMO_STEP_S = 0.1
DMO_SMUTE = 1.5


def _dmo_check(manifest):
    vcap = evidence.get_capability(manifest, "velocity.validated") or {}
    if vcap.get("status") != evidence.PASS and not governance.off():
        raise ValueError("dmo needs a validated velocity (it runs between NMO and inverse "
                         f"NMO); velocity.validated is {vcap.get('status', 'UNKNOWN')}.")
    bin_m = ((evidence.get_capability(manifest, "geometry.cmp_assigned") or {})
             .get("evidence", {}) or {}).get("bin_size_m")
    if not bin_m:
        raise ValueError("build_cmp recorded no bin size; DMO needs the cdp spacing.")
    return safe_input_path(evidence.get_artifact(manifest, "velocity_model")["path"]), float(bin_m)


def _scaled(values, scalco):
    v = np.asarray(values, dtype=np.float64)
    sc = np.asarray(scalco, dtype=np.float64)
    factor = np.where(sc > 0, sc, np.where(sc < 0, -1.0 / np.where(sc == 0, 1, sc), 1.0))
    return v * factor


def dmo_parameters(cdp, sx, bin_m, model, t):
    """sudmofk arguments from the file and the validated model (never from the caller)."""
    from . import migrate as MG
    ucdp = np.unique(cdp)
    step = float(np.median(np.diff(ucdp))) if ucdp.size > 1 else 1.0
    usx = np.unique(sx)
    shot_dx = float(np.median(np.diff(usx))) if usx.size > 1 else bin_m
    noffmix = max(1, int(round(shot_dx / bin_m)))
    med = np.median(MG.rms_grid(model["locations"], ucdp, t), axis=0)
    tk = np.arange(0.0, t[-1] + 1e-9, DMO_TDMO_STEP_S)
    vk = np.interp(tk, t, med)
    return {"cdpmin": int(ucdp.min()), "cdpmax": int(ucdp.max()),
            "dxcdp": round(bin_m * step, 3), "noffmix": noffmix,
            "tdmo": [round(float(x), 3) for x in tk], "vdmo": [round(float(x), 1) for x in vk]}, \
        {"shot_spacing_m": round(shot_dx, 2), "cdp_step": step}


def _nmo_args(model, invert=False):
    locs = model["locations"]
    a = {"cdp": [loc["cdp"] for loc in locs],
         "tnmo": [[round(p["t0_s"], 3) for p in loc["function"]] for loc in locs],
         "vnmo": [[round(p["v_m_s"], 1) for p in loc["function"]] for loc in locs],
         "smute": DMO_SMUTE}
    if invert:
        a["invert"] = 1
    return a


def _dmo_chain(src, dst, tmp, model, dmo_args, tag, with_dmo=True):
    _run_file("sunmo", _nmo_args(model), src, tmp / f"dmo_{tag}_nmo.su")
    cur = tmp / f"dmo_{tag}_nmo.su"
    if with_dmo:
        # susort keys are positional; fixed literals built here, never caller input
        runner.run_trusted("susort", ["offset", "cdp"], stdin_path=cur,
                           stdout_path=tmp / f"dmo_{tag}_co.su")
        _run_file("sudmofk", dmo_args, tmp / f"dmo_{tag}_co.su", tmp / f"dmo_{tag}_codmo.su")
        runner.run_trusted("susort", ["cdp", "offset"], stdin_path=tmp / f"dmo_{tag}_codmo.su",
                           stdout_path=tmp / f"dmo_{tag}_cmp.su")
        cur = tmp / f"dmo_{tag}_cmp.su"
    _run_file("sunmo", _nmo_args(model, invert=True), cur, dst)


def _read_all(path):
    g = sufile.geometry(path)
    h = sufile.read_header_columns(path, ["cdp", "offset"], g)
    return (np.asarray(h["cdp"]), np.asarray(h["offset"]),
            sufile.read_traces(path, np.arange(g["ntr"]), g).astype(np.float32))


def _dmo_pass(manifest, src, dst, tmp, geom, ctx, tz):
    """v0.26: NMO -> DMO -> inverse NMO, gated by flat-event preservation (D1)."""
    from . import migrate as MG
    model_path, bin_m = _dmo_check(manifest)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    dt, ns = geom["dt_s"], geom["ns"]
    t = geom["t_start_s"] + np.arange(ns) * dt
    h = sufile.read_header_columns(src, ["cdp", "offset", "sx", "scalco"], geom)
    cdp = np.asarray(h["cdp"])
    off = np.abs(np.asarray(h["offset"], dtype=np.float64))
    sx = _scaled(h["sx"], h["scalco"])
    dmo_args, info = dmo_parameters(cdp, sx, bin_m, model, t)
    # D1 injection: flat (zero-dip) reflections at every CMP, moveout from the model
    if ctx.get("first_arrivals"):     # v0.33 L1
        t_direct = gate_window({**ctx, "max_offset_m": float(off.max())})[0]
    else:
        v_d = ctx["direct_velocity_m_s"] or S.ASSUMED_WATER_M_S
        t_direct = float(off.max()) / float(v_d)
    record_end = float(t[-1])
    period = tz.get("tolerance_s")
    period_source = "R1"
    if not period:
        sample = np.arange(0, min(geom["ntr"], 400))
        period = 1.0 / gate_hz(sufile.read_traces(src, sample, geom).astype(float), dt)
        period_source = "G1_RICKER_EQUIVALENT_FROM_DATA"
    f0 = 1.0 / float(period)
    ucdp, inv = np.unique(cdp, return_inverse=True)
    vgrid = MG.rms_grid(model["locations"], ucdp, t)
    rms = float(np.sqrt(np.mean(sufile.read_traces(
        src, np.arange(0, geom["ntr"], max(1, geom["ntr"] // 400)), geom).astype(float) ** 2)) or 1.0)
    amp = K.INJECT_AMPLITUDE_X_RMS * rms
    t0s = [t_direct + frac * (record_end - t_direct) for frac in K.INJECT_FRACTIONS]

    def events(start, n):
        ev = np.zeros((n, ns))
        for j in range(n):
            i = start + j
            for t0 in t0s:
                v = float(np.interp(t0, t, vgrid[inv[i]]))
                tx = np.sqrt(t0 ** 2 + (off[i] / v) ** 2)
                ev[j] += amp * K.ricker(t - tx, f0)
        return ev

    inj_only = tmp / "dmo_inj_only.su"
    inj_data = tmp / "dmo_inj_data.su"
    _rewrite_samples(src, inj_only, geom, lambda d, st: events(st, d.shape[0]))
    _rewrite_samples(src, inj_data, geom, lambda d, st: d + events(st, d.shape[0]))
    _dmo_chain(src, dst, tmp, model, dmo_args, "data")
    _dmo_chain(inj_data, tmp / "dmo_inj_out.su", tmp, model, dmo_args, "inj")
    _dmo_chain(inj_only, tmp / "dmo_ref_out.su", tmp, model, dmo_args, "ref", with_dmo=False)
    c0, o0, _ = _read_all(src)
    c1, o1, out = _read_all(dst)
    _, _, out_inj = _read_all(tmp / "dmo_inj_out.su")
    _, _, ref = _read_all(tmp / "dmo_ref_out.su")
    order_ok = (c0.size == c1.size and np.array_equal(c0, c1) and np.array_equal(o0, o1))
    pres = K.preservation(out_inj, out, ref) if order_ok else 0.0
    finite = bool(np.isfinite(pres))
    accepted = bool(order_ok and finite and pres >= K.PRESERVATION_MIN)
    qc = {"gate": "flat-event preservation through NMO-DMO-inverse NMO (v0.26 D1)",
          "preservation": round(pres, 4), "preservation_min": K.PRESERVATION_MIN,
          "trace_order_kept": bool(order_ok), "injected_t0_s": [round(x, 3) for x in t0s],
          "injected_hz": round(f0, 2), "period_source": period_source,
          **({"window_rule": "v0.33 L1: land, measured first arrivals"}
             if ctx.get("first_arrivals") else {}),
          "sudmofk": {k: v for k, v in dmo_args.items() if k not in ("tdmo", "vdmo")},
          "vdmo_range_m_s": [min(dmo_args["vdmo"]), max(dmo_args["vdmo"])], **info,
          "verdict": "PASS" if accepted else "FAIL"}
    if not accepted:
        qc["reason"] = ("the output lost or reordered traces" if not order_ok else
                        "N0: the preservation measurement is not finite (non-finite samples)"
                        if not finite else
                        f"flat reflections kept only {pres:.2f} correlation (< "
                        f"{K.PRESERVATION_MIN}); the product is kept for audit and not used")
    chain = [{"operation": "dmo", "program": "sunmo", "args": "validated model, smute 1.5"},
             {"operation": "dmo", "program": "susort", "args": ["offset", "cdp"]},
             {"operation": "dmo", "program": "sudmofk", "args": dmo_args},
             {"operation": "dmo", "program": "susort", "args": ["cdp", "offset"]},
             {"operation": "dmo", "program": "sunmo", "args": "invert=1, same model"}]
    return accepted, qc, chain, {}


def _kill_pass(src, dst, geom):
    """v0.30 kill_corrupt: zero the corrupt traces, touch nothing else (gate K0)."""
    rms, mx, nf = sanity.file_stats(src, geom)
    bad, scale, limit = sanity.corrupt_mask(rms, mx, nf)
    ntr, stride = geom["ntr"], geom["trace_bytes"]
    raw = np.fromfile(src, dtype=np.uint8).reshape(ntr, stride)
    out = raw.copy()
    out[bad, sufile.HEADER_BYTES:] = 0          # 0.0 in either byte order
    dst.write_bytes(out.tobytes())
    back = np.fromfile(dst, dtype=np.uint8).reshape(ntr, stride)
    others_same = bool(np.array_equal(back[~bad], raw[~bad]))
    left = sanity.scan(dst, geom)["corrupt_count"]
    frac = float(bad.sum()) / max(1, ntr)
    accepted = bool(frac <= sanity.KILL_MAX_FRACTION and others_same and left == 0)
    cdp = np.asarray(sufile.read_header_columns(src, ["cdp"], geom)["cdp"])
    qc = {"gate": "K0 (v0.30): corrupt traces <= 1% of the file, others byte-identical, none left",
          "killed_traces": int(bad.sum()), "killed_fraction": round(frac, 6),
          "killed_cdps": sorted({int(c) for c in cdp[bad]})[:200],
          "median_trace_rms": scale, "limit": limit,
          "max_abs_killed": float(mx[bad].max()) if bad.any() else None,
          "others_byte_identical": others_same, "corrupt_left": int(left),
          "verdict": "PASS" if accepted else "FAIL"}
    if not accepted:
        qc["reason"] = ("more than 1% of the traces are corrupt: this is not a few bad traces"
                        if frac > sanity.KILL_MAX_FRACTION else
                        "the output changed a trace that was not corrupt, or left one")
    chain = [{"operation": "kill_corrupt", "program": "in-process",
              "args": {"traces": int(bad.sum())}}]
    return accepted, qc, chain, {}


def condition_gathers(dataset_id: str, operations) -> dict:
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["geometry.cmp_assigned", "geometry.fold_valid"],
                     "Gather conditioning")
    budgets = _budgets(manifest)
    done = int(budgets.get("conditioning_passes", 0))
    if done >= K.MAX_PASSES:
        raise S.BudgetExhausted(
            f"{done} conditioning passes already spent on {dataset_id!r}; the "
            f"limit is {K.MAX_PASSES} per dataset.")

    src = safe_input_path(evidence.get_artifact(manifest, "cmp_sorted")["path"])
    geom = sufile.geometry(src)
    if _header_statics_present(src, geom):
        raise ValueError(
            "The CMP file carries source/receiver statics that pick_velocity "
            "applies later; conditioning before them would filter uncorrected "
            "traces. Not supported.")
    cols = sufile.read_header_columns(src, ["cdp", "offset"], geom)
    runs = gather_runs(cols["cdp"])
    offsets = np.asarray(cols["offset"], dtype=np.float64)
    tz_cap, tz = _time_zero(manifest)
    ctx = {"dt_s": geom["dt_s"], "max_offset_m": float(np.abs(offsets).max()),
           "direct_velocity_m_s": tz.get("direct_velocity_m_s"),
           "first_arrivals": acqstatics.land_first_arrivals(manifest)}     # v0.33 L0/L1
    steps = K.resolve(operations, ctx)          # validation errors spend no budget
    solo = steps[0][0] if steps[0][0] in K.SOLO_OPERATIONS else None
    # v0.30 Q0: corrupt samples are removed first, or nothing runs; spends no budget
    q0 = sanity.scan(src, geom)
    if solo == "kill_corrupt" and not q0["corrupt_count"]:
        raise ValueError("kill_corrupt: the Q0 sample check finds no corrupt trace in "
                         "cmp_sorted; there is nothing to remove.")
    if solo != "kill_corrupt" and q0["corrupt_count"] and not governance.off():
        raise ValueError(
            f"Q0: cmp_sorted holds {q0['corrupt_count']} corrupt trace(s) (non-finite or "
            f"beyond 120 dB of the median trace RMS) at CDP {q0['corrupt_cdps'][:10]}; any "
            "filter, gain, DMO or statics would spread them. Run condition_gathers "
            "[{\"op\": \"kill_corrupt\"}] first.")
    # refusals that need no data spend no budget either
    if solo == "datum_shift":
        _datum_check(tz_cap, tz)
    elif solo == "residual_statics":
        _statics_check(manifest)
    elif solo == "dmo":
        _dmo_check(manifest)

    pass_no = done + 1
    out_dir = config.WORK_DIR / dataset_id
    tmp = out_dir / f"_conditioning_tmp_{run_id}"
    tmp.mkdir(parents=True, exist_ok=True)
    dst = safe_output_path(as_rel(out_dir / f"{dataset_id}_cmp_conditioned_p{pass_no}.su"),
                           overwrite=True)
    try:
        if solo == "datum_shift":
            accepted, qc, chain, extra = _datum_pass(src, dst, geom, tz)
        elif solo == "residual_statics":
            accepted, qc, chain, extra = _statics_pass(manifest, dataset_id, src, dst, tmp,
                                                       geom, ctx, tz, pass_no, run_id)
        elif solo == "dmo":
            accepted, qc, chain, extra = _dmo_pass(manifest, src, dst, tmp, geom, ctx, tz)
        elif solo == "kill_corrupt":
            accepted, qc, chain, extra = _kill_pass(src, dst, geom)
        else:
            accepted, qc, chain, extra = _injection_pass(steps, src, dst, tmp, geom, runs,
                                                         offsets, ctx, tz)
        budgets["conditioning_passes"] = pass_no
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if governance.off():
        accepted = True          # baseline01 C0: every product is adopted

    entry = {"pass": pass_no, "run_id": run_id, "operations": operations,
             "chain": chain, "input": as_rel(src), "output": as_rel(dst), "qc": qc,
             "accepted": accepted}
    manifest.setdefault("conditioning", []).append(entry)
    previously = evidence.capability_status(manifest, "processing.preprocessed")
    if accepted:
        if "cmp_sorted_unconditioned" not in manifest.get("artifacts", {}):
            manifest["artifacts"]["cmp_sorted_unconditioned"] = dict(
                manifest["artifacts"]["cmp_sorted"])
        evidence.add_artifact(manifest, "cmp_sorted", dst, "cmp-sorted-conditioned",
                              parents=[as_rel(src)], run_id=run_id)
        _set(manifest, "processing.preprocessed", True,
             {"passes": [e["pass"] for e in manifest["conditioning"] if e["accepted"]],
              "operations": [op for e in manifest["conditioning"] if e["accepted"]
                             for op in e["operations"]],
              "last_gate": qc.get("gate"), "output": as_rel(dst)},
             run_id, artifact=as_rel(dst))
        if "time_zero" in extra:
            _set(manifest, "acquisition.time_zero_consistent", True, extra["time_zero"],
                 run_id, notes=[f"re-measured after a datum shift of "
                                f"{1000 * extra['time_zero']['datum_shift_applied_s']:+.0f} ms: "
                                + extra["time_zero"].get("reason", "")])
        for name in _DOWNSTREAM:
            _set(manifest, name, None,
                 {"reason": "the CMP gathers were conditioned", "conditioning_run_id": run_id},
                 run_id, notes=["Earlier products were built from unconditioned gathers."])
        evidence.invalidate_downstream(manifest, "stack.completed", "the CMP gathers were conditioned",
                                       ITERATE_VERSION, run_id)
    else:
        evidence.add_artifact(manifest, f"conditioning_rejected_p{pass_no}", dst,
                              "conditioning-rejected", parents=[as_rel(src)],
                              run_id=run_id)
        if previously != evidence.PASS:
            verdict = qc.get("verdict")
            _set(manifest, "processing.preprocessed",
                 False if verdict == "FAIL" else None,
                 {"operations": operations, "gate": qc.get("gate"),
                  "rejected_output": as_rel(dst)}, run_id,
                 notes=[qc.get("reason", "conditioning gate not passed")])
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id, "pass": pass_no,
            "passes_left": K.MAX_PASSES - pass_no, "accepted": accepted,
            "operations": operations, "chain": chain, "qc": qc,
            "input": as_rel(src), "output": as_rel(dst),
            "cmp_sorted_now": evidence.get_artifact(manifest, "cmp_sorted")["path"],
            "capabilities": {n: evidence.capability_status(manifest, n)
                             for n in ("processing.preprocessed",
                                       "acquisition.time_zero_consistent") + _DOWNSTREAM},
            "algorithm_version": ITERATE_VERSION}



# ---------------------------------------------------------------------------
# refine_velocity,-------------------------------------------------------------------------

def _analyse(su_path, geom, cdps, params, direct_wave, label):
    cols = sufile.read_header_columns(su_path, ["cdp", "offset"], geom)
    idx = np.flatnonzero(np.isin(np.asarray(cols["cdp"]), cdps))
    data = sufile.read_traces(su_path, idx, geom).astype(np.float64)
    off = np.abs(np.asarray(cols["offset"], dtype=float))[idx]
    rep = velocity.analyse_gather(
        data, off, geom["dt_s"], geom["t_start_s"],
        v_min=params["v_min"], v_max=params["v_max"], v_step=params["v_step"],
        t_step=params["t_step"], f_lo=params["band_low"], f_hi=params["band_high"],
        n_points=params["n_points"], max_rate_m_s2=params["max_rate_m_s2"],
        label=label, direct_wave=direct_wave,
        # v0.20: every refine test is one more chance to pass on noise
        null_trials=REFINE_NULL_TRIALS, path_alpha=REFINE_PATH_ALPHA, local_trials=39)
    rep["traces"] = int(idx.size)
    rep["pooled_cdps"] = [int(c) for c in cdps]
    return rep


def refine_velocity(dataset_id: str) -> dict:
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["geometry.cmp_assigned", "geometry.fold_valid",
                                "velocity.model_available"], "Velocity refinement")
    vcap = evidence.get_capability(manifest, "velocity.validated") or {}
    if vcap.get("status") != evidence.FAIL and not governance.off():
        raise ValueError(f"velocity.validated is {vcap.get('status', 'UNKNOWN')}; "
                         "refine_velocity runs only after a velocity FAIL.")
    tz_cap, tz = _time_zero(manifest)
    if tz_cap.get("status") == evidence.FAIL and not governance.off():
        raise ValueError(
            "acquisition.time_zero_consistent is FAIL: the time axis is not "
            "anchored at the shot, and no choice of gathers removes that bias. "
            "Refinement refused.")
    model_path = safe_input_path(evidence.get_artifact(manifest, "velocity_model")["path"])
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("refinement"):
        raise S.BudgetExhausted("This velocity model was already refined once; "
                                "run pick_velocity again for a new model.")
    params = model.get("pick_parameters")
    if not params:
        raise ValueError("The velocity model predates v0.19 and does not record "
                         "its pick parameters; run pick_velocity again.")
    budgets = _budgets(manifest)
    if int(budgets.get("velocity_analyses", 0)) >= S.MAX_VELOCITY_ANALYSES:
        raise S.BudgetExhausted(
            f"{budgets['velocity_analyses']} velocity analyses already run on "
            f"{dataset_id!r}; the limit is {S.MAX_VELOCITY_ANALYSES}.")
    reports = model["reports"]
    failed0 = [int(r["cdp"]) for r in reports if not r["valid"]]
    if governance.off():
        # baseline01 C0: no validity is known; every analysed location is re-picked and adopted
        failed0 = [int(r["cdp"]) for r in reports]
    if not failed0:
        raise ValueError("No analysed location failed; the FAIL is not "
                         "location-level and re-picking cannot change it.")

    su_path = safe_input_path(model["input"])
    geom = sufile.geometry(su_path)
    all_cdp, fold = np.unique(np.asarray(
        sufile.read_header_columns(su_path, ["cdp"], geom)["cdp"]), return_counts=True)
    eligible, _ = S.choose_analysis_locations(all_cdp, fold, all_cdp.size)
    analysed = sorted(int(r["cdp"]) for r in reports)
    spacing = float(np.median(np.diff(analysed))) if len(analysed) > 1 else 0.0
    direct_wave = ({"velocity_m_s": tz["direct_velocity_m_s"],
                    "period_s": tz["tolerance_s"]}
                   if tz.get("direct_velocity_m_s") and tz.get("tolerance_s") else None)

    current = {int(r["cdp"]): r for r in reports}     # keyed by ORIGINAL location
    pending = list(failed0)
    attempts, grade = [], None
    ladder = [("supergather_5", SUPERGATHER_HALF), ("relocate", None),
              ("wide_supergather_9", WIDE_SUPERGATHER_HALF)]
    for strategy, half in ladder[:MAX_REFINE_ATTEMPTS]:
        tried = []
        for loc in list(pending):
            if strategy == "relocate":
                cands = relocation_candidates(loc, eligible, analysed, spacing)
                outcome = {"location": loc, "candidates": cands, "result": None}
                for cand in cands:
                    pool = supergather_cdps(all_cdp, cand, SUPERGATHER_HALF)
                    rep = _analyse(su_path, geom, pool, params, direct_wave,
                                   f"cdp {cand} (relocated from {loc}, 5-CMP)")
                    rep.update(cdp=cand, relocated_from=loc, strategy=strategy)
                    outcome.setdefault("tries", []).append(
                        {"cdp": cand, "valid": rep["valid"], "problems": rep["problems"]})
                    if rep["valid"]:
                        current[loc] = rep
                        pending.remove(loc)
                        outcome["result"] = cand
                        break
            else:
                pool = supergather_cdps(all_cdp, loc, half)
                rep = _analyse(su_path, geom, pool, params, direct_wave,
                               f"cdp {loc} ({len(pool)}-CMP supergather)")
                rep.update(cdp=loc, strategy=strategy)
                outcome = {"location": loc, "pooled_cdps": pool,
                           "valid": rep["valid"], "problems": rep["problems"]}
                if rep["valid"] or governance.off():
                    current[loc] = rep
                    pending.remove(loc)
            tried.append(outcome)
        grade = S.grade_velocity_locations(list(current.values()))
        attempts.append({"attempt": len(attempts) + 1, "strategy": strategy,
                         "locations": tried, "model_passes_after": grade["ok"],
                         "still_failed": list(pending)})
        if grade["ok"] or not pending:
            break

    scope = None if governance.off() else scope_from_grade(grade, list(current.values()))
    if scope:
        grade = {**grade, "ok": True, "scope": scope,
                 "problems": [f"scoped release (S1): the stack is limited to cdp "
                              f"{scope[0]}-{scope[1]}, the span the valid locations "
                              f"measure ({100 * grade['coverage_fraction']:.0f}% of the "
                              "analysed span); nothing beyond the last measured location "
                              "is released"]}
    velocity_attempts = 1 + len(attempts)
    budgets["velocity_analyses"] = int(budgets.get("velocity_analyses", 0)) + 1
    final = list(current.values())
    failed = grade["failed"]
    functions = [{"cdp": int(r["cdp"]), "function": r["function"]} for r in grade["valid"]]
    if governance.off():
        functions = [{"cdp": int(r["cdp"]), "function": r["function"]} for r in final if r.get("function")]
    refinement = {"run_id": run_id, "version": ITERATE_VERSION,
                  "original_run_id": model.get("run_id"),
                  "original_failed_locations": failed0,
                  "attempts": attempts, "velocity_attempts": velocity_attempts,
                  "original_reports": {str(c): model_r for c, model_r in
                                       ((int(r["cdp"]), r) for r in reports)
                                       if c in failed0}}
    notes = grade["problems"] + [
        f"cdp {r['cdp']} omitted from interpolation: {'; '.join(r['problems'])}"
        for r in failed]
    notes.append(f"velocity model reached after {velocity_attempts} attempt(s) "
                 f"({', '.join(a['strategy'] for a in attempts)} after the first pick)")

    out_path = config.WORK_DIR / dataset_id / "velocity_model_refined.json"
    new_model = {**{k: v for k, v in model.items() if k not in ("reports", "locations")},
                 "run_id": run_id, "locations": functions, "reports": final,
                 "location_grade": {k: v for k, v in grade.items()
                                    if k not in ("valid", "failed")},
                 "refinement": refinement, **({"scope": scope} if scope else {})}
    out_path.write_text(json.dumps(new_model, indent=2, default=str), encoding="utf-8")
    manifest["artifacts"]["velocity_model_unrefined"] = dict(
        manifest["artifacts"]["velocity_model"])
    windows = [r["dix_valid_window"] for r in final if r.get("dix_valid_window")]
    ends = [w["valid_to_s"] for w in windows]
    dix_valid_to = None if (not ends or any(e is None for e in ends)) else min(ends)

    _set(manifest, "velocity.model_available", True,
         {"locations": [f["cdp"] for f in functions],
          "locations_analysed": [int(r["cdp"]) for r in final],
          "locations_omitted": [int(r["cdp"]) for r in failed],
          "model": as_rel(out_path), "refined": True},
         run_id, artifact=as_rel(out_path))
    _set(manifest, "velocity.validated", grade["ok"],
         {"locations_analysed": len(final),
          "locations_valid": [int(r["cdp"]) for r in grade["valid"]],
          "locations_failed": [int(r["cdp"]) for r in failed],
          "required_valid": grade["required_valid"],
          "coverage_fraction": grade["coverage_fraction"],
          "supported_to_s": {int(r["cdp"]): r["supported_to_s"] for r in final},
          "median_semblance": {int(r["cdp"]): r["median_semblance"] for r in final},
          "dix_checked": True,
          "time_zero_status": tz_cap.get("status", evidence.UNKNOWN),
          "scan_edge_picks": {int(r["cdp"]): r.get("scan_edge_picks") for r in final},
          "dix_valid_to_s_report_only": dix_valid_to,
          "velocity_attempts": velocity_attempts,
          "refinement_strategies": [a["strategy"] for a in attempts]
          + (["scope"] if scope else []),
          **({"scope_cdp": scope} if scope else {})},
         run_id, notes=notes)
    for name in ("nmo.applied", "stack.completed"):
        _set(manifest, name, None, {"reason": "velocity model was refined",
                                    "velocity_run_id": run_id}, run_id,
             notes=["Any earlier product belongs to a superseded velocity model."])
    evidence.invalidate_downstream(manifest, "stack.completed", "the velocity model was refined",
                                   ITERATE_VERSION, run_id)
    evidence.add_artifact(manifest, "velocity_model", out_path, "velocity-model",
                          parents=[as_rel(su_path), as_rel(model_path)], run_id=run_id)
    evidence.save(manifest)
    return {"run_id": run_id, "dataset_id": dataset_id, "model": as_rel(out_path),
            "velocity_attempts": velocity_attempts, "attempts": attempts,
            "capabilities": {"velocity.validated": evidence.capability_status(
                manifest, "velocity.validated")},
            "locations": [{"cdp": int(r["cdp"]), "valid": r["valid"],
                           "strategy": r.get("strategy", "original"),
                           "pooled_cdps": r.get("pooled_cdps"),
                           "relocated_from": r.get("relocated_from"),
                           "supported_to_s": r["supported_to_s"],
                           "problems": r["problems"]} for r in final],
            "location_grade": {k: v for k, v in grade.items()
                               if k not in ("valid", "failed")},
            "velocity_analyses_used": budgets["velocity_analyses"],
            "notes": notes, "algorithm_version": ITERATE_VERSION}
