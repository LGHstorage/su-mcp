"""CMP binning, and the gate in front of it."""

from __future__ import annotations

import json

import numpy as np

from . import config, evidence, geometry, provenance, sufile
from .paths import as_rel, safe_input_path, safe_output_path

CMP_VERSION = "cmp-0.8"

__all__ = ["CMP_VERSION", "STACK_TRACK_PREREQUISITES", "build_cmp", "feasibility_gate",
           "cdp_origin"]

# What has to be established before a dataset may enter the stack pipeline.
STACK_TRACK_PREREQUISITES = [
    "geometry.coordinate_scale_resolved",
    "geometry.source_coords_available",
    "geometry.receiver_coords_available",
    "geometry.acquisition_classified",
    "geometry.receiver_positions_trustworthy",
    # Added after round 1 of the adversarial suite: the offset diagnosis was recorded and then ignored, and a file
    # with a doubled offset header and otherwise valid coordinates would have reached a stack with offsets twice
    # the truth.
    "geometry.processing_offset_resolved",
    "reflection.processing_feasible",
]


def _set(manifest, name, ok, evidence_dict, run_id, notes=(), artifact=None):
    status = {True: evidence.PASS, False: evidence.FAIL, None: evidence.UNKNOWN}[ok]
    return evidence.set_capability(manifest, name, status, evidence_dict,
                                   CMP_VERSION, run_id, artifact=artifact,
                                   notes=list(notes))


def feasibility_gate(manifest) -> str:
    """The stack-track prerequisites, with v0.20 G1."""
    others = [n for n in STACK_TRACK_PREREQUISITES if n != "reflection.processing_feasible"]
    evidence.require(manifest, others, "CMP binning (entering the stack pipeline)")
    cap = evidence.get_capability(manifest, "reflection.processing_feasible") or {}
    if (cap.get("status") == evidence.UNKNOWN
            and (cap.get("evidence") or {}).get("verdict") == "INCONCLUSIVE"):
        provenance.note_gate("reflection.processing_feasible", evidence.UNKNOWN,
                             "required", detail=["v0.20 G1: INCONCLUSIVE admitted"])
        return "INCONCLUSIVE"
    evidence.require(manifest, ["reflection.processing_feasible"],
                     "CMP binning (entering the stack pipeline)")
    return "PASS"


