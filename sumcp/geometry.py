"""Geometry: what the coordinate headers actually say, and what they don't."""

from __future__ import annotations

import numpy as np

from . import claims as C
from . import leverage as LEV
from . import sufile

__all__ = [
    "GEOMETRY_VERSION", "COUNIT_NAMES", "resolve_coordinates",
    "detect_sort", "receiver_variation", "offset_state", "cdp_state", "CDP_ABSENT",
    "CDP_PRESENT", "CDP_PLAUSIBLE", "CDP_IMPLAUSIBLE",
]

GEOMETRY_VERSION = "geometry-0.7"

# SEG-Y coordinate units (trace header word `counit`).
COUNIT_NAMES = {
    1: "length (metres or feet)",
    2: "seconds of arc",
    3: "decimal degrees",
    4: "degrees, minutes, seconds",
}

CDP_ABSENT = "ABSENT"
CDP_PRESENT = "PRESENT"
CDP_PLAUSIBLE = "PLAUSIBLE"
CDP_IMPLAUSIBLE = "IMPLAUSIBLE"

COORD_KEYS = ("sx", "sy", "gx", "gy", "scalco", "counit", "fldr", "tracf", "cdp", "offset")


def _apply_scalco(values: np.ndarray, scalco: np.ndarray) -> np.ndarray:
    """SEG-Y scalco: positive multiplies, negative divides, 0 and 1 leave as is."""
    out = values.astype(np.float64)
    s = scalco.astype(np.float64)
    positive = s > 1
    negative = s < -1
    out[positive] = out[positive] * s[positive]
    out[negative] = out[negative] / np.abs(s[negative])
    return out


def _describe_range(a: np.ndarray) -> dict:
    return {"min": float(a.min()), "max": float(a.max()),
            "span": float(a.max() - a.min()), "n_unique": int(np.unique(a).size)}


def resolve_coordinates(path, geom: dict | None = None) -> dict:
    """Read the coordinate headers and apply scalco; report what the units are."""
    geom = geom or sufile.geometry(path)
    cols = sufile.read_header_columns(path, list(COORD_KEYS), geom)
    scalco = cols["scalco"]
    counit = cols["counit"]

    scaled = {k: _apply_scalco(cols[k], scalco) for k in ("sx", "sy", "gx", "gy")}

    scalco_values = sorted(set(int(v) for v in np.unique(scalco)))
    counit_values = sorted(set(int(v) for v in np.unique(counit)))
    notes = []

    if len(scalco_values) > 1:
        notes.append(f"scalco is not constant ({scalco_values}); each trace was scaled "
                     "by its own value.")
    if scalco_values == [0]:
        notes.append("scalco is 0: coordinates are taken as written, unscaled.")
    elif any(v < 0 for v in scalco_values):
        notes.append(f"scalco {scalco_values} is negative, so coordinates were divided "
                     f"by {abs(scalco_values[0])}.")

    unit_known = counit_values == [1]
    names = [COUNIT_NAMES.get(v, f"unknown code {v}") for v in counit_values]

    # counit is a header field like any other, so it gets checked rather than believed, but NOT against the offset
    # header.
    angular = _angular_plausibility(scaled, counit_values)

    # Kept as corroboration and reported as such. It is not what decides.
    header_offset = cols["offset"].astype(np.float64)
    distance = np.hypot(scaled["gx"] - scaled["sx"], scaled["gy"] - scaled["sy"])
    unit_evidence = {
        "decided_by": "coordinate magnitudes against the range the stated "
                      "counit allows; the offset header is not consulted",
        "angular_plausibility": angular,
    }
    if np.unique(header_offset).size > 1 and float(np.median(distance)) > 0:
        relative = float(np.median(np.abs(np.abs(header_offset) - distance))
                         / max(1.0, float(np.median(distance))))
        unit_evidence.update({
            "offset_header_varies": True,
            "relative_median_difference": relative,
            "offset_header_corroborates": bool(relative < 0.02),
            "corroboration_role": "reported only; the units decision does not use it",
        })
    else:
        unit_evidence.update({"offset_header_varies": False,
                              "offset_header_corroborates": None})

    if not unit_known and angular["impossible_as_angles"]:
        notes.append(
            f"counit is {counit_values} ({', '.join(names)}), but the coordinates run to "
            f"{angular['max_abs']:.0f}, outside the +/-{angular['limit']:.0f} that unit "
            "allows. They cannot be angles, so they are lengths and counit is wrong.")
        unit_known = True
    elif counit_values == [0]:
        notes.append("counit is 0: the coordinate units are not stated in the headers.")
        if angular["impossible_as_angles"]:
            notes.append(
                f"The coordinates run to {angular['max_abs']:.0f}, too large for any "
                "angular unit, so they are lengths even though counit does not say so.")
            unit_known = True
    elif not unit_known:
        notes.append(f"counit is {counit_values} ({', '.join(names)}): these coordinates "
                     "are within the range that unit allows, and nothing independent of "
                     "the offset header contradicts it.")

    span = max(scaled["sx"].max() - scaled["sx"].min(),
               scaled["sy"].max() - scaled["sy"].min())
    magnitude = float(np.median(np.abs(scaled["sx"])))
    if unit_known and 1e5 <= magnitude <= 1e7:
        shape = "projected grid (UTM-like magnitudes)"
    elif unit_known and magnitude < 1e5:
        shape = "local grid or small projected coordinates"
    elif counit_values in ([3], [4], [2]):
        shape = "geographic"
    else:
        shape = "indeterminate"

    return {
        "algorithm_version": GEOMETRY_VERSION,
        "scalco_values": scalco_values,
        "counit_values": counit_values,
        "counit_meaning": [COUNIT_NAMES.get(v, f"unknown code {v}") for v in counit_values],
        "units_are_lengths": unit_known,
        "counit_says_lengths": counit_values == [1],
        "unit_evidence": unit_evidence,
        "coordinate_shape": shape,
        "source": {k: _describe_range(scaled[k]) for k in ("sx", "sy")},
        "receiver": {k: _describe_range(scaled[k]) for k in ("gx", "gy")},
        "line_span_m": float(span) if unit_known else None,
        "notes": notes,
        "_scaled": scaled,
        "_raw": cols,
    }


