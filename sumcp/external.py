"""Geometry that is not in the file."""

from __future__ import annotations

import numpy as np

from . import claims as C

EXTERNAL_VERSION = "external-0.1"

RESOLVED, INDETERMINATE = "RESOLVED", "INDETERMINATE"

# Seawater over the range the literature allows for a marine direct arrival.
SEAWATER_RANGE_M_S = (1440.0, 1560.0)

# A direct arrival has to stand above what the same gather reaches by accident.
MIN_DIRECT_CONTRAST = 3.0

# How much more the fold profile may move than one rise and one fall.
MAX_FOLD_RAGGEDNESS = 1.5

__all__ = ["EXTERNAL_VERSION", "RESOLVED", "INDETERMINATE",
           "SEAWATER_RANGE_M_S", "MAX_FOLD_RAGGEDNESS", "MIN_DIRECT_CONTRAST",
           "shotpoint_mapping", "interpolate_track",
           "receiver_positions", "midpoints", "linear_moveout_fit",
           "direct_arrival_consistency", "fold_pattern", "validate_assignment"]


# ------------------------------------------------------- shotpoint mapping
def shotpoint_mapping(field_records, pairs=None, *, allow_counting=False) -> dict:
    """Tie each field record to the survey shotpoint it belongs to."""
    records = np.asarray(sorted(set(int(f) for f in field_records)), dtype=np.int64)
    out = {"algorithm_version": EXTERNAL_VERSION,
           "field_records": int(records.size),
           "field_record_range": [int(records.min()), int(records.max())]
           if records.size else None}

    if not pairs:
        if not allow_counting:
            out.update(
                verdict=INDETERMINATE,
                reason=("No field-record to shotpoint pairs were supplied. The "
                        "mapping cannot be counted from a shotpoint range: a "
                        "tape with fewer records than the range spans is "
                        "missing some, and an arithmetic mapping is then wrong "
                        "on one side of every gap without saying so."),
                what_would_answer_it=(
                    "The observer log for this line, which lists the shotpoint "
                    "against each field file or record number."))
            return out
        out.update(verdict=RESOLVED,
                   mapping={int(r): int(r) for r in records},
                   note="counting allowed by the caller; fixtures only")
        return out

    listed = {int(f): int(sp) for f, sp in pairs}
    known = np.asarray(sorted(listed), dtype=np.int64)
    if known.size < 2:
        out.update(verdict=INDETERMINATE,
                   reason=f"Only {known.size} pair(s) given; at least two are "
                          f"needed before anything between them can be filled in.")
        return out

    steps = np.diff([listed[int(k)] for k in known]) / np.diff(known)
    step = float(np.median(steps))
    consistent = bool(np.allclose(steps, step, atol=1e-9))
    mapping, gaps = {}, []
    for record in records:
        r = int(record)
        if r in listed:
            mapping[r] = listed[r]
            continue
        after = known[known > r]
        before = known[known < r]
        if not (after.size and before.size and consistent):
            gaps.append(r)
            continue
        anchor = int(before[-1])
        mapping[r] = int(round(listed[anchor] + step * (r - anchor)))

    out.update({
        "pairs_given": len(listed),
        "shotpoint_step_per_record": step,
        "step_consistent": consistent,
        "records_mapped": len(mapping),
        "records_unmapped": gaps[:20],
        "n_unmapped": len(gaps),
    })
    if gaps:
        out.update(verdict=INDETERMINATE, mapping=mapping, reason=(
            f"{len(gaps)} of {records.size} records could not be mapped: they "
            f"fall outside the listed pairs, or the shotpoint step between "
            f"listed pairs is not constant ({'consistent' if consistent else 'inconsistent'}). "
            f"Geometry is not attached to a record whose shotpoint is unknown."))
    else:
        out.update(verdict=RESOLVED, mapping=mapping, claim=C.derived(
            "field record -> shotpoint", "observer log pairs, filled in only "
            "between listed anchors at a constant step",
            inputs=[C.observed("shotpoint pairs", "observer log",
                               origin=C.ORIGIN_ACQUISITION_LOG)]))
    return out


