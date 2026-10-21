"""Dataset manifests: capabilities, evidence and artifact lineage."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config, governance, provenance
from .provenance import file_fingerprint

__all__ = [
    "CAPABILITIES", "PASS", "FAIL", "UNKNOWN",
    "DatasetError", "PrerequisiteError",
    "create", "load", "exists", "list_datasets", "save",
    "set_capability", "add_artifact", "get_artifact", "require",
    "capability_status", "get_capability", "summary",
]

SCHEMA_VERSION = 1

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
_STATUSES = (PASS, FAIL, UNKNOWN)

# The full vocabulary, declared up front so every version uses the same names and so a refusal can explain which
# later stage is still missing.
CAPABILITIES = {
    # v0.2
    "dataset.registered": "A manifest exists and names a source file.",
    "dataset.imported": "The source has been converted to an SU file.",
    "headers.parsed": "SU trace headers were read and summarised.",
    "headers.sampling_consistent": "ns and dt agree between the source and the SU file.",
    "headers.trace_count_consistent": "The imported trace count matches the source.",
    # v0.3
    "geometry.source_coords_available": "sx/sy are populated and vary.",
    "geometry.receiver_coords_available": "gx/gy are populated and vary.",
    "geometry.coordinate_scale_resolved": "scalco and counit were applied and the units are known.",
    "geometry.receiver_positions_trustworthy":
        "The receiver coordinates describe where the receivers really were, "
        "tested against the data rather than assumed.",
    "geometry.acquisition_classified":
        "The acquisition geometry has been named from measured evidence.",
    "geometry.receiver_spacing_consistent":
        "The velocity measured across the channels agrees with the velocity measured "
        "against source-receiver distance, so both coordinate sets describe one wavefront.",
    "geometry.offset_header_consistent":
        "Diagnosis: the offset header agrees with the distance between the "
        "coordinates. Not a gate -- a wrong header can be repaired from the "
        "coordinates, and this says whether it needs to be.",
    "geometry.processing_offset_resolved":
        "Gate: an offset exists that this survey may be processed with. Its "
        "evidence names the origin, TRACE_HEADERS or DERIVED_FROM_COORDINATES.",
    "geometry.array_geometry_resolved":
        "Whether the channel moveout is a receiver-spacing error or a per-channel "
        "recording delay has been decided from lines that can tell them apart, or "
        "the geometry has been shown unable to decide it.",
    # v0.10 -- geometry that is not in the file
    "geometry.shotpoint_mapping":
        "Each trace's field record has been tied to the survey shotpoint it "
        "belongs to, from the observer log rather than by counting. Without "
        "this nothing external can be attached to the right trace.",
    "geometry.external_geometry_assigned":
        "Source and receiver positions have been written from acquisition "
        "metadata outside the file. The values are nominal survey geometry, "
        "not measured positions, and carry the origin they came from.",
    "geometry.assignment_validated":
        "The assigned geometry has been tested against the data it was "
        "attached to -- the direct arrival, the seafloor moveout and the fold "
        "pattern -- rather than trusted because it parsed.",
    "geometry.cdp_header_plausible":
        "The cdp header is populated and its bins hold midpoints that belong together.",
    "geometry.cmp_assigned": "Every trace carries a CMP bin number.",
    "geometry.fold_valid": "Fold per bin is within the expected range.",
    "geometry.validated": "The geometry may be used for CMP processing.",
    # v0.15
    "acquisition.time_zero_consistent":
        "The direct wave, flattened at its own velocity, peaks within one "
        "dominant period of the SEG-Y time zero, so t = 0 is the shot instant "
        "and hyperbolic velocities read from the record are not biased by a "
        "shifted clock. UNKNOWN where the direct wave is not robust enough to "
        "carry the clock.",
    "reflection.direct_wave_suppressed":
        "The direct wave has been suppressed by three independent methods and the "
        "amount each one left is recorded.",
    "reflection.processing_feasible":
        "A reflection candidate survives all three suppression branches, and the "
        "amplitude at which one would have been detected is recorded. FAIL with a "
        "recorded detection threshold means 'not detectable here', not 'not present'.",
    # v0.4
    "processing.preprocessed": "A preprocessing product exists and passed QC.",
    # v0.5
    "velocity.model_available": "A stacking velocity model exists for this dataset.",
    "velocity.validated": "The velocity model passed monotonicity and bounds checks.",
    # v0.6
    "nmo.applied": "NMO correction has been applied.",
    "nmo.qc_passed": "Stretch and mute QC passed.",
    "stack.completed": "A stack section exists.",
    # v0.24
    "migration.completed":
        "A post-stack time migration exists and its operator focused synthetic "
        "diffractions with the same velocities (M1); FAIL keeps it for audit only.",
    # v0.28
    "depth.completed":
        "A depth image exists (depth_convert or depth_pspi) with its depth tolerance stated (Z3); "
        "depth_pspi focused synthetic diffractions in depth (Z1); FAIL keeps it for audit only.",
}


class DatasetError(ValueError):
    """The dataset id or manifest is unusable."""


class PrerequisiteError(PermissionError):
    """A required capability is missing; the message explains which and why."""

    def __init__(self, message, failed=()):
        super().__init__(message)
        self.failed = list(failed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_id(dataset_id: str) -> str:
    dataset_id = str(dataset_id).strip()
    if not config.DATASET_ID_RE.match(dataset_id):
        raise DatasetError(
            f"Invalid dataset id {dataset_id!r}: use lower-case letters, digits, "
            "'-' and '_', starting with a letter or digit."
        )
    return dataset_id


def manifest_path(dataset_id: str) -> Path:
    return config.DATASET_DIR / f"{_check_id(dataset_id)}.json"


def exists(dataset_id: str) -> bool:
    return manifest_path(dataset_id).is_file()


def list_datasets() -> list:
    if not config.DATASET_DIR.is_dir():
        return []
    return sorted(p.stem for p in config.DATASET_DIR.glob("*.json"))


def save(manifest: dict) -> dict:
    """Write the manifest atomically, so a crash cannot leave it half-written."""
    manifest["updated"] = _now()
    path = manifest_path(manifest["dataset_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=False)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return manifest


def load(dataset_id: str) -> dict:
    path = manifest_path(dataset_id)
    if not path.is_file():
        known = list_datasets()
        raise DatasetError(
            f"No dataset {dataset_id!r}. "
            + (f"Known datasets: {', '.join(known)}." if known else
               "No datasets have been registered yet.")
        )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def create(dataset_id: str, source_path: Path, source_kind: str,
           run_id: str, description: str = "") -> dict:
    dataset_id = _check_id(dataset_id)
    if exists(dataset_id):
        raise DatasetError(f"Dataset {dataset_id!r} already exists.")
    from .paths import as_rel
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "description": description,
        "created": _now(),
        "updated": _now(),
        "source": {
            "path": as_rel(source_path),
            "kind": source_kind,
            **file_fingerprint(source_path),
        },
        "artifacts": {},
        "capabilities": {},
        "history": [],
    }
    _history(manifest, run_id, "create", {"source": manifest["source"]["path"],
                                          "kind": source_kind})
    return manifest


def _history(manifest: dict, run_id: str, action: str, detail: dict) -> None:
    manifest.setdefault("history", []).append(
        {"timestamp": _now(), "run_id": run_id, "action": action, "detail": detail})


def record_product_run(manifest: dict, name: str, released: bool, evidence: dict,
                       algorithm_version: str, run_id: str, artifact: str | None = None,
                       notes=None) -> dict:
    """v0.31 B1: a rejected run never demotes a capability that a released product holds."""
    current = (manifest.get("capabilities") or {}).get(name) or {}
    attempt = {"run_id": run_id, "released": bool(released), "artifact": artifact,
               "method": (evidence or {}).get("method"), "timestamp": _now(),
               "notes": list(notes or [])}
    if not released and current.get("status") == PASS:
        current.setdefault("attempts", []).append(attempt)
        _history(manifest, run_id, "rejected_attempt_recorded", {"capability": name})
        return current
    previous = list(current.get("attempts") or [])
    entry = set_capability(manifest, name, PASS if released else FAIL, evidence,
                           algorithm_version, run_id, artifact=artifact, notes=notes)
    entry["attempts"] = previous + [attempt]
    return entry


# v0.33.2 I1.
_ARTIFACT_PREFIX = {"migration.completed": "migration_", "depth.completed": "depth_"}
PRODUCT_CHAIN = ("velocity.model_available", "velocity.validated", "nmo.applied", "stack.completed",
                 "migration.completed", "depth.completed")


def invalidate_downstream(manifest: dict, after: str, reason: str, algorithm_version: str,
                          run_id: str) -> list:
    """Return every capability later in PRODUCT_CHAIN than `after` that holds a verdict to UNKNOWN."""
    if after not in PRODUCT_CHAIN:
        raise DatasetError(f"{after!r} is not in the product chain")
    caps = manifest.get("capabilities") or {}
    changed = []
    for name in PRODUCT_CHAIN[PRODUCT_CHAIN.index(after) + 1:]:
        current = caps.get(name)
        if not current or current.get("status") == UNKNOWN:
            continue
        attempts = current.get("attempts")
        entry = set_capability(
            manifest, name, UNKNOWN,
            {"reason": reason, "invalidated_by": after, "previous_status": current.get("status"),
             "previous_artifact": current.get("artifact"), "previous_run_id": current.get("run_id")},
            algorithm_version, run_id,
            notes=[f"Invalidated (I1): {reason}. The earlier product is kept for audit only."])
        if attempts:
            entry["attempts"] = attempts
        changed.append(name)
        # the files themselves are marked, so a step that reads an artifact by name cannot take a stale one
        prefix = _ARTIFACT_PREFIX.get(name)
        for logical, art in (manifest.get("artifacts") or {}).items():
            if prefix and logical.startswith(prefix) and not logical.endswith("_rejected"):
                art["superseded"] = {"run_id": run_id, "reason": reason}
    return changed


def invalidate_after_migration(manifest: dict, reason: str, algorithm_version: str, run_id: str) -> list:
    """v0.33.3 I1b."""
    changed = []
    art = (manifest.get("artifacts") or {}).get("depth_depth_convert")
    if art and not art.get("superseded"):
        art["superseded"] = {"run_id": run_id, "reason": reason}
        changed.append("depth_depth_convert")
    current = (manifest.get("capabilities") or {}).get("depth.completed")
    if (current and current.get("status") != UNKNOWN
            and (current.get("evidence") or {}).get("method") == "depth_convert"):
        attempts = current.get("attempts")
        entry = set_capability(
            manifest, "depth.completed", UNKNOWN,
            {"reason": reason, "invalidated_by": "migration.completed", "previous_status": current.get("status"),
             "previous_artifact": current.get("artifact"), "previous_run_id": current.get("run_id")},
            algorithm_version, run_id,
            notes=[f"Invalidated (I1b): {reason}. The earlier product is kept for audit only."])
        if attempts:
            entry["attempts"] = attempts
        changed.append("depth.completed")
    return changed


def superseded(manifest: dict, logical_name: str) -> dict | None:
    """The I1 mark on an artifact whose inputs were replaced after it was made, or None."""
    return ((manifest.get("artifacts") or {}).get(logical_name) or {}).get("superseded")


def set_capability(manifest: dict, name: str, status: str, evidence: dict,
                   algorithm_version: str, run_id: str,
                   artifact: str | None = None, notes=None) -> dict:
    if name not in CAPABILITIES:
        raise DatasetError(
            f"Unknown capability {name!r}. Declared capabilities: "
            + ", ".join(sorted(CAPABILITIES))
        )
    if status not in _STATUSES:
        raise DatasetError(f"status must be one of {_STATUSES}")
    entry = {
        "status": status,
        "evidence": evidence,
        "artifact": artifact,
        "algorithm_version": algorithm_version,
        "run_id": run_id,
        "timestamp": _now(),
        "notes": list(notes or []),
    }
    manifest.setdefault("capabilities", {})[name] = entry
    provenance.note_gate(name, status, "set",
                         detail=(list(notes or []) or None))
    _history(manifest, run_id, "set_capability", {"capability": name, "status": status})
    return entry


def get_capability(manifest: dict, name: str) -> dict | None:
    """The whole capability entry, evidence included, or None."""
    return manifest.get("capabilities", {}).get(name)


def capability_status(manifest: dict, name: str) -> str:
    return manifest.get("capabilities", {}).get(name, {}).get("status", UNKNOWN)


def add_artifact(manifest: dict, logical_name: str, path: Path, role: str,
                 run_id: str, parents=None) -> dict:
    from .paths import as_rel
    entry = {
        "path": as_rel(path),
        "role": role,
        "produced_by": run_id,
        "parents": list(parents or []),
        "created": _now(),
        **file_fingerprint(path),
    }
    manifest.setdefault("artifacts", {})[logical_name] = entry
    provenance.note_artifact(path, role)
    _history(manifest, run_id, "add_artifact",
             {"artifact": logical_name, "path": entry["path"]})
    return entry


def get_artifact(manifest: dict, logical_name: str) -> dict:
    artifacts = manifest.get("artifacts", {})
    if logical_name not in artifacts:
        raise DatasetError(
            f"Dataset {manifest['dataset_id']!r} has no artifact {logical_name!r}. "
            f"It has: {', '.join(sorted(artifacts)) or '(none)'}."
        )
    return artifacts[logical_name]


def processing_su(manifest: dict) -> dict:
    """The SU file downstream steps should read."""
    if "geometry" in manifest.get("artifacts", {}):
        return get_artifact(manifest, "geometry")
    return get_artifact(manifest, "su")


def require(manifest: dict, names, action: str = "this step") -> None:
    """Refuse an action unless every named capability is PASS."""
    if governance.off():
        return _require_mechanical(manifest, names, action)
    missing, failed = [], []
    for name in names:
        entry = manifest.get("capabilities", {}).get(name)
        status = UNKNOWN if entry is None else entry["status"]
        # Every consulted capability is logged, not only the ones that refuse: "these five were checked and
        # passed" is part of the audit trail.
        provenance.note_gate(name, status, "required")
        if entry is None:
            missing.append(f"{name}: never evaluated ({CAPABILITIES.get(name, '')})")
            failed.append({"capability": name, "status": status,
                           "reason": "never evaluated"})
        elif entry["status"] != PASS:
            detail = entry.get("notes") or list(entry.get("evidence", {}).items())[:3]
            missing.append(f"{name}: {entry['status']} - {detail}")
            failed.append({"capability": name, "status": status,
                           "reason": str(detail)})
    if missing:
        raise PrerequisiteError(
            f"{action} is not permitted for dataset {manifest['dataset_id']!r}.\n"
            + "\n".join("  - " + m for m in missing),
            failed=failed,
        )


def _require_mechanical(manifest: dict, names, action: str) -> None:
    """Governance OFF (baseline01 C0): only the mechanical part of each requirement."""
    missing = []
    for name in names:
        entry = manifest.get("capabilities", {}).get(name)
        if name in governance.MECHANICAL_STATUS:
            if entry is None or entry["status"] != PASS:
                missing.append(f"{name}: {UNKNOWN if entry is None else entry['status']}")
        elif name in governance.MECHANICAL_ARTIFACT:
            if not any(a in manifest.get("artifacts", {}) for a in governance.MECHANICAL_ARTIFACT[name]):
                missing.append(f"{name}: the product it needs does not exist yet")
    if missing:
        raise PrerequisiteError(
            f"{action} cannot run for dataset {manifest['dataset_id']!r}:\n"
            + "\n".join("  - " + m for m in missing),
            failed=[{"capability": m.split(":")[0], "status": "MISSING", "reason": m} for m in missing])


def summary(manifest: dict) -> dict:
    """Compact view: what is known, what is not, and what exists on disk."""
    caps = manifest.get("capabilities", {})
    by_status = {PASS: [], FAIL: [], UNKNOWN: []}
    for name in CAPABILITIES:
        by_status[caps.get(name, {}).get("status", UNKNOWN)].append(name)
    return {
        "dataset_id": manifest["dataset_id"],
        "description": manifest.get("description", ""),
        "source": manifest["source"],
        "artifacts": {k: v["path"] for k, v in manifest.get("artifacts", {}).items()},
        "capabilities_pass": by_status[PASS],
        "capabilities_fail": by_status[FAIL],
        "capabilities_unknown": by_status[UNKNOWN],
        "updated": manifest.get("updated"),
    }