# The largest magnitude each angular counit code can legitimately carry.
_ANGULAR_LIMITS = {
    2: 648000.0,      # arcseconds:      180 * 3600
    3: 180.0,         # decimal degrees
    4: 1800000.0,     # packed DDDMMSS.ss
}


def _angular_plausibility(scaled: dict, counit_values: list) -> dict:
    """Could these coordinates be the angular unit counit claims?"""
    values = np.concatenate([np.abs(scaled[k]) for k in ("sx", "sy", "gx", "gy")])
    finite = values[np.isfinite(values)]
    max_abs = float(finite.max()) if finite.size else 0.0
    limits = [_ANGULAR_LIMITS[v] for v in counit_values if v in _ANGULAR_LIMITS]
    limit = min(limits) if limits else None
    return {
        "max_abs": max_abs,
        "limit": limit,
        "unit_is_angular": bool(limits),
        "impossible_as_angles": bool(limit is not None and max_abs > limit),
    }

def detect_sort(resolved: dict) -> dict:
    """Is this file shot-ordered, CDP-ordered, or neither?"""
    raw = resolved["_raw"]
    cdp, fldr = raw["cdp"], raw["fldr"]
    cdp_sorted = bool(np.unique(cdp).size > 1 and np.all(np.diff(cdp) >= 0))
    shot_sorted = bool(np.unique(fldr).size > 1 and np.all(np.diff(fldr) >= 0))

    # Fold decides the ambiguous case.
    fold = 0
    if np.unique(cdp).size > 1:
        counts = np.bincount((cdp - cdp.min()).astype(int))
        fold = int(np.median(counts[counts > 0]))

    if cdp_sorted and not shot_sorted:
        kind = "cdp"
    elif shot_sorted and not cdp_sorted:
        kind = "shot"
    elif shot_sorted and cdp_sorted:
        kind = "cdp" if fold > 1 else "shot"
    else:
        kind = "unsorted"
    return {"kind": kind, "cdp_monotonic": cdp_sorted, "fldr_monotonic": shot_sorted,
            "median_traces_per_cdp": fold}


