"""Geometry analysis for a registered dataset."""

from __future__ import annotations

import json

import numpy as np

from . import claims as C
from . import (config, evidence, external, geometry, measure, provenance,
               sps, sufile)
from .paths import as_rel, safe_input_path, safe_output_path

__all__ = ["analyze_geometry", "inspect_external_geometry",
           "assign_external_geometry", "EXTERNAL_SU_ROLE"]


def _set(manifest, name, ok, evidence_dict, run_id, notes=(), artifact=None):
    status = {True: evidence.PASS, False: evidence.FAIL, None: evidence.UNKNOWN}[ok]
    return evidence.set_capability(manifest, name, status, evidence_dict,
                                   geometry.GEOMETRY_VERSION, run_id,
                                   artifact=artifact, notes=list(notes))


def _source_distance_by_shot(resolved) -> dict:
    s, raw = resolved["_scaled"], resolved["_raw"]
    out = {}
    for shot in np.unique(raw["fldr"]):
        sel = raw["fldr"] == shot
        out[int(shot)] = float(np.median(np.hypot(s["gx"][sel] - s["sx"][sel],
                                                  s["gy"][sel] - s["sy"][sel])))
    return out


def _array_ray_angles(resolved) -> list | None:
    """Range of the angle between the receiver array axis and the incoming ray."""
    raw, s = resolved["_raw"], resolved["_scaled"]
    shots = np.unique(raw["fldr"])
    first = raw["fldr"] == shots[0]
    order = np.argsort(raw["tracf"][first])
    gx, gy = s["gx"][first][order], s["gy"][first][order]
    if gx.size < 2:
        return None
    axis = np.array([gx[-1] - gx[0], gy[-1] - gy[0]])
    axis_len = float(np.hypot(*axis))
    if axis_len <= 0:
        return None
    angles = []
    for shot in shots:
        sel = raw["fldr"] == shot
        ray = np.array([gx[0] - s["sx"][sel][0], gy[0] - s["sy"][sel][0]])
        ray_len = float(np.hypot(*ray))
        if ray_len <= 0:
            continue
        cos = abs(float(axis @ ray)) / (axis_len * ray_len)
        angles.append(float(np.degrees(np.arccos(min(1.0, cos)))))
    return [min(angles), max(angles)] if angles else None


SPLIT_SPREAD_SIDE = 0.1


def is_split_spread(dist_by_channel) -> bool:
    """v0.33 G3: the source sits inside the spread, the source-receiver distance, in channel order, reaches its
    minimum with at least 10% of the channels on each side."""
    d = np.asarray(dist_by_channel, dtype=float)
    if d.size < 3:
        return False
    k = int(np.argmin(d))
    side = SPLIT_SPREAD_SIDE * d.size
    return bool(k >= side and d.size - 1 - k >= side)