def build_cmp(dataset_id: str, *, bin_size_m: float | None = None,
              receiver_spacing_m: float | None = None,
              reference_velocity_m_s: float = 1800.0,
              reference_t0_s: float = 1.0,
              min_fold: int = 4, overwrite: bool = False) -> dict:
    """Assign CMP bins, write them into the cdp header, and grade the result."""
    run_id = provenance.new_run_id()
    manifest = evidence.load(dataset_id)
    feasibility_basis = feasibility_gate(manifest)

    su_path = safe_input_path(evidence.processing_su(manifest)["path"])
    geom = sufile.geometry(su_path)
    resolved = geometry.resolve_coordinates(su_path, geom)

    if receiver_spacing_m is None and bin_size_m is None:
        receiver_spacing_m = geometry.receiver_variation(resolved)["channel_spacing_m"]

    plan = geometry.assign_cmp(
        resolved, bin_size_m=bin_size_m, receiver_spacing_m=receiver_spacing_m,
        reference_velocity_m_s=reference_velocity_m_s,
        reference_t0_s=reference_t0_s, sample_interval_s=geom["dt_s"])
    cdp = np.asarray(plan.pop("cdp"))

    header_cdp = np.asarray(resolved["_raw"]["cdp"])
    comparison = _compare_with_header(header_cdp, cdp)

    cdp_repair = cdp_origin(header_cdp, comparison, as_rel(su_path))
    cdp_agrees = bool(comparison.get("agrees"))

    # When the file's own cdp groups the traces exactly as the coordinates do, keep its numbering.
    if comparison.get("agrees"):
        lookup = {int(b): int(header_cdp[cdp == b][0]) for b in np.unique(cdp)}
        cdp = np.asarray([lookup[int(b)] for b in cdp])
        comparison["numbering"] = "kept from the file, having been verified"
    elif comparison["header_cdp"] == "present":
        comparison["numbering"] = (
            "computed from the coordinates; the file's own numbering is "
            "replaced because it does not group the traces the same way")
    else:
        comparison["numbering"] = "computed from the coordinates"

    out_dir = config.WORK_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = safe_output_path(as_rel(out_dir / f"{dataset_id}_cmp.su"),
                           overwrite=overwrite)

    # The processing copy carries the canonical offset, which is not always the one in the file.
    canonical = evidence.get_capability(manifest, "geometry.processing_offset_resolved")
    repair = (canonical.get("evidence") or {}) if canonical else {}
    columns = {"cdp": cdp}
    offset_repair = None
    if repair.get("origin") == geometry.OFFSET_FROM_COORDINATES:
        header = resolved["_raw"]["offset"].astype(np.float64)
        derived = np.hypot(resolved["_scaled"]["gx"] - resolved["_scaled"]["sx"],
                           resolved["_scaled"]["gy"] - resolved["_scaled"]["sy"])
        # Keep the file's own sign convention: a negative offset means the receiver is behind the source, which is
        # geometry, not corruption.
        sign = np.where(header < 0, -1.0, 1.0) if np.any(header < 0) else 1.0
        repaired = np.rint(derived * sign).astype(np.int64)
        difference = np.abs(np.abs(header) - derived)
        columns["offset"] = repaired
        offset_repair = {
            "applied": True,
            "origin": geometry.OFFSET_FROM_COORDINATES,
            "formula": "offset = sign(header) * hypot(gx - sx, gy - sy), "
                       "coordinates scaled by scalco",
            "traces_repaired": int(repaired.size),
            "original_offset_range_m": [float(np.abs(header).min()),
                                        float(np.abs(header).max())],
            "processing_offset_range_m": [float(np.abs(repaired).min()),
                                          float(np.abs(repaired).max())],
            "difference_m": {"min": float(difference.min()),
                             "median": float(np.median(difference)),
                             "max": float(difference.max())},
            "source_file_modified": False,
            "source_file": as_rel(su_path),
            "processing_file": as_rel(dst),
        }

    written = (sufile.write_header_columns(su_path, dst, columns)
               if len(columns) > 1
               else sufile.write_header_column(su_path, dst, "cdp", cdp))
    if offset_repair is not None:
        offset_repair["processing_file_sha256"] = \
            provenance.file_fingerprint(dst).get("sha256")

    fold, leverage = plan["fold"], plan["nmo_leverage"]
    fold_ok = fold["median"] >= min_fold and leverage["verdict"] != "NONE"
    reasons = []
    if fold["median"] < min_fold:
        reasons.append(
            f"median fold {fold['median']} is below the {min_fold} this step "
            f"requires; there is no gather to stack")
    if leverage["verdict"] == "NONE":
        reasons.append(
            f"no NMO leverage: {leverage.get('reason', 'the bins carry no moveout')}. "
            f"Fold alone does not make a gather stackable -- moveout is linear in "
            f"offset squared, and these bins hold "
            f"{leverage['moveout_spread_ms']:.1f} ms of it at the reference "
            f"{reference_velocity_m_s:g} m/s, {reference_t0_s:g} s")
    elif leverage["verdict"] == "MARGINAL":
        reasons.append(
            f"leverage is MARGINAL: {leverage['moveout_spread_ms']:.1f} ms across a "
            f"bin at the reference hyperbola. A velocity scan will be poorly "
            f"constrained and the stack will be close to a straight sum")

    _set(manifest, "geometry.cmp_assigned", True,
         {"bin_size_m": plan["bin_size_m"], "bins": fold["n_bins_occupied"],
          "line_length_m": round(plan["line_length_m"], 1),
          "crookedness_rms_m": round(plan["crookedness_rms_m"], 2),
          "header_cdp_comparison": comparison,
          "offset_repair": offset_repair or {"applied": False,
                                             "origin": repair.get("origin")},
          "cdp_repair": cdp_repair,
          "feasibility_basis": feasibility_basis,
          "output": as_rel(dst)},
         run_id, artifact=as_rel(dst),
         notes=([f"The cdp header groups the traces differently from the "
                 f"coordinates ({comparison.get('header_bins')} header bins "
                 f"against {comparison.get('computed_bins')} computed); the "
                 f"processing copy is binned from the coordinates and "
                 f"{as_rel(su_path)} is unchanged."]
                if not cdp_agrees else [])
               + ([f"The offset header was rejected and replaced in the processing "
                 f"copy from the coordinates; the two differed by a median of "
                 f"{offset_repair['difference_m']['median']:.1f} m over "
                 f"{offset_repair['traces_repaired']} traces. "
                 f"{as_rel(su_path)} is unchanged."]
                  if offset_repair else []))
    _set(manifest, "geometry.fold_valid", fold_ok,
         {"fold": fold, "nmo_leverage": leverage,
          "offset_diversity": round(plan["offset_diversity"], 3),
          "min_fold_required": min_fold},
         run_id, notes=reasons)

    evidence.add_artifact(manifest, "cmp", dst, "cmp-binned",
                          parents=[as_rel(su_path)], run_id=run_id)
    report = out_dir / "cmp_report.json"
    report.write_text(json.dumps(
        {"dataset_id": dataset_id, "run_id": run_id, "plan": plan,
         "written": written, "header_cdp_comparison": comparison},
        indent=2, default=str), encoding="utf-8")
    evidence.save(manifest)

    return {
        "run_id": run_id, "dataset_id": dataset_id,
        "output": as_rel(dst), "report": as_rel(report),
        "bin_size_m": plan["bin_size_m"],
        "fold": fold, "nmo_leverage": leverage,
        "offset_diversity": round(plan["offset_diversity"], 3),
        "line_length_m": round(plan["line_length_m"], 1),
        "crookedness_rms_m": round(plan["crookedness_rms_m"], 2),
        "crookedness_max_m": round(plan["crookedness_max_m"], 2),
        "header_cdp_comparison": comparison,
        "offset_repair": offset_repair or {"applied": False,
                                           "origin": repair.get("origin")},
        "cdp_repair": cdp_repair,
        "feasibility_basis": feasibility_basis,
        "capabilities": {
            "geometry.cmp_assigned": evidence.capability_status(
                manifest, "geometry.cmp_assigned"),
            "geometry.fold_valid": evidence.capability_status(
                manifest, "geometry.fold_valid"),
        },
        "notes": reasons + ([
            "Reflection feasibility was INCONCLUSIVE on its gather; binning is "
            "admitted (v0.20 G1) and the velocity analysis will decide whether "
            "there is anything to stack."] if feasibility_basis == "INCONCLUSIVE" else []),
        "algorithm_version": CMP_VERSION,
    }