def receiver_variation(resolved: dict) -> dict:
    """Does each channel's receiver position change from shot to shot?"""
    raw = resolved["_raw"]
    gx, gy = resolved["_scaled"]["gx"], resolved["_scaled"]["gy"]
    tracf, fldr = raw["tracf"], raw["fldr"]

    channels = np.unique(tracf)
    per_channel = []
    for ch in channels:
        sel = tracf == ch
        pts = np.stack([gx[sel], gy[sel]], axis=1)
        uniq = np.unique(np.round(pts, 3), axis=0)
        spread = 0.0
        if uniq.shape[0] > 1:
            spread = float(np.hypot(pts[:, 0].max() - pts[:, 0].min(),
                                    pts[:, 1].max() - pts[:, 1].min()))
        per_channel.append({"channel": int(ch), "n_shots": int(sel.sum()),
                            "n_distinct_positions": int(uniq.shape[0]),
                            "position_spread_m": spread})

    distinct = np.array([c["n_distinct_positions"] for c in per_channel])
    n_shots = int(np.unique(fldr).size)
    varies = bool((distinct > 1).all())
    fixed = bool((distinct == 1).all())

    # Three states, not two.
    every_coordinate_zero = bool(np.all(gx == 0) and np.all(gy == 0))
    if every_coordinate_zero:
        coordinate_state = RX_ABSENT
    elif varies:
        coordinate_state = RX_VARYING
    elif fixed:
        coordinate_state = RX_STATIC
    else:
        coordinate_state = RX_MIXED

    # Receiver spacing from the distinct positions themselves, so the answer does not depend on how the file
    # happens to be sorted.
    positions = np.unique(np.round(np.stack([gx, gy], axis=1), 3), axis=0)
    order = np.lexsort((positions[:, 1], positions[:, 0]))
    positions = positions[order]
    steps = np.hypot(np.diff(positions[:, 0]), np.diff(positions[:, 1]))
    spacing = float(np.median(steps)) if steps.size else None
    extent = (float(np.hypot(positions[-1, 0] - positions[0, 0],
                             positions[-1, 1] - positions[0, 1]))
              if positions.shape[0] > 1 else 0.0)

    sort = detect_sort(resolved)
    array_length = None
    if sort["kind"] == "shot":
        first = np.unique(fldr)[0]
        sel = fldr == first
        ordering = np.argsort(tracf[sel])
        px, py = gx[sel][ordering], gy[sel][ordering]
        if px.size > 1:
            array_length = float(np.hypot(px[-1] - px[0], py[-1] - py[0]))

    # The plain keys below stay plain numbers so existing readers keep working; the claims block says what each
    # one IS.
    coordinates = C.observed(
        "gx/gy after scalco", "SU trace headers",
        note="scalco applied; counit checked by resolve_coordinates")
    claims = {
        "channel_spacing_m": (
            C.derived(spacing, "median step between distinct receiver positions",
                      inputs=[coordinates])
            if spacing is not None else
            C.hypothesized(None, "no distinct receiver positions to step between")),
        "receiver_extent_m": C.derived(
            extent, "distance between the outermost distinct positions",
            inputs=[coordinates]),
        "array_length_m": (
            C.derived(array_length, "first shot's channel 1 to channel N",
                      inputs=[coordinates])
            if array_length is not None else
            C.hypothesized(None, "the file is not shot-sorted")),
    }

    return {
        "algorithm_version": GEOMETRY_VERSION,
        "claims": claims,
        "receiver_coordinate_state": coordinate_state,
        "receiver_coordinate_state_note": RX_STATE_NOTES[coordinate_state],
        "trace_sort": sort,
        "receiver_positions": int(positions.shape[0]),
        "receiver_extent_m": extent,
        "n_shots": n_shots,
        "n_channels": int(channels.size),
        "every_channel_moves": varies,
        "every_channel_fixed": fixed,
        "distinct_positions_per_channel": {"min": int(distinct.min()),
                                           "max": int(distinct.max())},
        "channel_spacing_m": spacing,
        "channel_spacing_source": "median step between distinct receiver positions",
        "array_length_m": array_length,
        "array_length_note": (None if sort["kind"] == "shot" else
                              "Not computed: the file is " + sort["kind"] +
                              "-sorted, so one fldr is not a contiguous receiver array."),
        "per_channel_sample": per_channel[:3] + per_channel[-1:],
    }


def offset_state(resolved: dict) -> dict:
    """Compare the offset header with the offset the coordinates imply."""
    raw = resolved["_raw"]
    s = resolved["_scaled"]
    header = raw["offset"].astype(np.float64)
    computed = np.hypot(s["gx"] - s["sx"], s["gy"] - s["sy"])

    if np.all(header == 0):
        state = "zero"
    elif np.unique(header).size == 1:
        state = "constant"
    else:
        state = "varying"

    report = {
        "algorithm_version": GEOMETRY_VERSION,
        "header_state": state,
        "header": _describe_range(header),
        "computed_from_coordinates": _describe_range(computed),
    }
    if state == "varying":
        # The SEG-Y offset word is signed (negative behind the source) while a distance is not, so the magnitudes
        # are what must agree.
        diff = np.abs(header) - computed
        scale = max(1.0, float(np.median(computed)))
        report["difference"] = {
            "compared": "abs(header offset) against distance from coordinates",
            "median_abs_m": float(np.median(np.abs(diff))),
            "max_abs_m": float(np.abs(diff).max()),
            "relative_median": float(np.median(np.abs(diff)) / scale),
        }
        report["signed_header"] = bool((header < 0).any())
        report["agrees"] = bool(report["difference"]["relative_median"]
                                < HEADER_AGREEMENT_RELATIVE)
    else:
        report["agrees"] = None
        report["note"] = ("The offset header carries no information; offsets must come "
                          "from the coordinates or from a measurement.")
    return report