def analyze_geometry(dataset_id: str, *, measure_fldr=None, measure_tmin=None,
                     measure_tmax=None, trend_shots: int = 20,
                     water_velocity: float = measure.WATER_VELOCITY) -> dict:
    """Resolve coordinates, test the receiver headers, and classify the geometry."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["dataset.imported", "headers.parsed"],
                     "Geometry analysis")

    su_path = safe_input_path(evidence.processing_su(manifest)["path"])
    geom = sufile.geometry(su_path)

    resolved = geometry.resolve_coordinates(su_path, geom)
    variation = geometry.receiver_variation(resolved)
    offsets = geometry.offset_state(resolved)
    cdp = geometry.cdp_state(resolved)

    velocity_check = trend = None
    if measure_fldr is not None and measure_tmin is not None and measure_tmax is not None:
        raw, scaled = resolved["_raw"], resolved["_scaled"]
        sel = raw["fldr"] == int(measure_fldr)
        order = np.argsort(raw["tracf"][sel])
        dist = np.hypot(scaled["gx"][sel] - scaled["sx"][sel],
                        scaled["gy"][sel] - scaled["sy"][sel])[order]
        predicted_slope = float(np.median(np.diff(dist / water_velocity)) * 1000)
        velocity_check = measure.apparent_velocity(
            su_path, fldr=int(measure_fldr), tmin=measure_tmin, tmax=measure_tmax,
            geom=geom, channel_spacing_m=variation["channel_spacing_m"],
            predicted_slope_ms=predicted_slope,
            # measured from the headers here, so the velocity built on it is DERIVED rather than the ASSUMED a
            # bare number would imply
            spacing_claim=variation.get("claims", {}).get("channel_spacing_m"))
        shots = [int(s) for s in np.unique(resolved["_raw"]["fldr"])][:int(trend_shots)]
        if len(shots) >= 3:
            distances = _source_distance_by_shot(resolved)
            spread = (max(distances.values()) - min(distances.values())) / water_velocity
            # If the arrival moves further than the window across the line, a fixed window cannot hold it for
            # every shot; search instead.
            mode = "scan" if spread > (measure_tmax - measure_tmin) else "window"
            trend = measure.arrival_time_trend(
                su_path, shots, tmin=measure_tmin, tmax=measure_tmax,
                slope_ms=velocity_check["slope_ms_per_channel"], geom=geom,
                predicted_distance=distances, velocity=water_velocity,
                pick_mode=mode)

    cross_check = None
    split = velocity_check is not None and is_split_spread(dist)
    if split:
        cross_check = {"status": "NOT_APPLICABLE", "rule": "v0.33 G3",
                       "reason": (f"shot {int(measure_fldr)} is split-spread (the source lies inside "
                                  "the receiver spread); one slope across all channels mixes the two "
                                  "sides' opposite moveouts, so the slope cross-check does not apply "
                                  "and no receiver-spacing verdict is written")}
    elif velocity_check and trend:
        cross_check = measure.cross_check_velocity(
            velocity_check, trend,
            array_ray_angle_range_deg=_array_ray_angles(resolved))

    classification = geometry.classify_acquisition(variation, trend, velocity_check)
    if cross_check and cross_check.get("agrees") is False:
        classification["unresolved"].append(cross_check["reason"])

    # ---- record it all -----------------------------------------------------
    _set(manifest, "geometry.coordinate_scale_resolved",
         resolved["units_are_lengths"],
         {k: resolved[k] for k in ("scalco_values", "counit_values", "counit_meaning",
                                   "coordinate_shape", "units_are_lengths",
                                   "source", "receiver", "line_span_m")},
         run_id, notes=resolved["notes"])

    _set(manifest, "geometry.source_coords_available",
         resolved["source"]["sx"]["n_unique"] > 1, resolved["source"], run_id)
    _set(manifest, "geometry.receiver_coords_available",
         resolved["receiver"]["gx"]["n_unique"] > 1, resolved["receiver"], run_id)

    _set(manifest, "geometry.acquisition_classified",
         geometry.classification_status(classification),
         classification, run_id, notes=[classification["reason"]] + classification["unresolved"])

    if classification["kind"] == geometry.ACQ_MOVING_RECEIVERS:
        trust, trust_note = True, ["Receiver positions change with every shot, as the headers must."]
    elif classification["kind"] == geometry.ACQ_FIXED_ARRAY:
        trust, trust_note = True, [classification["reason"]]
    elif classification["kind"] == geometry.ACQ_RECEIVERS_UNTRUSTWORTHY:
        trust, trust_note = False, [classification["reason"]]
    else:
        trust, trust_note = None, [classification["reason"]]
    _set(manifest, "geometry.receiver_positions_trustworthy", trust,
         {"classification": classification["kind"],
          "variation": variation, "trend": trend}, run_id, notes=trust_note)

    if offsets["header_state"] in ("zero", "constant"):
        off_ok, off_notes = None, [offsets["note"]]
    else:
        off_ok, off_notes = offsets["agrees"], []
        if not offsets["agrees"]:
            off_notes = ["The offset header and the coordinates disagree. Which of them "
                         "is wrong is decided next, by whether the coordinates can "
                         "stand on their own."]
    _set(manifest, "geometry.offset_header_consistent", off_ok, offsets, run_id,
         notes=off_notes)

    # The gate.
    authority = geometry.coordinate_offset_authority(resolved, variation, classification)
    canonical = geometry.processing_offset(offsets, authority)
    _set(manifest, "geometry.processing_offset_resolved", canonical["resolved"],
         canonical, run_id, notes=[canonical["reason"]])

    level = cdp["level"]
    cdp_ok = {geometry.CDP_PLAUSIBLE: True, geometry.CDP_IMPLAUSIBLE: False}.get(level)
    _set(manifest, "geometry.cdp_header_plausible", cdp_ok, cdp, run_id,
         notes=[cdp["reason"]])

    if cross_check is not None and not split:
        _set(manifest, "geometry.receiver_spacing_consistent", cross_check["agrees"],
             cross_check, run_id, notes=[cross_check["reason"]])

    report = {"dataset_id": dataset_id, "coordinates": {
        k: resolved[k] for k in resolved if not k.startswith("_")},
        "receiver_variation": variation, "offsets": offsets,
        "processing_offset": canonical, "cdp": cdp,
        "apparent_velocity": velocity_check, "arrival_time_trend": trend,
        "velocity_cross_check": cross_check, "classification": classification}
    out_dir = config.WORK_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "geometry_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=float),
                    encoding="utf-8")
    evidence.add_artifact(manifest, "geometry_report", path, "report", run_id)
    evidence.save(manifest)

    provenance.record({"run_id": run_id, "kind": "analyze_geometry", "status": "success",
                       "dataset_id": dataset_id, "input": as_rel(su_path),
                       "output": as_rel(path),
                       "classification": classification["kind"],
                       "cdp_level": cdp["level"]})
    return {"run_id": run_id, "report": as_rel(path), **report}


# --------------------------------------------------------------------------- Geometry that is not in the file:
# the standard SPS exchange set,------------------------------------------------------------------------- v0.13.0.

EXTERNAL_SU_ROLE = "geometry"


def _scalco_for(values) -> int:
    """The finest SEG-Y coordinate scalar that keeps every value in an int32."""
    biggest = float(np.max(np.abs(np.asarray(values, float))) or 1.0)
    limit = np.iinfo(np.int32).max
    for scale in (10000, 1000, 100, 10, 1):
        if biggest * scale <= limit:
            return scale
    raise ValueError(f"Coordinates reach {biggest:.1f}; they do not fit a SEG-Y "
                     f"coordinate word even unscaled.")


def _header_comparison(resolved, assign, keep) -> dict:
    """Case 1/2/3 of Phase E: is there header geometry, and does it agree?"""
    s = resolved["_scaled"]
    header_present = bool(np.ptp(s["sx"]) > 0 or np.ptp(s["gx"]) > 0
                          or np.ptp(s["sy"]) > 0 or np.ptp(s["gy"]) > 0)
    out = {"header_geometry_present": header_present,
           "tolerance_relative_median": geometry.HEADER_AGREEMENT_RELATIVE,
           "tolerance_source": "geometry.HEADER_AGREEMENT_RELATIVE, the rule the "
                               "header/coordinate check already uses"}
    if not header_present:
        out.update(case="1_segy_geometry_absent", conflict=False,
                   reason="The SEG-Y carries no source or receiver geometry, so "
                          "there is nothing for the acquisition files to conflict "
                          "with.")
        return out
    sel = np.asarray(keep, bool)
    hdr = np.hypot(s["gx"][sel] - s["sx"][sel], s["gy"][sel] - s["sy"][sel])
    ext = np.hypot(assign["gx"][sel] - assign["sx"][sel],
                   assign["gy"][sel] - assign["sy"][sel])
    scale = max(1.0, float(np.median(ext)) if ext.size else 1.0)
    rel = float(np.median(np.abs(hdr - ext)) / scale) if ext.size else float("inf")
    out.update(compared="source-receiver distance per trace, header against "
                        "the acquisition files",
               relative_median=rel,
               median_abs_m=float(np.median(np.abs(hdr - ext))) if ext.size else None,
               max_abs_m=float(np.abs(hdr - ext).max()) if ext.size else None)
    if rel < geometry.HEADER_AGREEMENT_RELATIVE:
        out.update(case="2_segy_geometry_present_and_consistent", conflict=False,
                   reason=f"The header geometry and the acquisition files agree to "
                          f"{rel * 100:.2f}%, inside the tolerance the geometry "
                          f"stage already applies to a header.")
    else:
        out.update(case="3_segy_geometry_present_and_conflicting", conflict=True,
                   reason=f"The header geometry and the acquisition files disagree "
                          f"by {rel * 100:.1f}%. Which of the two is authoritative "
                          f"is a survey question this version does not answer, so "
                          f"nothing is overwritten and the assignment is refused.")
    return out


def _read_set(sps_file, rps_file, xps_file) -> dict:
    return sps.read_set(safe_input_path(sps_file), safe_input_path(rps_file),
                        safe_input_path(xps_file))


def inspect_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                              xps_file: str) -> dict:
    """Read an S/R/X set against a dataset and report what would happen."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["dataset.imported", "headers.parsed"],
                     "External geometry inspection")
    su_path = safe_input_path(evidence.get_artifact(manifest, "su")["path"])
    geom = sufile.geometry(su_path)
    cols = sufile.read_header_columns(su_path, ["fldr", "tracf", "trid"], geom)

    parsed = _read_set(sps_file, rps_file, xps_file)
    assign = external.relation_assignment(cols["fldr"], cols["tracf"],
                                          cols["trid"], parsed)
    resolved = geometry.resolve_coordinates(su_path, geom)
    comparison = _header_comparison(resolved, assign, assign["placed"])
    return {
        "run_id": run_id, "dataset_id": dataset_id,
        "su_file": as_rel(su_path), "traces_in_file": geom["ntr"],
        "files": parsed["paths"], "layouts": parsed["layouts"],
        "counts": {**parsed["counts"], **assign["counts"]},
        "parse_problems": {k: v[:10] for k, v in parsed["problems"].items()},
        "checks": assign["checks"], "verdict": assign["verdict"],
        "header_comparison": comparison,
        "would_assign": bool(assign["verdict"]["verdict"] == "ACCEPTED"
                             and not comparison["conflict"]),
        "algorithm_versions": {"sps": parsed["algorithm_version"],
                               "assignment": assign["algorithm_version"]},
        "note": "Nothing was written and no capability was set.",
    }


