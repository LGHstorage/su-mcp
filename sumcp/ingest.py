"""Getting data into the project, and proving that it arrived intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config, evidence, provenance, runner, segy, sufile
from .paths import as_rel, safe_input_path

__all__ = ["IMPORTER_VERSION", "HEADER_KEYS_OF_INTEREST",
           "header_availability", "register_su", "import_segy"]

IMPORTER_VERSION = "importer-0.2"

# The header words later stages depend on.
HEADER_KEYS_OF_INTEREST = (
    "fldr", "tracf", "ep", "cdp", "cdpt", "offset",
    "sx", "sy", "gx", "gy", "scalco", "scalel", "counit",
    "selev", "gelev", "delrt", "trid",
)


def _classify(stats: dict) -> str:
    if stats is None:
        return "absent"
    if stats["min"] == 0 and stats["max"] == 0:
        return "zero"
    if stats["constant"]:
        return "constant"
    return "varying"


def header_availability(scan: dict) -> dict:
    """Per-key availability: absent / zero / constant / varying, plus a verdict."""
    keys = scan.get("keys", {})
    report = {}
    for key in HEADER_KEYS_OF_INTEREST:
        stats = keys.get(key)
        entry = {"state": _classify(stats)}
        if stats:
            entry.update({k: stats[k] for k in ("min", "max", "n_unique") if k in stats})
            if "step" in stats:
                entry["step"] = stats["step"]
        report[key] = entry
    return report


def _geometry_outlook(availability: dict) -> dict:
    """What the header availability implies for later stages - facts, not decisions."""
    def varying(key):
        return availability.get(key, {}).get("state") == "varying"

    source_coords = varying("sx")
    receiver_coords = varying("gx")
    cdp_state = availability.get("cdp", {}).get("state")
    notes = []
    if not source_coords:
        notes.append("sx does not vary; source positions cannot be taken from the headers.")
    if not receiver_coords:
        notes.append("gx does not vary; receiver positions cannot be taken from the headers.")
    if cdp_state in ("zero", "absent"):
        notes.append("cdp is not populated; CMP bins must be computed before sorting or stacking.")
    elif cdp_state == "constant":
        notes.append("cdp is constant across every trace, which cannot be a real bin numbering.")
    else:
        notes.append("cdp varies, but a populated cdp is not evidence that it is correct; "
                     "it has to be checked against the coordinates in v0.3.")
    if availability.get("scalco", {}).get("state") == "zero":
        notes.append("scalco is 0; coordinates are read as written, with no scaling applied.")
    if availability.get("counit", {}).get("state") in ("zero", "absent"):
        notes.append("counit is not set; coordinate units are unconfirmed.")
    return {
        "source_coords_vary": source_coords,
        "receiver_coords_vary": receiver_coords,
        "cdp_state": cdp_state,
        "notes": notes,
    }


def _record_header_capabilities(manifest, scan, run_id, su_path):
    availability = header_availability(scan)
    outlook = _geometry_outlook(availability)
    evidence.set_capability(
        manifest, "headers.parsed", evidence.PASS,
        {"ns": scan["ns"], "dt_us": scan["dt_us"], "ntr": scan["ntr"],
         "availability": availability, "outlook": outlook},
        IMPORTER_VERSION, run_id, artifact=as_rel(su_path),
        notes=outlook["notes"],
    )
    return availability, outlook


def _write_report(manifest, report: dict, run_id: str) -> Path:
    out_dir = config.WORK_DIR / manifest["dataset_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "import_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence.add_artifact(manifest, "import_report", path, "report", run_id)
    return path


def register_su(dataset_id: str, su_file: str, description: str = "") -> dict:
    """Register a dataset that is already in SU form, without converting anything."""
    run_id = provenance.new_run_id()
    dataset_id = evidence._check_id(dataset_id)
    if evidence.exists(dataset_id):
        raise evidence.DatasetError(f"Dataset {dataset_id!r} already exists.")
    path = safe_input_path(su_file)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {su_file}")
    scan = sufile.scan(path, keys=HEADER_KEYS_OF_INTEREST + ("tracl",))

    manifest = evidence.create(dataset_id, path, "su", run_id, description)
    evidence.add_artifact(manifest, "su", path, "imported", run_id)
    evidence.set_capability(manifest, "dataset.registered", evidence.PASS,
                            {"source": as_rel(path), "kind": "su"},
                            IMPORTER_VERSION, run_id)
    evidence.set_capability(
        manifest, "dataset.imported", evidence.PASS,
        {"note": "The source is already an SU file; no conversion was needed.",
         "ntr": scan["ntr"], "sha256": manifest["source"].get("sha256")},
        IMPORTER_VERSION, run_id, artifact=as_rel(path))
    availability, outlook = _record_header_capabilities(manifest, scan, run_id, path)

    # Nothing external to compare against, so consistency is asserted only between the trace headers and the file
    # length, which sufile already did.
    evidence.set_capability(
        manifest, "headers.sampling_consistent", evidence.PASS,
        {"ns": scan["ns"], "dt_us": scan["dt_us"],
         "checked_against": "SU trace headers and file length"},
        IMPORTER_VERSION, run_id)
    evidence.set_capability(
        manifest, "headers.trace_count_consistent", evidence.PASS,
        {"ntr": scan["ntr"], "checked_against": "file length / (240 + 4*ns)"},
        IMPORTER_VERSION, run_id)

    report = {"dataset_id": dataset_id, "kind": "su", "source": as_rel(path),
              "scan": scan, "header_availability": availability,
              "geometry_outlook": outlook}
    _write_report(manifest, report, run_id)
    evidence.save(manifest)
    provenance.record({"run_id": run_id, "kind": "register_su", "status": "success",
                       "dataset_id": dataset_id, "input": as_rel(path)})
    return manifest


def import_segy(dataset_id: str, segy_file: str, description: str = "",
                endian: int | None = None, ns_override: int | None = None,
                force_format: int | None = None) -> dict:
    """Diagnose a SEG-Y file, convert it with segyread, then verify the result."""
    run_id = provenance.new_run_id()
    # Refuse a taken id before converting anything: the old order spent the whole segyread on a file it was then
    # going to reject, and it overwrote the existing dataset's SU file on the way.
    dataset_id = evidence._check_id(dataset_id)
    if evidence.exists(dataset_id):
        raise evidence.DatasetError(f"Dataset {dataset_id!r} already exists.")
    src = safe_input_path(segy_file)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {segy_file}")

    diag = segy.diagnose(src)
    if not diag["segyread_can_convert"] and force_format is None:
        raise ValueError(
            f"Sample format {diag['sample_format_code']} "
            f"({diag['sample_format']}) is not one segyread converts on its own. "
            "Re-run with force_format= once the correct format is known."
        )

    out_dir = config.WORK_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    su_path = out_dir / f"{dataset_id}.su"
    hfile = out_dir / "textual_header.txt"
    bfile = out_dir / "binary_header.bin"
    xfile = out_dir / "extended_headers.bin"

    args = [f"tape={src}", f"hfile={hfile}", f"bfile={bfile}", f"xfile={xfile}"]
    # segyread's endian= is the *machine's* byte order, not the file's: it swaps when endian=0.
    if endian is None:
        same_order = diag["byte_order"] == sys.byteorder[:3].replace("lit", "little")
        args.append(f"endian={1 if same_order else 0}")
    else:
        args.append(f"endian={int(endian)}")
    if ns_override:
        args.append(f"ns={int(ns_override)}")
    if force_format:
        args += ["over=1", f"format={int(force_format)}"]

    with provenance.Timer() as timer:
        result = runner.run_trusted("segyread", args, stdout_path=su_path)

    scan = sufile.scan(su_path, keys=HEADER_KEYS_OF_INTEREST + ("tracl",))

    # --- verification: the SU file must still describe the same survey --------
    checks = {
        "ns": {"segy": diag["ns"], "su": scan["ns"], "match": diag["ns"] == scan["ns"]},
        "dt_us": {"segy": diag["dt_us"], "su": scan["dt_us"],
                  "match": diag["dt_us"] == scan["dt_us"]},
        "traces": {"segy": diag["traces_estimated"], "su": scan["ntr"],
                   "match": diag["traces_estimated"] in (None, scan["ntr"])},
    }
    sampling_ok = checks["ns"]["match"] and checks["dt_us"]["match"]
    count_ok = checks["traces"]["match"]

    manifest = evidence.create(dataset_id, src, "segy", run_id, description)
    evidence.add_artifact(manifest, "su", su_path, "imported", run_id,
                          parents=[manifest["source"]["path"]])
    for name, path in (("textual_header", hfile), ("binary_header", bfile)):
        if path.exists() and path.stat().st_size:
            evidence.add_artifact(manifest, name, path, "source_header", run_id)
    if xfile.exists() and xfile.stat().st_size == 0:
        xfile.unlink()

    evidence.set_capability(manifest, "dataset.registered", evidence.PASS,
                            {"source": as_rel(src), "kind": "segy",
                             "sha256": manifest["source"].get("sha256")},
                            IMPORTER_VERSION, run_id)
    evidence.set_capability(
        manifest, "dataset.imported", evidence.PASS,
        {"byte_order": diag["byte_order"], "sample_format": diag["sample_format"],
         "revision": diag["revision"], "argv": result["argv"],
         "elapsed_s": timer.seconds, "su_sha256": provenance.file_fingerprint(su_path).get("sha256")},
        IMPORTER_VERSION, run_id, artifact=as_rel(su_path),
        notes=diag["warnings"])
    evidence.set_capability(
        manifest, "headers.sampling_consistent",
        evidence.PASS if sampling_ok else evidence.FAIL,
        {"ns": checks["ns"], "dt_us": checks["dt_us"],
         "checked_against": "SEG-Y binary header"},
        IMPORTER_VERSION, run_id,
        notes=[] if sampling_ok else
        ["ns or dt changed during import; do not process this dataset until the "
         "SEG-Y header layout is understood."])
    evidence.set_capability(
        manifest, "headers.trace_count_consistent",
        evidence.PASS if count_ok else evidence.FAIL,
        {"traces": checks["traces"], "checked_against": "SEG-Y file length"},
        IMPORTER_VERSION, run_id,
        notes=[] if count_ok else
        ["The imported trace count differs from what the SEG-Y file size implies."])
    availability, outlook = _record_header_capabilities(manifest, scan, run_id, su_path)

    report = {"dataset_id": dataset_id, "kind": "segy", "source": as_rel(src),
              "segy_diagnosis": diag, "segyread_argv": result["argv"],
              "verification": checks, "scan": scan,
              "header_availability": availability, "geometry_outlook": outlook,
              "segyread_stderr": result["stderr"]}
    _write_report(manifest, report, run_id)
    evidence.save(manifest)

    provenance.record({
        "run_id": run_id, "kind": "import_segy",
        "status": "success" if sampling_ok and count_ok else "verification_failed",
        "dataset_id": dataset_id, "input": as_rel(src), "output": as_rel(su_path),
        "elapsed_s": timer.seconds, "argv": result["argv"],
        "verification": checks,
        "output_file": provenance.file_fingerprint(su_path),
    })
    return manifest