# --------------------------------------------------------------------------- Which offset the processing may
# use,------------------------------------------------------------------------- The relative-median difference
# below which a header and the coordinates are taken to say the same thing.
HEADER_AGREEMENT_RELATIVE = 0.02

OFFSET_FROM_HEADER = "TRACE_HEADERS"
OFFSET_FROM_COORDINATES = "DERIVED_FROM_COORDINATES"


def coordinate_offset_authority(resolved: dict, variation: dict,
                                classification: dict) -> dict:
    """May the coordinates be used to compute offsets in their own right?"""
    source_ok = resolved["source"]["sx"]["n_unique"] > 1
    receiver_ok = resolved["receiver"]["gx"]["n_unique"] > 1
    units_ok = bool(resolved["units_are_lengths"])
    scalco_ok = all(v == 0 or abs(v) in (1, 10, 100, 1000, 10000)
                    for v in resolved["scalco_values"])
    geometry_ok = classification_status(classification) is True
    spread_ok = bool(variation.get("receiver_extent_m") or 0) > 0

    checks = {
        "source_coordinates_vary": source_ok,
        "receiver_coordinates_vary": receiver_ok,
        "units_resolved_as_lengths": units_ok,
        "scalco_interpretable": scalco_ok,
        "acquisition_geometry_coherent": geometry_ok,
        "receiver_positions_spread": spread_ok,
    }
    failed = [k for k, v in checks.items() if not v]
    return {
        "algorithm_version": GEOMETRY_VERSION,
        "trustworthy": not failed,
        "checks": checks,
        "failed": failed,
        "independent_of": "the offset header",
        "reason": ("The coordinates stand on their own: they vary, their scale and "
                   "units are resolved, and the acquisition they describe is coherent."
                   if not failed else
                   "The coordinates cannot be used as an independent offset source: "
                   + ", ".join(failed)),
    }


def processing_offset(offsets: dict, authority: dict) -> dict:
    """Decide the canonical offset for processing, and say where it came from."""
    header_usable = offsets.get("agrees") is True
    trusted = bool(authority["trustworthy"])

    if header_usable:
        return {
            "algorithm_version": GEOMETRY_VERSION,
            "resolved": True,
            "origin": OFFSET_FROM_HEADER,
            "repair_required": False,
            "header_state": offsets["header_state"],
            "header_agrees": True,
            "coordinate_authority": authority,
            "reason": "The offset header agrees with the coordinates to "
                      f"{offsets['difference']['relative_median'] * 100:.2f}%, "
                      "so it is used as written.",
        }
    if trusted:
        why = ("the offset header carries no information"
               if offsets["header_state"] in ("zero", "constant")
               else "the offset header disagrees with the coordinates by "
                    f"{offsets['difference']['relative_median'] * 100:.1f}%")
        return {
            "algorithm_version": GEOMETRY_VERSION,
            "resolved": True,
            "origin": OFFSET_FROM_COORDINATES,
            "repair_required": True,
            "header_state": offsets["header_state"],
            "header_agrees": offsets.get("agrees"),
            "coordinate_authority": authority,
            "reason": f"The header is rejected because {why}. The coordinates are "
                      "trustworthy on evidence that does not involve the offset "
                      "header, so the offset is recomputed from them and written "
                      "into the processing copy. The imported file is unchanged.",
        }
    return {
        "algorithm_version": GEOMETRY_VERSION,
        "resolved": False,
        "origin": None,
        "repair_required": False,
        "header_state": offsets["header_state"],
        "header_agrees": offsets.get("agrees"),
        "coordinate_authority": authority,
        "reason": "There is no offset this survey may be processed with: the header "
                  "is not usable and " + authority["reason"][0].lower()
                  + authority["reason"][1:],
    }