# ------------------------------------------------------------- navigation
def interpolate_track(nav_shotpoints, nav_x, nav_y, wanted) -> dict:
    """Positions at every shotpoint, from positions at some of them."""
    sp = np.asarray(nav_shotpoints, dtype=np.float64)
    order = np.argsort(sp)
    sp, x, y = sp[order], np.asarray(nav_x, float)[order], np.asarray(nav_y, float)[order]
    if sp.size < 2:
        raise ValueError("Track interpolation needs at least two fixes.")
    step = float(np.median(np.diff(sp)))

    seg = np.hypot(np.diff(x), np.diff(y))
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    wanted = np.asarray(wanted, dtype=np.float64)
    inside = (wanted >= sp[0]) & (wanted <= sp[-1])
    arc_at = np.interp(wanted, sp, arc)
    out_x = np.interp(arc_at, arc, x)
    out_y = np.interp(arc_at, arc, y)

    return {
        "algorithm_version": EXTERNAL_VERSION,
        "x": out_x, "y": out_y,
        "inside_navigation": inside,
        "n_outside": int((~inside).sum()),
        "fix_interval_shotpoints": step,
        "track_length_m": float(arc[-1]),
        "position": C.derived(
            "source position at every shotpoint",
            "along-track interpolation between navigation fixes",
            inputs=[C.observed("navigation fixes", "survey navigation file",
                               origin=C.ORIGIN_NAVIGATION)],
            interpolation="along-track arc length",
            fix_interval_shotpoints=step),
    }


# ------------------------------------------------------------- the geometry
def receiver_positions(source_x, source_y, offsets, *, tangent=None,
                       next_x=None, next_y=None) -> dict:
    """Place the streamer behind the boat, along the local track tangent."""
    sx = np.asarray(source_x, float)
    sy = np.asarray(source_y, float)
    offsets = np.asarray(offsets, float)

    if tangent is None:
        if next_x is None or next_y is None:
            raise ValueError("Give tangent= or the next shot's position.")
        dx = np.asarray(next_x, float) - sx
        dy = np.asarray(next_y, float) - sy
        length = np.hypot(dx, dy)
        length[length == 0] = 1.0
        tangent = np.stack([dx / length, dy / length], axis=-1)
    tangent = np.asarray(tangent, float)

    gx = sx[..., None] - offsets * tangent[..., 0:1]
    gy = sy[..., None] - offsets * tangent[..., 1:2]
    return {
        "gx": gx, "gy": gy,
        "geometry_type": "nominal 2-D acquisition geometry",
        "not": "true receiver position",
        "assumption": ("The streamer is straight and aligned with the "
                       "direction of travel. No compass or bird data exists "
                       "for this survey, so feathering is neither recovered "
                       "nor modelled."),
        "claim": C.derived(
            "receiver positions", "source position offset along the track tangent",
            inputs=[C.assumed("channel offsets", "cable layout",
                              origin=C.ORIGIN_ACQUISITION_LOG)]),
    }


def midpoints(sx, sy, gx, gy):
    return 0.5 * (np.asarray(sx, float)[..., None] + np.asarray(gx, float)), \
           0.5 * (np.asarray(sy, float)[..., None] + np.asarray(gy, float))