def assign_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                             xps_file: str, overwrite: bool = False) -> dict:
    """Attach an S/R/X set to a dataset, on a processing copy, and validate it."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    evidence.require(manifest, ["dataset.imported", "headers.parsed"],
                     "External geometry assignment")
    su_path = safe_input_path(evidence.get_artifact(manifest, "su")["path"])
    geom = sufile.geometry(su_path)
    cols = sufile.read_header_columns(su_path, ["fldr", "tracf", "trid"], geom)

    parsed = _read_set(sps_file, rps_file, xps_file)
    assign = external.relation_assignment(cols["fldr"], cols["tracf"],
                                          cols["trid"], parsed)
    keep = assign["placed"]
    resolved = geometry.resolve_coordinates(su_path, geom)
    comparison = _header_comparison(resolved, assign, keep)

    mapping_ok = assign["checks"]["field_records_match_relations"]["supports_assignment"]
    _set(manifest, "geometry.shotpoint_mapping", mapping_ok,
         {"source": "SPS X relation records, read not counted",
          "records_in_file": int(np.unique(cols["fldr"]).size),
          "relations_read": len(parsed["relations"]),
          "records_without_a_relation":
              assign["checks"]["field_records_match_relations"]
              ["records_without_a_relation"],
          "origin": C.ORIGIN_ACQUISITION_LOG,
          "file": parsed["paths"]["X"]},
         run_id, notes=[assign["checks"]["field_records_match_relations"]["reason"]])

    accepted = (assign["verdict"]["verdict"] == "ACCEPTED"
                and not comparison["conflict"])
    if not accepted:
        why = list(assign["problems"])
        if comparison["conflict"]:
            why.append("header_geometry_conflict: " + comparison["reason"])
        _set(manifest, "geometry.external_geometry_assigned", False,
             {"files": parsed["paths"], "counts": {**parsed["counts"],
                                                   **assign["counts"]},
              "checks": {k: v["reason"] for k, v in assign["checks"].items()},
              "header_comparison": comparison,
              "origin": C.ORIGIN_ACQUISITION_LOG}, run_id, notes=why)
        _set(manifest, "geometry.assignment_validated", False,
             {"verdict": assign["verdict"], "header_comparison": comparison},
             run_id, notes=why)
        evidence.save(manifest)
        return {"run_id": run_id, "dataset_id": dataset_id, "assigned": False,
                "counts": {**parsed["counts"], **assign["counts"]},
                "layouts": parsed["layouts"],
                "checks": assign["checks"], "verdict": assign["verdict"],
                "header_comparison": comparison, "problems": why,
                "capabilities": {
                    "geometry.external_geometry_assigned": evidence.FAIL,
                    "geometry.assignment_validated": evidence.FAIL},
                "reason": ("The acquisition geometry was not attached. "
                           + " ".join(why))}

    # ---- write the processing copy -----------------------------------------
    coords = np.concatenate([assign["sx"][keep], assign["sy"][keep],
                             assign["gx"][keep], assign["gy"][keep]])
    scale = _scalco_for(coords)
    scalco = -scale if scale > 1 else 1

    def word(values):
        return np.rint(np.asarray(values, float) * scale).astype(np.int64)

    columns = {
        "sx": word(assign["sx"]), "sy": word(assign["sy"]),
        "gx": word(assign["gx"]), "gy": word(assign["gy"]),
        "offset": np.rint(assign["offset"]).astype(np.int64),
        "scalco": np.full(geom["ntr"], scalco, dtype=np.int64),
        "counit": np.ones(geom["ntr"], dtype=np.int64),
    }
    if assign["statics"]["available"]:
        columns.update({
            "sstat": np.rint(assign["sstat_ms"]).astype(np.int64),
            "gstat": np.rint(assign["gstat_ms"]).astype(np.int64),
            "tstat": np.rint(assign["sstat_ms"] + assign["gstat_ms"])
            .astype(np.int64),
        })
    out_dir = config.WORK_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = safe_output_path(as_rel(out_dir / f"{dataset_id}_geom.su"),
                           overwrite=overwrite)
    written = sufile.write_header_columns(su_path, dst, columns, keep=keep)

    recorded = evidence.get_artifact(manifest, "su").get("sha256")
    now = provenance.file_fingerprint(su_path).get("sha256")
    source_unchanged = (recorded is not None and now == recorded)

    evidence.add_artifact(manifest, EXTERNAL_SU_ROLE, dst, "geometry-assigned",
                          parents=[as_rel(su_path), parsed["paths"]["S"],
                                   parsed["paths"]["R"], parsed["paths"]["X"]],
                          run_id=run_id)
    _set(manifest, "geometry.external_geometry_assigned", True,
         {"files": parsed["paths"], "layouts": parsed["layouts"],
          "counts": {**parsed["counts"], **assign["counts"]},
          "written": written, "scalco": scalco, "counit": 1,
          "acquisition_statics": assign["statics"],
          "counit_reason": "the S and R files give a map grid in length units",
          "offset_sign": "positive toward increasing receiver station along the "
                         "line's own principal direction",
          "claim": assign["claim"],
          "origin": C.ORIGIN_ACQUISITION_LOG,
          "geometry_type": "nominal survey geometry from the acquisition files, "
                           "not a measured position",
          "source_file_modified": False,
          "source_file": as_rel(su_path),
          "source_file_sha256_unchanged": source_unchanged,
          "processing_copy": as_rel(dst)},
         run_id, artifact=as_rel(dst))
    _set(manifest, "geometry.assignment_validated", True,
         {"verdict": assign["verdict"],
          "checks": {k: {kk: vv for kk, vv in v.items() if kk != "reason"}
                     for k, v in assign["checks"].items()},
          "reasons": {k: v["reason"] for k, v in assign["checks"].items()},
          "header_comparison": comparison},
         run_id, notes=[assign["verdict"]["reason"]])
    evidence.save(manifest)

    report = {
        "algorithm_versions": {"sps": parsed["algorithm_version"],
                               "assignment": assign["algorithm_version"]},
        "dataset_id": dataset_id, "run_id": run_id,
        "files": parsed["paths"], "layouts": parsed["layouts"],
        "counts": {**parsed["counts"], **assign["counts"]},
        "checks": assign["checks"], "verdict": assign["verdict"],
        "header_comparison": comparison, "written": written,
        "scalco": scalco, "counit": 1,
        "acquisition_statics": assign["statics"],
        "processing_copy": as_rel(dst), "source_file": as_rel(su_path),
        "source_file_modified": False,
    }
    path = out_dir / "external_geometry_report.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # ---- hand back to the existing geometry stage, on the copy -------------
    follow = analyze_geometry(dataset_id)
    manifest = evidence.load(dataset_id)
    return {
        "run_id": run_id, "dataset_id": dataset_id, "assigned": True,
        "report": as_rel(path), **{k: report[k] for k in
            ("files", "layouts", "counts", "checks", "verdict",
             "header_comparison", "written", "scalco", "counit",
             "acquisition_statics",
             "processing_copy", "source_file", "source_file_modified")},
        "geometry_after_assignment": {
            "classification": follow["classification"]["kind"],
            "offsets": follow["offsets"], "cdp": follow["cdp"]},
        "capabilities": {k: v["status"] for k, v in manifest["capabilities"].items()},
    }