def cdp_state(resolved: dict) -> dict:
    """Three-level CDP check: ABSENT -> PRESENT -> PLAUSIBLE."""
    raw = resolved["_raw"]
    s = resolved["_scaled"]
    cdp = raw["cdp"]
    out = {"algorithm_version": GEOMETRY_VERSION}

    if np.all(cdp == 0) or np.unique(cdp).size == 1:
        out["level"] = CDP_ABSENT
        out["reason"] = ("cdp is zero or constant, so no CMP numbering exists in the "
                         "headers.")
        return out

    mx = 0.5 * (s["sx"] + s["gx"])
    my = 0.5 * (s["sy"] + s["gy"])

    bins = np.unique(cdp)
    spreads, centres = [], []
    for b in bins:
        sel = cdp == b
        bx, by = mx[sel], my[sel]
        spreads.append(float(np.hypot(bx.max() - bx.min(), by.max() - by.min())))
        centres.append((float(bx.mean()), float(by.mean())))
    spreads = np.array(spreads)
    centres = np.array(centres)

    order = np.argsort(bins)
    step = np.hypot(*np.diff(centres[order], axis=0).T) if bins.size > 1 else np.array([0.0])
    bin_step = float(np.median(step)) if step.size else 0.0
    median_spread = float(np.median(spreads))
    ratio = median_spread / bin_step if bin_step > 0 else float("inf")

    out.update({
        "n_bins": int(bins.size),
        "cdp_range": [int(bins.min()), int(bins.max())],
        "traces_per_bin": {"min": int(np.bincount(
            (cdp - cdp.min()).astype(int))[np.bincount((cdp - cdp.min()).astype(int)) > 0].min()),
            "max": int(np.bincount((cdp - cdp.min()).astype(int)).max())},
        "midpoint_spread_per_bin_m": {"median": median_spread,
                                      "max": float(spreads.max())},
        "spacing_between_bin_centres_m": bin_step,
        "spread_over_spacing": ratio,
    })
    # A real bin holds midpoints within roughly one bin width.
    if ratio <= 2.0:
        out["level"] = CDP_PLAUSIBLE
        out["reason"] = (f"Midpoints inside a bin spread {median_spread:.1f} m, "
                         f"comparable to the {bin_step:.1f} m between bin centres.")
    else:
        out["level"] = CDP_IMPLAUSIBLE
        out["reason"] = (f"Midpoints inside a bin spread {median_spread:.1f} m, "
                         f"{ratio:.0f} times the {bin_step:.1f} m between bin centres. "
                         "The cdp header is populated but is not a CMP binning.")
    return out


# How well the evidence separates the candidates.
RX_ABSENT = "ABSENT"       # gx and gy are zero on every trace
RX_STATIC = "STATIC"       # each channel holds one position for the whole line
RX_VARYING = "VARYING"     # every channel moves from shot to shot
RX_MIXED = "MIXED"         # some move and some do not; internally inconsistent

RX_STATE_NOTES = {
    RX_ABSENT: ("gx and gy are zero on every trace. The headers carry no "
                "receiver geometry at all -- which is not the same as "
                "receivers that did not move, and nothing about the "
                "acquisition can be classified from it. Geometry has to come "
                "from outside the file."),
    RX_STATIC: ("Each channel holds one position for the whole line. Either a "
                "real fixed deployment or one record's positions copied into "
                "every trace; only an arrival-time measurement separates them."),
    RX_VARYING: ("Every channel occupies a different position at every shot, "
                 "as a towed or otherwise moving spread does."),
    RX_MIXED: ("Some channels move between shots and some do not; the receiver "
               "headers are internally inconsistent."),
}

ACQ_ESTABLISHED = "ESTABLISHED"
ACQ_PROBABLE = "PROBABLE"
ACQ_STATUS_UNKNOWN = "UNKNOWN"

ACQ_MOVING_RECEIVERS = "moving_receivers"
ACQ_FIXED_ARRAY = "fixed_receiver_array"
ACQ_RECEIVERS_UNTRUSTWORTHY = "receiver_headers_untrustworthy"
ACQ_UNDETERMINED = "undetermined"