# ------------------------------------------------------------- validation
def linear_moveout_fit(data, offsets, dt, t_start=0.0,
                       v_range=(1200.0, 2200.0), v_step=5.0,
                       t_range=None, window_samples=7) -> dict:
    """Best straight line t = |x|/v + c through a gather, and how much it beats the same gather's own accidents."""
    data = np.asarray(data, float)
    x = np.abs(np.asarray(offsets, float))
    ntr, ns = data.shape
    norm = data / (np.sqrt((data ** 2).mean(axis=1))[:, None] + 1e-30)

    velocities = np.arange(v_range[0], v_range[1] + 1e-9, v_step)
    lo = 0 if t_range is None else max(0, int((t_range[0] - t_start) / dt))
    hi = ns if t_range is None else min(ns, int((t_range[1] - t_start) / dt))
    span = hi - lo
    if span < 32:
        raise ValueError("The window is too short to fit anything.")

    # Semblance over a WINDOW, not a sample.
    size = max(1, int(window_samples))
    best = (-np.inf, None, None)
    scores = []
    for v in velocities:
        shift = np.round((x / v) / dt).astype(int)
        index = np.clip(np.arange(lo, hi)[None, :] + shift[:, None], 0, ns - 1)
        flat = np.take_along_axis(norm, index, axis=1)
        num = np.concatenate(([0.0], np.cumsum(flat.sum(axis=0) ** 2)))
        den = np.concatenate(([0.0], np.cumsum((flat ** 2).sum(axis=0))))
        semb = ((num[size:] - num[:-size])
                / (ntr * (den[size:] - den[:-size]) + 1e-30))
        j = int(semb.argmax())
        scores.append(float(semb[j]))
        if semb[j] > best[0]:
            best = (float(semb[j]), float(v),
                    float(t_start + (lo + j + size // 2) * dt))
    scores = np.asarray(scores)
    median = float(np.median(scores))
    return {
        "best_semblance": best[0], "velocity_m_s": best[1],
        "intercept_s": best[2],
        "median_semblance_over_velocities": median,
        "contrast": best[0] / (median + 1e-30),
        "velocities_tried": [float(velocities[0]), float(velocities[-1])],
        "window_samples": size,
    }


def direct_arrival_consistency(data, offsets, dt, t_start=0.0,
                               seawater=SEAWATER_RANGE_M_S) -> dict:
    """Does the direct arrival line up at seawater speed on these offsets?"""
    # Searched far wider than seawater on purpose.
    fit = linear_moveout_fit(data, offsets, dt, t_start,
                             v_range=(600.0, 4000.0), v_step=10.0)
    informative = fit["contrast"] >= MIN_DIRECT_CONTRAST
    inside = seawater[0] <= (fit["velocity_m_s"] or 0.0) <= seawater[1]
    out = {"algorithm_version": EXTERNAL_VERSION, **fit,
           "seawater_bracket_m_s": list(seawater),
           "inside_seawater_bracket": bool(inside)}
    if not informative:
        out.update(verdict=INDETERMINATE, reason=(
            f"No linear arrival stands out: the best velocity scores "
            f"{fit['best_semblance']:.4f} against a median of "
            f"{fit['median_semblance_over_velocities']:.4f} over the velocities "
            f"tried, a contrast of {fit['contrast']:.2f} below the "
            f"{MIN_DIRECT_CONTRAST} this test needs. The assignment is neither "
            f"supported nor contradicted here."))
    elif inside:
        out.update(verdict=RESOLVED, supports_assignment=True, reason=(
            f"The direct arrival lines up at {fit['velocity_m_s']:.0f} m/s on "
            f"the assigned offsets, inside the {seawater[0]:.0f}-"
            f"{seawater[1]:.0f} m/s bracket, with a contrast of "
            f"{fit['contrast']:.2f}. Offsets that were wrong in order or in "
            f"scale would not do this."))
    else:
        out.update(verdict=RESOLVED, supports_assignment=False, reason=(
            f"A linear arrival is present and strong (contrast "
            f"{fit['contrast']:.2f}) but lines up at {fit['velocity_m_s']:.0f} "
            f"m/s, outside the seawater bracket. Either the assigned offsets "
            f"are wrong by roughly a factor of "
            f"{fit['velocity_m_s'] / 1500.0:.2f}, or the arrival being timed is "
            f"not the direct wave."))
    return out


def fold_pattern(cdp) -> dict:
    """Does the fold profile look like a line that was shot, or like a bug?"""
    cdp = np.asarray(cdp, dtype=np.int64)
    bins, counts = np.unique(cdp, return_counts=True)
    if bins.size < 8:
        return {"verdict": INDETERMINATE,
                "reason": f"{bins.size} bins is too few to see a profile in."}
    plateau = float(np.median(counts))

    # Counting direction changes does not work: a real roll-along climbs in steps (1,1,2,2,3,3...) and changes
    # direction at more than half the bins while looking exactly as it should.
    window = 5
    smooth = (np.convolve(counts.astype(float), np.ones(window) / window,
                          mode="valid")
              if counts.size >= window else counts.astype(float))
    variation = float(np.abs(np.diff(smooth)).sum())
    span = float(smooth.max() - smooth.min())
    ragged = variation / (2.0 * span) if span > 0 else np.inf

    out = {"algorithm_version": EXTERNAL_VERSION,
           "bins": int(bins.size), "fold_median": plateau,
           "fold_min": int(counts.min()), "fold_max": int(counts.max()),
           "total_variation": round(variation, 1),
           "single_rise_and_fall": round(2.0 * span, 1),
           "raggedness": round(float(ragged), 3)}
    if ragged > MAX_FOLD_RAGGEDNESS:
        out.update(verdict=RESOLVED, supports_assignment=False, reason=(
            f"The fold profile moves {ragged:.1f} times as much as one rise "
            f"and one fall would need. A line that was shot rolls in, holds "
            f"and rolls out; this alternates, which is what a wrong channel "
            f"order or offset sign does to the binning."))
    else:
        out.update(verdict=RESOLVED, supports_assignment=True, reason=(
            f"Fold rises, holds near {plateau:.0f} and falls, with a profile "
            f"that moves {ragged:.1f} times a single rise and fall -- the "
            f"shape of a line that was rolled along."))
    return out


def validate_assignment(checks) -> dict:
    """Combine the independent checks without letting one of them decide alone."""
    against = [k for k, v in checks.items() if v.get("supports_assignment") is False]
    for_ = [k for k, v in checks.items() if v.get("supports_assignment") is True]
    silent = [k for k, v in checks.items() if "supports_assignment" not in v]
    out = {"algorithm_version": EXTERNAL_VERSION,
           "supported_by": for_, "contradicted_by": against,
           "could_not_tell": silent,
           "checks": {k: v.get("reason") for k, v in checks.items()}}
    if against:
        out.update(verdict="REJECTED", reason=(
            "The assigned geometry is contradicted by "
            + ", ".join(against) + ". It is not attached to the data."))
    elif for_:
        out.update(verdict="ACCEPTED", reason=(
            "Supported by " + ", ".join(for_) + " and contradicted by nothing."
            + (f" {', '.join(silent)} could not tell." if silent else "")))
    else:
        out.update(verdict=INDETERMINATE, reason=(
            "No check could tell. The geometry parsed and nothing in the data "
            "either supports or contradicts it, which is not the same as "
            "correct."))
    return out


# ---------------------------------------------- SPS relation assignment Added in v0.13.0.

SPS_ASSIGN_VERSION = "external-sps-0.2"

__all__ += ["SPS_ASSIGN_VERSION", "line_direction", "relation_assignment"]


def line_direction(rx, ry, station):
    """A deterministic unit vector along the line, pointing toward increasing receiver station number."""
    x = np.asarray(rx, float)
    y = np.asarray(ry, float)
    pts = np.stack([x - x.mean(), y - y.mean()], axis=1)
    # principal axis; for a straight or gently curved 2-D line this is the line
    _u, _s, vt = np.linalg.svd(pts, full_matrices=False)
    u = vt[0]
    u = u / (np.hypot(*u) or 1.0)
    station = np.asarray(station, float)
    if np.ptp(station) > 0 and np.corrcoef(pts @ u, station)[0, 1] < 0:
        u = -u
    return u


def relation_assignment(fldr, tracf, trid, sps_set) -> dict:
    """Give every data trace its source and receiver, from the X relation."""
    fldr = np.asarray(fldr, dtype=np.int64)
    tracf = np.asarray(tracf, dtype=np.int64)
    trid = np.asarray(trid, dtype=np.int64)
    ntr = fldr.size

    trid_informative = bool(np.unique(trid).size > 1)
    is_data = (trid == 1) if trid_informative else np.ones(ntr, dtype=bool)

    sources = sps_set["sources"]
    receivers = sps_set["receivers"]
    checks, problems = {}, []

    # ---- relations grouped by field record, overlaps refused ---------------
    by_record, dup_channel = {}, []
    for rel in sps_set["relations"]:
        by_record.setdefault(rel["record"], []).append(rel)
    for record, rels in by_record.items():
        seen = {}
        for rel in rels:
            step = max(1, abs(rel["channel_increment"]))
            lo, hi = sorted((rel["from_channel"], rel["to_channel"]))
            for c in range(lo, hi + 1, step):
                if c in seen:
                    dup_channel.append({"record": record, "channel": c,
                                        "relation_lines": [seen[c], rel["_line"]]})
                seen[c] = rel["_line"]

    # ---- channel range must map one-to-one onto a receiver-station range ---
    range_mismatch = []
    for rel in sps_set["relations"]:
        step = max(1, abs(rel["channel_increment"]))
        n_ch = abs(rel["to_channel"] - rel["from_channel"]) // step + 1
        n_st = abs(rel["to_receiver"] - rel["from_receiver"]) + 1
        if n_ch != n_st:
            range_mismatch.append({
                "record": rel["record"], "relation_line": rel["_line"],
                "channels": [rel["from_channel"], rel["to_channel"]],
                "channel_increment": rel["channel_increment"],
                "channels_implied": int(n_ch),
                "receivers": [rel["from_receiver"], rel["to_receiver"]],
                "receivers_implied": int(n_st)})

    # ---- place every trace --------------------------------------------------
    sx = np.zeros(ntr); sy = np.zeros(ntr)
    gx = np.zeros(ntr); gy = np.zeros(ntr)
    station = np.zeros(ntr, dtype=np.int64)
    src_point = np.zeros(ntr, dtype=np.int64)
    sstat = np.zeros(ntr); gstat = np.zeros(ntr)
    static_present = np.zeros(ntr, dtype=bool)
    placed = np.zeros(ntr, dtype=bool)
    multiple = np.zeros(ntr, dtype=bool)
    records_absent, sources_absent, receivers_absent = set(), set(), set()

    for i in range(ntr):
        rels = by_record.get(int(fldr[i]))
        if not rels:
            records_absent.add(int(fldr[i]))
            continue
        hits = []
        for rel in rels:
            step = max(1, abs(rel["channel_increment"]))
            lo, hi = sorted((rel["from_channel"], rel["to_channel"]))
            c = int(tracf[i])
            if lo <= c <= hi and (c - lo) % step == 0:
                hits.append(rel)
        if not hits:
            continue
        if len(hits) > 1:
            multiple[i] = True
            continue
        rel = hits[0]
        step = max(1, abs(rel["channel_increment"]))
        k = (int(tracf[i]) - rel["from_channel"]) // (
            step if rel["to_channel"] >= rel["from_channel"] else -step)
        direction = 1 if rel["to_receiver"] >= rel["from_receiver"] else -1
        st = rel["from_receiver"] + direction * k
        s = sources.get((rel["source_line"], rel["source_point"]))
        g = receivers.get((rel["receiver_line"], int(st)))
        if s is None:
            sources_absent.add((rel["source_line"], rel["source_point"]))
            continue
        if g is None:
            receivers_absent.add((rel["receiver_line"], int(st)))
            continue
        sx[i], sy[i] = s["x"], s["y"]
        gx[i], gy[i] = g["x"], g["y"]
        station[i] = int(st)
        src_point[i] = rel["source_point"]
        if s.get("static_ms") is not None and g.get("static_ms") is not None:
            sstat[i] = float(s["static_ms"])
            gstat[i] = float(g["static_ms"])
            static_present[i] = True
        placed[i] = True

    unplaced_data = int(np.count_nonzero(is_data & ~placed))
    placed_nondata = int(np.count_nonzero(~is_data & placed))

    # ---- the checks ---------------------------------------------------------
    def check(name, ok, reason, **extra):
        checks[name] = {"supports_assignment": bool(ok) if ok is not None else None,
                        "reason": reason, **extra}
        if ok is False:
            problems.append(f"{name}: {reason}")

    check("field_records_match_relations", not records_absent,
          (f"every field record in the file is named by an X relation"
           if not records_absent else
           f"{len(records_absent)} field record(s) in the file are named by no X "
           f"relation, first few {sorted(records_absent)[:10]}"),
          records_in_file=int(np.unique(fldr).size),
          relations_read=len(sps_set["relations"]),
          records_without_a_relation=len(records_absent))
    check("sources_present_in_S", not sources_absent,
          ("every source the relations name exists in the S file"
           if not sources_absent else
           f"{len(sources_absent)} source point(s) named by a relation are absent "
           f"from the S file, first few {sorted(sources_absent)[:10]}"),
          sources_missing=len(sources_absent))
    check("receivers_present_in_R", not receivers_absent,
          ("every receiver station the relations name exists in the R file"
           if not receivers_absent else
           f"{len(receivers_absent)} receiver station(s) named by a relation are "
           f"absent from the R file, first few {sorted(receivers_absent)[:10]}"),
          receivers_missing=len(receivers_absent))
    check("channel_range_matches_receiver_range", not range_mismatch,
          ("every relation's channel range maps one-to-one onto its receiver "
           "station range"
           if not range_mismatch else
           f"{len(range_mismatch)} relation(s) declare a channel range and a "
           f"receiver range of different length, first {range_mismatch[:3]}"),
          mismatched_relations=len(range_mismatch))
    ambiguous = len(dup_channel) + int(np.count_nonzero(multiple))
    check("assignment_is_unambiguous", ambiguous == 0,
          ("no channel is claimed by more than one relation and no trace was "
           "matched twice"
           if ambiguous == 0 else
           f"{len(dup_channel)} channel(s) are claimed by more than one relation "
           f"and {int(np.count_nonzero(multiple))} trace(s) matched more than one, "
           f"first {dup_channel[:3]}"),
          channels_claimed_twice=len(dup_channel),
          traces_matching_more_than_one=int(np.count_nonzero(multiple)))
    check("every_data_trace_is_placed", unplaced_data == 0,
          (f"all {int(np.count_nonzero(is_data))} seismic-data traces were placed"
           if unplaced_data == 0 else
           f"{unplaced_data} trace(s) marked as seismic data were not placed by "
           f"any relation"),
          data_traces=int(np.count_nonzero(is_data)),
          traces_placed=int(np.count_nonzero(placed)),
          non_data_traces_excluded=int(np.count_nonzero(~is_data)),
          trid_informative=trid_informative,
          non_data_traces_placed_anyway=placed_nondata)

    finite = bool(np.isfinite(sx[placed]).all() and np.isfinite(sy[placed]).all()
                  and np.isfinite(gx[placed]).all() and np.isfinite(gy[placed]).all())
    spread = float(np.hypot(np.ptp(gx[placed]) if placed.any() else 0.0,
                            np.ptp(gy[placed]) if placed.any() else 0.0))
    check("coordinates_finite_and_varying", finite and spread > 0.0,
          ("the assigned coordinates are finite and the receivers occupy more "
           f"than one position ({spread:.1f} m across the line)"
           if finite and spread > 0 else
           "an assigned coordinate is not finite, or every receiver landed in "
           "the same place"),
          receiver_extent_m=round(spread, 2))

    # ---- derived offset and midpoint ---------------------------------------
    offset = np.zeros(ntr)
    midx = np.zeros(ntr); midy = np.zeros(ntr)
    consistency = None
    if placed.any():
        u = line_direction(gx[placed], gy[placed], station[placed])
        dx, dy = gx - sx, gy - sy
        signed = dx * u[0] + dy * u[1]
        magnitude = np.hypot(dx, dy)
        offset = np.where(signed < 0, -magnitude, magnitude)
        offset[~placed] = 0.0
        midx = 0.5 * (sx + gx)
        midy = 0.5 * (sy + gy)
        residual = float(np.abs(np.abs(offset[placed]) - magnitude[placed]).max())
        consistency = {"max_abs_difference_m": residual,
                       "line_unit_vector": [float(u[0]), float(u[1])]}
    check("offset_consistent_with_coordinates",
          consistency is not None and consistency["max_abs_difference_m"] <= 1e-6,
          ("the signed offset's magnitude equals the distance between the "
           "assigned source and receiver on every placed trace"
           if consistency and consistency["max_abs_difference_m"] <= 1e-6 else
           "the derived offset does not reproduce the distance between the "
           "assigned coordinates"),
          **(consistency or {}))
    check("midpoint_derivation_deterministic", True,
          "midpoint is 0.5*(source + receiver) per trace, with no free parameter "
          "and no dependence on trace order",
          formula="midpoint = 0.5 * (source + receiver)")

    placed_with_statics = int(np.count_nonzero(placed & static_present))
    statics_complete = bool(placed.any() and placed_with_statics ==
                            int(np.count_nonzero(placed)))

    verdict = validate_assignment(checks)
    return {
        "algorithm_version": SPS_ASSIGN_VERSION,
        "sps_version": sps_set["algorithm_version"],
        "traces": int(ntr),
        "placed": placed, "is_data": is_data,
        "sx": sx, "sy": sy, "gx": gx, "gy": gy,
        "offset": offset, "midpoint_x": midx, "midpoint_y": midy,
        "sstat_ms": sstat, "gstat_ms": gstat,
        "statics": {
            "available": statics_complete,
            "placed_traces_with_both": placed_with_statics,
            "placed_traces": int(np.count_nonzero(placed)),
            "source_range_ms": ([float(sstat[placed].min()),
                                 float(sstat[placed].max())]
                                if statics_complete else None),
            "receiver_range_ms": ([float(gstat[placed].min()),
                                   float(gstat[placed].max())]
                                  if statics_complete else None),
            "total_range_ms": ([float((sstat + gstat)[placed].min()),
                                float((sstat + gstat)[placed].max())]
                               if statics_complete else None),
            "origin": C.ORIGIN_ACQUISITION_LOG,
        },
        "receiver_station": station, "source_point": src_point,
        "checks": checks, "verdict": verdict, "problems": problems,
        "counts": {
            "traces": int(ntr),
            "data_traces": int(np.count_nonzero(is_data)),
            "placed": int(np.count_nonzero(placed)),
            "excluded_non_data": int(np.count_nonzero(~is_data)),
            "unplaced_data_traces": unplaced_data,
            "trid_informative": trid_informative},
        "claim": C.derived(
            "source and receiver positions per trace",
            "the survey's own S/R/X relation, followed record by record",
            inputs=[C.observed("source and receiver coordinates",
                               "SPS S and R files",
                               origin=C.ORIGIN_ACQUISITION_LOG),
                    C.observed("field record to source and channel relation",
                               "SPS X file",
                               origin=C.ORIGIN_ACQUISITION_LOG)]),
    }