def cdp_origin(header_cdp, comparison, source_rel) -> dict:
    """Where the processing copy's cdp came from, recorded as the offset is."""
    header_cdp = np.asarray(header_cdp)
    agrees = bool(comparison.get("agrees"))
    return {
        "applied": not agrees,
        "origin": (geometry.OFFSET_FROM_HEADER if agrees
                   else geometry.OFFSET_FROM_COORDINATES),
        "header_state": ("absent" if not header_cdp.size or np.all(header_cdp == 0)
                         else "constant" if np.unique(header_cdp).size == 1
                         else "varying"),
        "header_bins": comparison.get("header_bins"),
        "computed_bins": comparison.get("computed_bins"),
        "header_bins_split_by_coordinates":
            comparison.get("header_bins_split_by_coordinates"),
        "computed_bins_merged_in_header":
            comparison.get("computed_bins_merged_in_header"),
        "formula": "bin = floor((midpoint along the line - origin) / bin size), "
                   "midpoints from the scaled coordinates",
        "source_file_modified": False,
        "source_file": source_rel,
    }


def _compare_with_header(header_cdp, computed) -> dict:
    """Does the cdp already in the file mean the same bins as the coordinates?"""
    header_cdp = np.asarray(header_cdp)
    if not header_cdp.any():
        return {"header_cdp": "absent", "agrees": None,
                "note": "the file carries no cdp, so there is nothing to compare"}

    splits = merges = 0
    for value in np.unique(header_cdp):
        if len(np.unique(computed[header_cdp == value])) > 1:
            splits += 1
    for value in np.unique(computed):
        if len(np.unique(header_cdp[computed == value])) > 1:
            merges += 1
    agrees = splits == 0 and merges == 0
    return {
        "header_cdp": "present",
        "header_bins": int(np.unique(header_cdp).size),
        "computed_bins": int(np.unique(computed).size),
        "header_bins_split_by_coordinates": splits,
        "computed_bins_merged_in_header": merges,
        "agrees": bool(agrees),
        "note": ("The cdp already in the file groups the traces exactly as the "
                 "coordinates do." if agrees else
                 "The cdp in the file and the coordinates do not group the traces "
                 "the same way. The computed binning is what the output carries; "
                 "the disagreement is recorded rather than resolved, because "
                 "which one is right depends on survey information this file "
                 "does not contain."),
    }