def classify_acquisition(variation: dict, trend: dict | None = None,
                         velocity_check: dict | None = None,
                         tracking: dict | None = None) -> dict:
    """Name the acquisition geometry, and say what the evidence does not settle."""
    facts = {
        "receiver_coordinate_state": variation.get("receiver_coordinate_state"),
        "receivers_move_with_shot": variation["every_channel_moves"],
        "receivers_fixed": variation["every_channel_fixed"],
        "n_shots": variation["n_shots"],
        "n_channels": variation["n_channels"],
        "channel_spacing_m": variation["channel_spacing_m"],
        "array_length_m": variation["array_length_m"],
        "trace_sort": variation.get("trace_sort", {}).get("kind"),
    }
    unresolved = []
    status = ACQ_ESTABLISHED

    state = variation.get("receiver_coordinate_state")
    if state is None:
        # a caller from before the three-way state existed, or a stored variation dict read back out of an older
        # manifest
        state = (RX_VARYING if variation.get("every_channel_moves") else
                 RX_STATIC if variation.get("every_channel_fixed") else RX_MIXED)
    if state == RX_ABSENT:
        kind = ACQ_UNDETERMINED
        status = ACQ_STATUS_UNKNOWN
        reason = RX_STATE_NOTES[RX_ABSENT]
        unresolved.append(
            "Supply the acquisition geometry from outside the file -- the "
            "observer log and the shotpoint navigation -- and assign it before "
            "asking what the acquisition was.")
    elif variation["n_shots"] < 2:
        kind = ACQ_UNDETERMINED
        status = ACQ_STATUS_UNKNOWN
        reason = "Only one shot is present; receiver motion cannot be tested."
    elif variation["every_channel_moves"]:
        kind = ACQ_MOVING_RECEIVERS
        reason = ("Every channel occupies a different position at every shot, as a towed "
                  "or otherwise moving spread does.")
    elif variation["every_channel_fixed"]:
        # arrayfit's source-tracking test, when it has an answer, is the stronger evidence: it fits the arrival
        # across the whole array on every shot of the line rather than picking one named record, so it is
        # preferred over the single-ensemble trend when both exist.
        verdict = (tracking or {}).get("verdict")
        if verdict == "TRACKS":
            kind = ACQ_FIXED_ARRAY
            reason = (
                "Each channel holds one position for the whole line, and the "
                "arrival time at the array centre follows the source-to-array "
                f"distance over {tracking.get('shots_used')} shots "
                f"({tracking.get('scale')} of the predicted rate, correlation "
                f"{tracking.get('correlation')}, residual "
                f"{tracking.get('residual_rms_ms')} ms). The positions describe "
                "a real fixed array, not one record copied into the rest.")
            if tracking.get("velocity_note"):
                unresolved.append(tracking["velocity_note"])
        elif verdict == "DOES_NOT_TRACK":
            # Failing the test is not one thing.
            correlation = tracking.get("correlation") or 0.0
            if correlation >= 0.90:
                kind = ACQ_FIXED_ARRAY
                status = ACQ_PROBABLE
                reason = ("Each channel holds one position for the whole line, "
                          f"and the arrival time follows the header distance "
                          f"closely (correlation {correlation:.3f}) but at "
                          f"{tracking.get('scale')} of the predicted rate. The "
                          "positions are most likely real and the arrival timed "
                          "is most likely not the one assumed; neither is "
                          "established.")
                unresolved.append(
                    "Identify the arrival being timed -- the rate implies "
                    f"{tracking.get('implied_velocity_m_s')} m/s -- before the "
                    "classification can be called established.")
            else:
                kind = ACQ_RECEIVERS_UNTRUSTWORTHY
                status = (ACQ_ESTABLISHED if correlation < 0.5 else ACQ_PROBABLE)
                reason = ("Each channel holds one position for the whole line, "
                          "and the arrival time does not follow the "
                          "source-to-array distance those positions imply. "
                          + str(tracking.get("reason", "")))
        elif trend and trend.get("tracks_source_motion"):
            kind = ACQ_FIXED_ARRAY
            reason = (
                "Each channel holds one position for the whole line, and the arrival "
                f"time follows the source-to-array distance "
                f"({trend['measured_ms_per_shot']:.2f} ms/shot measured against "
                f"{trend['predicted_ms_per_shot']:.2f} ms/shot predicted, correlation "
                f"{trend['correlation_with_prediction']:.3f}). The positions describe a "
                "real fixed array, not one record copied into the rest.")
        elif trend:
            kind = ACQ_RECEIVERS_UNTRUSTWORTHY
            reason = (
                "Each channel holds one position for the whole line, and the arrival time "
                "does not follow the source-to-array distance those positions imply. "
                "The receiver coordinates cannot be used to compute offsets.")
        else:
            kind = ACQ_UNDETERMINED
            status = ACQ_STATUS_UNKNOWN
            reason = ("Each channel holds one position for the whole line. This is either a "
                      "fixed array or copied headers; an arrival-time measurement is needed "
                      "to tell which.")
            unresolved.append("Run a shot-to-shot arrival-time trend to separate the two.")
            if verdict:
                unresolved.append(str(tracking.get("reason", "")))
    else:
        kind = ACQ_UNDETERMINED
        status = ACQ_STATUS_UNKNOWN
        reason = ("Some channels move between shots and some do not; the receiver headers "
                  "are internally inconsistent.")

    # `kind` stays the settled name and drives the capability gate, so a PROBABLE classification does not open
    # anything.
    candidate = kind
    if status != ACQ_ESTABLISHED and kind != ACQ_UNDETERMINED:
        kind = ACQ_UNDETERMINED
    report = {"algorithm_version": GEOMETRY_VERSION, "kind": kind,
              "candidate": candidate, "status": status,
              "reason": reason, "facts": facts,
              "receiver_coordinate_state": state,
              "alternatives": ([ACQ_FIXED_ARRAY, ACQ_RECEIVERS_UNTRUSTWORTHY]
                               if state == RX_STATIC else [])}
    if tracking:
        report["source_tracking"] = {k: v for k, v in tracking.items()
                                     if not k.startswith("_")}

    if velocity_check:
        report["apparent_velocity"] = {
            "measured_m_s": velocity_check.get("apparent_velocity_m_s"),
            "predicted_m_s": velocity_check.get("predicted_velocity_m_s"),
            "matches_prediction": velocity_check.get("matches_prediction"),
        }
        if velocity_check.get("matches_prediction") is False:
            unresolved.append(
                "The measured apparent velocity "
                f"({velocity_check.get('apparent_velocity_m_s', float('nan')):.0f} m/s) "
                "differs from what the coordinates predict for a water-speed arrival "
                f"({velocity_check.get('predicted_velocity_m_s', float('nan')):.0f} m/s), "
                "so the event measured is not the direct water wave. Which arrival it is "
                "has not been established.")

    if candidate == ACQ_FIXED_ARRAY:
        unresolved.append(
            "A fixed array with a moving source is not a towed-streamer geometry; "
            "streamer CMP assumptions do not carry over and the processing goal has to "
            "be decided before CMP work.")
    report["unresolved"] = unresolved
    return report


def classification_status(classification: dict):
    """PASS / FAIL / UNKNOWN for a classification, as True / False / None."""
    kind = classification.get("kind")
    if kind == ACQ_RECEIVERS_UNTRUSTWORTHY:
        return False
    if kind == ACQ_UNDETERMINED:
        return None
    return True


def _moveout_spread_s(x_min: float, x_max: float, velocity: float,
                      t_zero: float) -> float:
    """Delegates to sumcp.leverage so there is one formula in the package."""
    return LEV.moveout_spread_s(x_min, x_max, velocity, t_zero)


def _leverage_report(offset_sq_range, moveout_s, velocity, t_zero,
                     sample_interval_s, fold_median, multi_trace_fraction):
    """How much moveout a typical bin actually holds, in time."""
    samples = (moveout_s / sample_interval_s) if sample_interval_s else None
    # Read only over bins that hold more than one trace, and if almost none do, that median describes a handful of
    # accidents, not the survey.
    reason = None
    if fold_median < 2 or multi_trace_fraction < 0.5:
        verdict = "NONE"
        reason = (f"a typical bin holds {fold_median} trace(s) and only "
                  f"{multi_trace_fraction:.0%} of bins hold more than one, so "
                  f"there is no gather to read moveout from; the spread quoted "
                  f"below is over the few bins that do")
    elif moveout_s < 0.002:
        verdict = "NONE"
        reason = "the traces in a bin are at effectively one moveout"
    elif moveout_s < 0.020:
        verdict = "MARGINAL"
    else:
        verdict = "USABLE"
    out = {
        "verdict": verdict,
        "algorithm_version": LEV.LEVERAGE_VERSION,
        "form": "single_hyperbola",
        "fold_median": int(fold_median),
        "bins_with_more_than_one_trace": round(multi_trace_fraction, 3),
        "moveout_spread_ms": round(moveout_s * 1000.0, 2),
        "median_offset_sq_range_m2": round(offset_sq_range, 1),
        "reference": C.assumed(
            {"velocity_m_s": velocity, "t0_s": t_zero},
            "caller or default; no velocity is established yet"),
        # The verdict below is computed from that reference, so it is no stronger than it: a bin graded USABLE at
        # 1800 m/s is graded on an assumption, and inherits ASSUMED rather than DERIVED.
        "claims": {"moveout_spread_ms": C.derived(
            round(moveout_s * 1000.0, 2),
            "traveltime across the reference hyperbola over the bin's offsets",
            inputs=[C.assumed(velocity, "reference velocity")])},
        "why": ("Traveltime difference a typical bin sees across the reference "
                "hyperbola. NONE means fold without leverage: the traces in a "
                "bin are at effectively one moveout, so no velocity can be read "
                "from them and stacking only averages noise."),
    }
    if reason:
        out["reason"] = reason
    if samples is not None:
        out["moveout_spread_samples"] = round(samples, 1)
    return out


def assign_cmp(resolved: dict, bin_size_m: float | None = None,
               receiver_spacing_m: float | None = None,
               reference_velocity_m_s: float = 1800.0,
               reference_t0_s: float = 1.0,
               sample_interval_s: float | None = None) -> dict:
    """Compute CMP bin numbers from the coordinates."""
    s = resolved["_scaled"]
    mx = 0.5 * (s["sx"] + s["gx"])
    my = 0.5 * (s["sy"] + s["gy"])

    centre = np.array([mx.mean(), my.mean()])
    cloud = np.stack([mx - centre[0], my - centre[1]], axis=1)
    # principal direction of the midpoint cloud = the line
    _, _, vectors = np.linalg.svd(cloud, full_matrices=False)
    direction = vectors[0]
    if direction[0] < 0 or (direction[0] == 0 and direction[1] < 0):
        direction = -direction               # a stable sign, so bins count one way
    along = cloud @ direction
    across = cloud @ np.array([-direction[1], direction[0]])

    if bin_size_m is None:
        if receiver_spacing_m:
            bin_size_m = receiver_spacing_m / 2.0      # the usual CMP interval
        else:
            steps = np.diff(np.unique(np.round(along, 3)))
            bin_size_m = float(np.median(steps)) if steps.size else 1.0
    bin_size_m = float(bin_size_m)
    if bin_size_m <= 0:
        raise ValueError("bin_size_m must be positive.")

    cdp = np.floor((along - along.min()) / bin_size_m).astype(np.int64) + 1
    counts = np.bincount(cdp)[1:]
    occupied = counts[counts > 0]

    fold = {"min": int(occupied.min()), "max": int(occupied.max()),
            "median": int(np.median(occupied)), "mean": float(occupied.mean()),
            "n_bins_occupied": int(occupied.size),
            "n_bins_spanned": int(cdp.max()),
            "empty_bins": int(cdp.max() - occupied.size)}

    offsets = np.hypot(s["gx"] - s["sx"], s["gy"] - s["sy"])
    # Fold alone does not make a CMP gather useful: its traces also have to carry different moveout, or there is
    # nothing for a velocity scan to read and nothing for stacking to add beyond averaging noise.
    spans, leverage, moveout = [], [], []
    total_span = float(offsets.max() - offsets.min())
    for b in np.unique(cdp):
        o = offsets[cdp == b]
        if o.size > 1:
            spans.append(float(o.max() - o.min()))
            leverage.append(float((o ** 2).max() - (o ** 2).min()))
            moveout.append(_moveout_spread_s(float(o.min()), float(o.max()),
                                             reference_velocity_m_s,
                                             reference_t0_s))
    median_span = float(np.median(spans)) if spans else 0.0
    offset_diversity = median_span / total_span if total_span > 0 else 0.0
    median_leverage = float(np.median(leverage)) if leverage else 0.0
    median_moveout = float(np.median(moveout)) if moveout else 0.0

    return {
        "algorithm_version": GEOMETRY_VERSION,
        "bin_size_m": bin_size_m,
        "bin_size_source": ("given" if receiver_spacing_m is None and bin_size_m else
                            "half the receiver spacing"),
        "line_direction": [float(direction[0]), float(direction[1])],
        "line_length_m": float(along.max() - along.min()),
        "crookedness_rms_m": float(np.sqrt((across ** 2).mean())),
        "crookedness_max_m": float(np.abs(across).max()),
        "fold": fold,
        "offset_range_m": [float(offsets.min()), float(offsets.max())],
        "aperture": LEV.aperture(offsets),
        "offset_span_per_bin_m": {"median": median_span,
                                  "max": float(max(spans)) if spans else 0.0},
        "nmo_leverage": _leverage_report(
            median_leverage, median_moveout, reference_velocity_m_s,
            reference_t0_s, sample_interval_s, fold["median"],
            len(spans) / max(1, occupied.size)),
        "offset_diversity": offset_diversity,
        "cdp": cdp,
    }
