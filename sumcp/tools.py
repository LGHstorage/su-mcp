"""The tool layer."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import (acqstatics, analysis, arrayfit, cmp, config, evidence, geometry, ingest, migrate,
               iterate, measure, overview, preview, provenance, reflection, runner,
               sanity, segy, sps, stack, sufile, suenv)
from .paths import PathPolicyError, as_rel, safe_input_path, safe_output_path

__all__ = [
    "su_status", "su_search", "su_help", "su_inspect", "su_run",
    "su_pipeline", "su_preview", "su_list_files", "su_log",
    "segy_inspect", "dataset_register_su", "dataset_import_segy",
    "dataset_list", "dataset_manifest",
    "geometry_analyze", "inspect_external_geometry", "assign_external_geometry",
    "measure_apparent_velocity", "scan_coherence",
    "fit_channel_geometry", "assess_reflection_feasibility",
    "build_cmp", "sort_cmp", "dataset_forget",
    "pick_velocity", "apply_nmo", "stack_cmp",
    "fit_array_geometry", "export_product", "survey_overview",
    "conditioning_menu", "condition_gathers", "refine_velocity",
    "migrate_stack",
]

_POLICY_ERRORS = (PathPolicyError, runner.CommandNotAllowed,
                  runner.ParameterError, runner.SURunError,
                  sufile.SUFormatError, evidence.PrerequisiteError,
                  FileNotFoundError, ValueError, KeyError)


# True/False/None -> the three manifest statuses.
_STATUS = {True: evidence.PASS, False: evidence.FAIL, None: evidence.UNKNOWN}


def _fail(error, **extra) -> dict:
    return {"ok": False, "error": str(error), "error_type": type(error).__name__, **extra}


def _log_reject(kind: str, run_id: str, error, request: dict) -> None:
    """A second, command-level line for a refused su_run or su_pipeline."""
    provenance.record({
        "run_id": run_id, "kind": kind, "status": "rejected",
        "error": str(error), "error_type": type(error).__name__,
        "request": request,
    })


# --------------------------------------------------------------------------- Environment and
# documentation,-------------------------------------------------------------------------

def su_status() -> dict:
    """Report the SU installation and the project directories."""
    core = ["surange", "sugethw", "suwind", "sugain", "sufilter", "susort",
            "sudoc", "sufind", "segyread", "sunmo", "sustack", "suvelan"]
    found = {name: suenv.find_program(name) for name in core}
    missing = [n for n in config.ALLOWED_SU_COMMANDS if found.get(n) is None]
    dirs = {}
    for d in config.PROJECT_DIRS:
        dirs[d.name] = {"path": str(d), "exists": d.is_dir(),
                        "files": len([p for p in d.glob("*") if p.is_file()]) if d.is_dir() else 0}
    notes = []
    # work/ moved off the Windows drive in v0.4.
    legacy = config.ROOT / "work"
    if (config.RUNTIME_ROOT != config.ROOT and legacy.is_dir()
            and any(legacy.iterdir())):
        notes.append(
            f"{legacy} holds products from before work/ moved to "
            f"{config.WORK_DIR}. Datasets imported then must be imported again; "
            f"the old directory is not read and can be deleted once nothing "
            f"needs it.")

    return {
        "ok": not missing,
        "cwproot": str(suenv.cwproot()) if suenv.cwproot() else None,
        "programs_installed": len(suenv.list_programs()),
        "programs": found,
        "allowed_commands": sorted(config.ALLOWED_SU_COMMANDS),
        "missing_allowed_commands": sorted(missing),
        "project_root": str(config.ROOT),
        "runtime_root": str(config.RUNTIME_ROOT),
        "directories": dirs,
        "datasets": evidence.list_datasets(),
        "su_output_byte_order": suenv.su_output_byte_order(),
        "version": config.VERSION,
        # The analysis modules are imported by the worker, not by the server, so these report the code the NEXT
        # tool call will actually run, which is the point of the worker, and the way to check it took.
        "algorithm_versions": {
            "geometry": geometry.GEOMETRY_VERSION,
            "measure": measure.MEASURE_VERSION,
            "reflection": reflection.REFLECTION_VERSION,
            "arrayfit": arrayfit.ARRAYFIT_VERSION,
        },
        "notes": notes,
    }


def su_search(keyword: str, mode: str = "synopsis") -> dict:
    """Search SU's self-documentation."""
    flags = {"synopsis": [], "name": ["-n"], "verbose": ["-v"]}
    if mode not in flags:
        return _fail(ValueError(f"mode must be one of {sorted(flags)}"))
    if not keyword or not str(keyword).strip():
        return _fail(ValueError("keyword is required"))
    try:
        text = runner.capture_text("sufind", flags[mode] + [str(keyword)],
                                   allowlisted=False)
    except (subprocess.TimeoutExpired, *_POLICY_ERRORS) as exc:
        return _fail(exc)
    return {"ok": True, "keyword": keyword, "mode": mode,
            "result": text.strip() or "(no match)"}


def su_help(program: str) -> dict:
    """Return the SU self-documentation for one program."""
    if not program or not str(program).replace("_", "").isalnum():
        return _fail(ValueError("program must be a bare SU program name"))
    if suenv.find_program(program) is None:
        return _fail(ValueError(f"No such SU program: {program}"))
    try:
        text = runner.capture_text("sudoc", [program], allowlisted=False)
    except (subprocess.TimeoutExpired, *_POLICY_ERRORS) as exc:
        return _fail(exc)
    return {
        "ok": True,
        "program": program,
        "allowed_in_this_version": program in config.ALLOWED_SU_COMMANDS,
        "doc": text.strip(),
    }


# --------------------------------------------------------------------------- Data
# inspection,-------------------------------------------------------------------------

def su_inspect(input_file: str, run_surange: bool = True) -> dict:
    """Inspect an SU file: sampling, trace count, header ranges, fold."""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        report = sufile.scan(path)
    except _POLICY_ERRORS as exc:
        return _fail(exc)

    out = {"ok": True, "input": as_rel(path), "structured": report}
    if run_surange:
        try:
            out["surange"] = runner.capture_text(
                "surange", stdin_path=path, timeout=config.TIMEOUT_INSPECT).strip()
        except (subprocess.TimeoutExpired, *_POLICY_ERRORS) as exc:
            out["surange_error"] = str(exc)

    notes = []
    if not report.get("has_cdp"):
        notes.append("cdp is not set; CMP sorting and stacking need geometry first.")
    if report["keys"].get("scalco", {}).get("constant") and \
            report["keys"].get("scalco", {}).get("min") == 0:
        notes.append("scalco is 0; coordinates are taken as written, with no scaling.")
    if report["keys"].get("offset", {}).get("constant"):
        notes.append("offset is constant; this looks like a stacked or single-offset section.")
    out["notes"] = notes
    return out


def su_list_files(directory: str = "") -> dict:
    """List the data files the agent may read."""
    dirs = config.READABLE_DIRS
    if directory:
        dirs = [d for d in config.READABLE_DIRS if d.name == directory.strip("/")]
        if not dirs:
            return _fail(ValueError(
                f"directory must be one of {[d.name for d in config.READABLE_DIRS]}"))
    listing = {}
    for d in dirs:
        entries = []
        if d.is_dir():
            for p in sorted(d.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    entries.append({"path": as_rel(p), "bytes": p.stat().st_size})
        listing[d.name] = entries
    return {"ok": True, "root": str(config.ROOT), "files": listing}


def su_log(limit: int = 20) -> dict:
    """Recent entries from the processing log."""
    return {"ok": True, "log": str(config.PROCESSING_LOG),
            "entries": provenance.read_log(int(limit))}


# ---------------------------------------------------------------------------
# Processing,-------------------------------------------------------------------------

def _log_run(kind, run_id, infile, outfile, detail, elapsed, status, error=None):
    entry = {
        "run_id": run_id,
        "kind": kind,
        "status": status,
        "input": as_rel(infile),
        "output": as_rel(outfile),
        "elapsed_s": elapsed,
        **detail,
    }
    if status == "success":
        entry["output_file"] = provenance.file_fingerprint(outfile)
        entry["input_file"] = provenance.file_fingerprint(infile)
    if error:
        entry["error"] = str(error)
    return provenance.record(entry)


def su_run(command: str, input_file: str, output_file: str,
           params: dict | None = None, overwrite: bool = False) -> dict:
    """Run one allowlisted SU program: input_file -> output_file."""
    run_id = provenance.new_run_id()
    try:
        infile = safe_input_path(input_file)
        if not infile.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        outfile = safe_output_path(output_file, overwrite=overwrite)
        runner.resolve_command(command)
        argv_preview = runner.validate_params(params)
    except _POLICY_ERRORS as exc:
        _log_reject("su_run", run_id, exc, {"command": command, "input": input_file,
                                            "output": output_file, "params": params})
        return _fail(exc, run_id=run_id)

    detail = {"command": command, "parameters": params or {}, "argv": argv_preview}
    try:
        with provenance.Timer() as timer:
            result = runner.run_single(command, infile, outfile, params)
    except subprocess.TimeoutExpired as exc:
        _log_run("su_run", run_id, infile, outfile, detail, None, "timeout", exc)
        return _fail(exc, run_id=run_id)
    except _POLICY_ERRORS as exc:
        outfile.unlink(missing_ok=True)       # never leave a truncated product
        _log_run("su_run", run_id, infile, outfile, detail, None, "failed", exc)
        return _fail(exc, run_id=run_id)

    entry = _log_run("su_run", run_id, infile, outfile, detail, timer.seconds, "success")
    return {
        "ok": True, "run_id": run_id, "command": command,
        "input": as_rel(infile), "output": as_rel(outfile),
        "parameters": params or {}, "shell_equivalent":
            f"{command} {' '.join(argv_preview)} < {as_rel(infile)} > {as_rel(outfile)}".replace("  ", " "),
        "elapsed_s": timer.seconds,
        "output_bytes": entry["output_file"]["bytes"],
        "stderr": result["stderr"],
    }


def su_pipeline(input_file: str, output_file: str, steps: list,
                overwrite: bool = False) -> dict:
    """Run several allowlisted SU programs joined by pipes."""
    run_id = provenance.new_run_id()
    try:
        infile = safe_input_path(input_file)
        if not infile.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        outfile = safe_output_path(output_file, overwrite=overwrite)
        if not isinstance(steps, list) or not steps:
            raise ValueError("steps must be a non-empty list of {command, params}")
        rendered = []
        for step in steps:
            runner.resolve_command(step.get("command", ""))
            rendered.append({"command": step["command"],
                             "argv": runner.validate_params(step.get("params"))})
    except _POLICY_ERRORS as exc:
        _log_reject("su_pipeline", run_id, exc, {"input": input_file,
                                                 "output": output_file, "steps": steps})
        return _fail(exc, run_id=run_id)

    detail = {"steps": [{"command": s["command"], "parameters": s.get("params", {})}
                        for s in steps]}
    try:
        with provenance.Timer() as timer:
            runner.run_chain(steps, infile, outfile)
    except subprocess.TimeoutExpired as exc:
        _log_run("su_pipeline", run_id, infile, outfile, detail, None, "timeout", exc)
        return _fail(exc, run_id=run_id)
    except _POLICY_ERRORS as exc:
        outfile.unlink(missing_ok=True)
        _log_run("su_pipeline", run_id, infile, outfile, detail, None, "failed", exc)
        return _fail(exc, run_id=run_id)

    entry = _log_run("su_pipeline", run_id, infile, outfile, detail, timer.seconds, "success")
    chain = " | ".join(f"{s['command']} {' '.join(s['argv'])}".strip() for s in rendered)
    return {
        "ok": True, "run_id": run_id,
        "input": as_rel(infile), "output": as_rel(outfile),
        "steps": detail["steps"],
        "shell_equivalent": f"< {as_rel(infile)} {chain} > {as_rel(outfile)}",
        "elapsed_s": timer.seconds,
        "output_bytes": entry["output_file"]["bytes"],
    }


def su_preview(input_file: str, output_png: str, fldr: int | None = None,
               cdp: int | None = None, start: int = 0, count: int | None = None,
               perc: float = 99.0, mode: str = "image", gain: str = "none",
               title: str | None = None, overwrite: bool = True) -> dict:
    """Render a QC image of an SU file into qc/."""
    run_id = provenance.new_run_id()
    try:
        infile = safe_input_path(input_file)
        if not infile.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        outfile = safe_output_path(output_png, overwrite=overwrite)
        if outfile.suffix.lower() != ".png":
            raise ValueError("output_png must end in .png")
        if mode not in ("image", "wiggle"):
            raise ValueError("mode must be 'image' or 'wiggle'")
        if gain not in ("none", "agc"):
            raise ValueError("gain must be 'none' or 'agc'")
        with provenance.Timer() as timer:
            info = preview.render(infile, outfile, fldr=fldr, cdp=cdp, start=start,
                                  count=count, perc=perc, mode=mode, gain=gain,
                                  title=title)
    except _POLICY_ERRORS as exc:
        _log_reject("su_preview", run_id, exc, {"input": input_file, "output": output_png})
        return _fail(exc, run_id=run_id)

    provenance.record({
        "run_id": run_id, "kind": "su_preview", "status": "success",
        "input": as_rel(infile), "output": as_rel(outfile),
        "elapsed_s": timer.seconds, "preview": info,
    })
    info["png"] = as_rel(outfile)
    return {"ok": True, "run_id": run_id, "input": as_rel(infile),
            "elapsed_s": timer.seconds, **info}


# --------------------------------------------------------------------------- v0.2 - datasets: identity, import,
# evidence,-------------------------------------------------------------------------

def segy_inspect(input_file: str, textual_header: bool = False) -> dict:
    """Diagnose a SEG-Y file without importing it."""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        report = segy.diagnose(path)
    except (segy.SEGYError, *_POLICY_ERRORS) as exc:
        return _fail(exc)
    if not textual_header:
        report["textual_header"] = report["textual_header"][:400] + \
            ("..." if len(report["textual_header"]) > 400 else "")
    return {"ok": True, "input": as_rel(path), **report}


def dataset_register_su(dataset_id: str, su_file: str, description: str = "") -> dict:
    """Register an SU file as a dataset, with a manifest, without converting it."""
    try:
        manifest = ingest.register_su(dataset_id, su_file, description)
    except (evidence.DatasetError, *_POLICY_ERRORS) as exc:
        return _fail(exc)
    return {"ok": True, **evidence.summary(manifest),
            "capabilities": {k: v["status"] for k, v in manifest["capabilities"].items()},
            "notes": manifest["capabilities"]["headers.parsed"]["notes"]}


def dataset_import_segy(dataset_id: str, segy_file: str, description: str = "",
                        endian: int | None = None, ns_override: int | None = None,
                        force_format: int | None = None) -> dict:
    """Import a SEG-Y file into the project as a dataset, then verify the import."""
    try:
        manifest = ingest.import_segy(dataset_id, segy_file, description,
                                      endian=endian, ns_override=ns_override,
                                      force_format=force_format)
    except (segy.SEGYError, evidence.DatasetError, subprocess.TimeoutExpired,
            *_POLICY_ERRORS) as exc:
        return _fail(exc)
    statuses = {k: v["status"] for k, v in manifest["capabilities"].items()}
    failed = [k for k, v in statuses.items() if v == evidence.FAIL]
    return {
        "ok": not failed,
        **evidence.summary(manifest),
        "capabilities": statuses,
        "verification_failed": failed,
        "notes": (manifest["capabilities"]["dataset.imported"]["notes"]
                  + manifest["capabilities"]["headers.parsed"]["notes"]),
    }


def dataset_list() -> dict:
    """List the registered datasets and how far each has been validated."""
    out = []
    for dataset_id in evidence.list_datasets():
        try:
            manifest = evidence.load(dataset_id)
        except evidence.DatasetError:
            continue
        summary = evidence.summary(manifest)
        out.append({"dataset_id": dataset_id,
                    "description": summary["description"],
                    "source": summary["source"]["path"],
                    "capabilities_pass": summary["capabilities_pass"],
                    "capabilities_fail": summary["capabilities_fail"],
                    "updated": summary["updated"]})
    return {"ok": True, "datasets": out}


def dataset_manifest(dataset_id: str, section: str = "summary") -> dict:
    """Read a dataset manifest."""
    try:
        manifest = evidence.load(dataset_id)
    except evidence.DatasetError as exc:
        return _fail(exc)
    if section == "summary":
        return {"ok": True, **evidence.summary(manifest)}
    if section == "capabilities":
        return {"ok": True, "dataset_id": dataset_id,
                "capabilities": manifest["capabilities"],
                "vocabulary": evidence.CAPABILITIES}
    if section in ("artifacts", "history"):
        return {"ok": True, "dataset_id": dataset_id, section: manifest[section]}
    if section == "full":
        return {"ok": True, **manifest}
    return _fail(ValueError(
        "section must be summary, capabilities, artifacts, history or full"))


# --------------------------------------------------------------------------- v0.3 - geometry: measured, not
# assumed,-------------------------------------------------------------------------

def geometry_analyze(dataset_id: str, measure_fldr: int | None = None,
                     measure_tmin: float | None = None,
                     measure_tmax: float | None = None,
                     trend_shots: int = 20,
                     water_velocity: float = 1500.0) -> dict:
    """Resolve coordinates, test the receiver headers against the data, classify."""
    try:
        result = analysis.analyze_geometry(
            dataset_id, measure_fldr=measure_fldr, measure_tmin=measure_tmin,
            measure_tmax=measure_tmax, trend_shots=trend_shots,
            water_velocity=water_velocity)
    except (evidence.DatasetError, evidence.PrerequisiteError, *_POLICY_ERRORS) as exc:
        return _fail(exc)
    manifest = evidence.load(dataset_id)
    return {
        "ok": True,
        "run_id": result["run_id"],
        "dataset_id": dataset_id,
        "report": result["report"],
        "classification": result["classification"],
        "coordinates": {k: result["coordinates"][k] for k in
                        ("scalco_values", "counit_values", "units_are_lengths",
                         "coordinate_shape", "notes")},
        "receiver_variation": {k: result["receiver_variation"][k] for k in
                               ("trace_sort", "n_shots", "n_channels",
                                "receiver_coordinate_state",
                                "receiver_coordinate_state_note",
                                "every_channel_moves", "every_channel_fixed",
                                "receiver_positions", "receiver_extent_m",
                                "channel_spacing_m", "channel_spacing_source",
                                "array_length_m", "array_length_note")},
        "offsets": {k: result["offsets"][k] for k in
                    ("header_state", "agrees") if k in result["offsets"]},
        "cdp": {k: result["cdp"][k] for k in ("level", "reason")},
        "apparent_velocity": result["apparent_velocity"],
        "arrival_time_trend": None if result["arrival_time_trend"] is None else
            {k: v for k, v in result["arrival_time_trend"].items() if k != "per_shot"},
        "velocity_cross_check": result["velocity_cross_check"],
        "capabilities": {k: v["status"] for k, v in manifest["capabilities"].items()},
    }


@provenance.audited("inspect_external_geometry")
def inspect_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                              xps_file: str) -> dict:
    """Read a standard SPS/RPS/XPS acquisition set and report what it would do."""
    try:
        return {"ok": True, **analysis.inspect_external_geometry(
            dataset_id, sps_file, rps_file, xps_file)}
    except (evidence.DatasetError, evidence.PrerequisiteError,
            sps.SPSError, ValueError, KeyError, *_POLICY_ERRORS) as exc:
        return _fail(exc)


@provenance.audited("assign_external_geometry")
def assign_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                             xps_file: str, overwrite: bool = False) -> dict:
    """Attach a standard SPS/RPS/XPS acquisition set to a dataset."""
    try:
        return {"ok": True, **analysis.assign_external_geometry(
            dataset_id, sps_file, rps_file, xps_file, overwrite=overwrite)}
    except (evidence.DatasetError, evidence.PrerequisiteError,
            sps.SPSError, ValueError, KeyError, *_POLICY_ERRORS) as exc:
        return _fail(exc)


def measure_apparent_velocity(input_file: str, fldr: int | None = None,
                              cdp: int | None = None, tmin: float | None = None,
                              tmax: float | None = None,
                              channel_spacing_m: float | None = None,
                              max_slope_ms: float = 8.0) -> dict:
    """Slant-stack one ensemble and report where it is most coherent."""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        result = measure.apparent_velocity(
            path, fldr=fldr, cdp=cdp, tmin=tmin, tmax=tmax,
            max_slope_ms=max_slope_ms, channel_spacing_m=channel_spacing_m)
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "input": as_rel(path), **result}


def scan_coherence(input_file: str, fldr: int | None = None, cdp: int | None = None,
                   t_start: float | None = None, t_end: float | None = None,
                   window_s: float = 0.2, step_s: float = 0.05,
                   band_low: float = 40.0, band_high: float = 120.0,
                   channel_spacing_m: float | None = None,
                   min_contrast: float = 1.8) -> dict:
    """Slide a window down the record and list every coherent arrival found."""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        result = measure.coherence_scan(
            path, fldr=fldr, cdp=cdp, t_start=t_start, t_end=t_end,
            window_s=window_s, step_s=step_s,
            band=(band_low, band_high) if band_low and band_high else None,
            channel_spacing_m=channel_spacing_m, min_contrast=min_contrast)
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "input": as_rel(path),
            **{k: v for k, v in result.items() if not k.startswith("_")}}


def fit_channel_geometry(input_file: str, velocity: float = 1492.0,
                         band_low: float = 40.0, band_high: float = 200.0,
                         window_s: float = 0.25, min_contrast: float = 1.5,
                         channel_spacing_m: float | None = None) -> dict:
    """Test whether the header geometry alone explains the channel moveout."""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        geom = sufile.geometry(path)
        spacing = channel_spacing_m
        if spacing is None:
            resolved = geometry.resolve_coordinates(path, geom)
            spacing = geometry.receiver_variation(resolved)["channel_spacing_m"]
        result = measure.channel_geometry_fit(
            path, velocity=velocity, band=(band_low, band_high),
            tmin_window_s=window_s, min_contrast=min_contrast, geom=geom,
            spacing_m=spacing, sample_interval_s=geom["dt_s"])
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "input": as_rel(path), **result}


def assess_reflection_feasibility(
        input_file: str, channel: int | None = None, fldr: int | None = None,
        cdp: int | None = None,
        water_velocity: float = 1492.0, band_low: float = 30.0,
        band_high: float = 250.0, max_traces: int = 400,
        probe_t0_s: float | None = None, probe_velocity: float | None = None,
        run_sensitivity: bool = True, dataset_id: str | None = None) -> dict:
    """Can this gather yield a reflection at all?"""
    try:
        path = safe_input_path(input_file)
        if not path.exists():
            return _fail(FileNotFoundError(f"File not found: {input_file}"))
        chosen = [(k, v) for k, v in (("tracf", channel), ("fldr", fldr),
                                      ("cdp", cdp)) if v is not None]
        if len(chosen) != 1:
            raise ValueError(
                "Choose exactly one gather: channel=<tracf> for a common-receiver "
                "walkaway, fldr=<shot> for one shot record, or cdp=<bin> for one "
                f"CMP gather. Given: {len(chosen)}.")
        import numpy as np
        geom = sufile.geometry(path)
        resolved = geometry.resolve_coordinates(path, geom)
        s, raw = resolved["_scaled"], resolved["_raw"]
        offsets = np.hypot(s["gx"] - s["sx"], s["gy"] - s["sy"])
        key, want = chosen[0]
        sel = np.flatnonzero(np.asarray(raw[key]) == want)
        if sel.size < 20:
            raise ValueError(
                f"{key}={want} selects {sel.size} traces; the semblance scan needs "
                f"at least 20 and is only meaningful with many more.")
        sel = sel[np.argsort(offsets[sel])][:max_traces]
        data = np.nan_to_num(np.asarray(sufile.read_traces(path, sel, geom),
                                        dtype=np.float64))
        result = reflection.assess(
            data, offsets[sel], geom["dt_s"], geom["t_start_s"],
            water=water_velocity, f_lo=band_low, f_hi=band_high,
            probe=(None if probe_t0_s is None or probe_velocity is None
                   else (probe_t0_s, probe_velocity)),
            run_sensitivity=run_sensitivity)
    except _POLICY_ERRORS as exc:
        return _fail(exc)

    out = {"ok": True, "input": as_rel(path), "gather": {key: want}, **result}
    if dataset_id:
        try:
            manifest = evidence.load(dataset_id)
            run_id = provenance.new_run_id()
            gather = {key: int(want)}
            # Feasibility is a property of a GATHER, and the manifest holds one entry per capability.
            previous = manifest.get("capabilities", {}).get(
                "reflection.processing_feasible")
            superseded = None
            if previous and previous.get("evidence", {}).get("gather") not in (
                    None, gather):
                superseded = (
                    f"Supersedes a measurement on gather "
                    f"{previous['evidence']['gather']}, which gave "
                    f"{previous['evidence'].get('verdict', previous['status'])}"
                    f". Feasibility is a property of the gather it was measured "
                    f"on; the two do not have to agree.")
            evidence.set_capability(
                manifest, "reflection.direct_wave_suppressed", evidence.PASS,
                {"gather": gather}
                | {name: {k: v for k, v in b.items() if k != "peaks"}
                   for name, b in result["branches"].items()},
                reflection.REFLECTION_VERSION, run_id)
            # Three verdicts, three statuses.
            verdict = result["REFLECTION_PROCESSING_FEASIBLE"]
            evidence.set_capability(
                manifest, "reflection.processing_feasible",
                {"PASS": evidence.PASS, "FAIL": evidence.FAIL}.get(
                    verdict, evidence.UNKNOWN),
                {"gather": gather,
                 "verdict": verdict,
                 "reason": result["feasibility_reason"],
                 "agreed_candidates": result["agreed_candidates"],
                 "detection_threshold_x_rms": result["detection_threshold_x_rms"],
                 "direct_wave_stack_peak": result["direct_wave_stack_peak"],
                 "analysis_band": result.get("analysis_band")},
                reflection.REFLECTION_VERSION, run_id,
                notes=([superseded] if superseded else []) + result["notes"])
            # v0.15: the direct wave's own clock.
            tz = result.get("time_zero") or {
                "status": "UNKNOWN",
                "reason": "not measured on this gather"}
            evidence.set_capability(
                manifest, "acquisition.time_zero_consistent",
                {"PASS": evidence.PASS, "FAIL": evidence.FAIL}.get(
                    tz.get("status"), evidence.UNKNOWN),
                {"gather": gather, **tz},
                tz.get("algorithm_version", reflection.REFLECTION_VERSION),
                run_id, notes=[tz.get("reason", "")])
            if superseded:
                out["superseded"] = superseded
            evidence.save(manifest)
            out["dataset_id"] = dataset_id
        except _POLICY_ERRORS as exc:
            out["manifest_error"] = str(exc)
    return out


def build_cmp(dataset_id: str, bin_size_m: float | None = None,
              receiver_spacing_m: float | None = None,
              reference_velocity_m_s: float = 1800.0,
              reference_t0_s: float = 1.0, min_fold: int = 4,
              overwrite: bool = False) -> dict:
    """Assign CMP bins from the coordinates and grade whether they can be stacked."""
    try:
        return {"ok": True, **cmp.build_cmp(
            dataset_id, bin_size_m=bin_size_m,
            receiver_spacing_m=receiver_spacing_m,
            reference_velocity_m_s=reference_velocity_m_s,
            reference_t0_s=reference_t0_s, min_fold=min_fold,
            overwrite=overwrite)}
    except _POLICY_ERRORS as exc:
        return _fail(exc)


def sort_cmp(dataset_id: str, overwrite: bool = False) -> dict:
    """Sort the CMP-binned file into cdp order with susort."""
    run_id = provenance.new_run_id()
    try:
        manifest = evidence.load(dataset_id)
        evidence.require(manifest, ["geometry.cmp_assigned", "geometry.fold_valid"],
                         "Sorting into CMP gathers")
        src = safe_input_path(evidence.get_artifact(manifest, "cmp")["path"])
        dst = safe_output_path(
            as_rel(config.WORK_DIR / dataset_id / f"{dataset_id}_cmp_sorted.su"),
            overwrite=overwrite)
        result = runner.run_single("susort", src, dst, {"cdp": None, "offset": None})
        # v0.32 S1: acquisition statics applied here, once, in the SEG-Y sense, gated
        use, acq = acqstatics.apply(manifest, dataset_id, dst, run_id)
        manifest["acquisition_statics"] = acq
        evidence.add_artifact(manifest, "cmp_sorted", use, "cmp-sorted",
                              parents=[as_rel(src)], run_id=run_id)
        # v0.31: Q0 as soon as the gathers exist (report; conditioning and migration act on it)
        q0 = sanity.scan(use)
        manifest["sample_check"] = q0
        evidence.save(manifest)
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "run_id": run_id, "dataset_id": dataset_id,
            "input": as_rel(src), "output": as_rel(dst),
            "output_bytes": use.stat().st_size, "sample_check": q0,
            "acquisition_statics": acq, **({"cmp_sorted": as_rel(use)} if use != dst else {}),
            **({"next": "condition_gathers [{\"op\": \"kill_corrupt\"}]: Q0 found "
                        f"{q0['corrupt_count']} corrupt trace(s) at CDP {q0['corrupt_cdps'][:10]}"}
               if q0["corrupt_count"] else {}),
            "elapsed_s": result.get("elapsed_s")}


def dataset_forget(dataset_id: str, confirm: bool = False) -> dict:
    """Delete a dataset's manifest so the identifier can be used again."""
    try:
        manifest = evidence.load(dataset_id)
        if not confirm:
            caps = manifest.get("capabilities", {})
            passed = sorted(k for k, v in caps.items() if v["status"] == "PASS")
            return {
                "ok": False, "error_type": "ConfirmationRequired",
                "error": (f"Deleting the manifest for {dataset_id!r} discards the "
                          f"evidence for {len(passed)} established capability(ies): "
                          f"{', '.join(passed) or 'none'}. Files in work/ are kept. "
                          f"Pass confirm=true to proceed."),
                "capabilities_that_would_be_lost": passed,
            }
        path = config.DATASET_DIR / f"{dataset_id}.json"
        path.unlink()
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "dataset_id": dataset_id, "forgotten": as_rel(path),
            "note": "Products in work/ were not deleted."}


def pick_velocity(dataset_id: str, n_locations: int = 5, cdp_list=None,
                  v_min: float = 1400.0, v_max: float = 5500.0,
                  v_step: float = 50.0, t_step: float = 0.04,
                  band_low: float = 5.0, band_high: float = 90.0,
                  n_points: int = 10, max_rate_m_s2: float = 2500.0) -> dict:
    """Measure a stacking velocity at several CMPs and grade every one."""
    try:
        return {"ok": True, **stack.pick_velocity(
            dataset_id, n_locations=n_locations, cdp_list=cdp_list,
            v_min=v_min, v_max=v_max, v_step=v_step, t_step=t_step,
            band_low=band_low, band_high=band_high, n_points=n_points,
            max_rate_m_s2=max_rate_m_s2)}
    except _POLICY_ERRORS as exc:
        return _fail(exc)


def apply_nmo(dataset_id: str, smute: float = 1.5,
              overwrite: bool = False) -> dict:
    """NMO with the measured velocity model, behind velocity.validated."""
    try:
        return {"ok": True, **stack.apply_nmo(dataset_id, smute=smute,
                                              overwrite=overwrite)}
    except _POLICY_ERRORS as exc:
        return _fail(exc)


def stack_cmp(dataset_id: str, overwrite: bool = False) -> dict:
    """Sum each CMP gather into one trace, behind nmo.applied."""
    try:
        return {"ok": True, **stack.stack_cmp(dataset_id, overwrite=overwrite)}
    except _POLICY_ERRORS as exc:
        return _fail(exc)


def conditioning_menu() -> dict:
    """The conditioning operations condition_gathers accepts, with their limits."""
    return {"ok": True, **iterate.conditioning_menu()}


def condition_gathers(dataset_id: str, operations: list) -> dict:
    """Up to three menu operations on the CMP gathers, behind a signal-preservation QC."""
    try:
        return {"ok": True, **iterate.condition_gathers(dataset_id, operations)}
    except _POLICY_ERRORS as exc:
        return _fail(exc)


def refine_velocity(dataset_id: str) -> dict:
    """Bounded re-analysis of the locations that failed velocity validation."""
    try:
        return {"ok": True, **iterate.refine_velocity(dataset_id)}
    except (evidence.DatasetError, *_POLICY_ERRORS) as exc:
        return _fail(exc)


def migrate_stack(dataset_id: str, method: str = migrate.DEFAULT_METHOD,
                  overwrite: bool = False) -> dict:
    """Post-stack phase-shift time migration behind the impulse gate (v0.24)."""
    try:
        return {"ok": True, **migrate.migrate_stack(dataset_id, method=method,
                                                    overwrite=overwrite)}
    except (evidence.DatasetError, *_POLICY_ERRORS) as exc:
        return _fail(exc)


def fit_array_geometry(dataset_ids: list, water_velocity: float = 1492.0,
                       band_low: float = 30.0, band_high: float = 250.0,
                       min_semblance: float = 0.30, max_shots: int | None = None,
                       bootstrap: int = 400) -> dict:
    """Decide whether the channel moveout is a spacing error or a timing delay."""
    try:
        if isinstance(dataset_ids, str):
            dataset_ids = [dataset_ids]
        if not dataset_ids:
            raise ValueError("Give at least one dataset_id.")
        lines, manifests, variations = {}, {}, {}
        for dataset_id in dataset_ids:
            manifest = evidence.load(dataset_id)
            evidence.require(manifest, ["dataset.imported",
                                        "geometry.coordinate_scale_resolved"],
                             "Array geometry fitting")
            path = safe_input_path(evidence.get_artifact(manifest, "su")["path"])
            geom = sufile.geometry(path)
            variations[dataset_id] = geometry.receiver_variation(
                geometry.resolve_coordinates(path, geom))
            lines[dataset_id] = arrayfit.measure_slopes(
                path, f_lo=band_low, f_hi=band_high, water=water_velocity,
                max_shots=max_shots)
            manifests[dataset_id] = manifest
        result = arrayfit.assess(lines, water=water_velocity,
                                 min_semblance=min_semblance,
                                 bootstrap=bootstrap)
        run_id = provenance.new_run_id()
        reclassified = {}
        for dataset_id, manifest in manifests.items():
            evidence.set_capability(
                manifest, "geometry.array_geometry_resolved",
                evidence.PASS if result["verdict"] == "RESOLVED" else evidence.UNKNOWN,
                {k: v for k, v in result.items() if k != "per_line"}
                | {"lines_used": list(lines)},
                arrayfit.ARRAYFIT_VERSION, run_id,
                notes=[result.get("reason") or result.get("cause", "")])

            # The same per-shot measurement answers a second, independent question: whether the receiver
            # coordinates are describing a real array.
            tracking = result["per_line"].get(dataset_id, {}).get("source_tracking")
            if tracking:
                trust = {arrayfit.TRACKS: True, arrayfit.NO_TRACK: False}.get(
                    tracking["verdict"])
                evidence.set_capability(
                    manifest, "geometry.receiver_positions_trustworthy",
                    _STATUS[trust],
                    {"test": "source_tracking", "line": dataset_id} | tracking,
                    arrayfit.ARRAYFIT_VERSION, run_id,
                    notes=[tracking.get("reason", "")])
                classification = geometry.classify_acquisition(
                    variations[dataset_id], tracking=tracking)
                evidence.set_capability(
                    manifest, "geometry.acquisition_classified",
                    _STATUS[geometry.classification_status(classification)],
                    classification, geometry.GEOMETRY_VERSION, run_id,
                    notes=[classification["reason"]] + classification["unresolved"])
                reclassified[dataset_id] = {
                    "receiver_positions_trustworthy": trust,
                    "acquisition": classification["kind"],
                    "candidate": classification["candidate"],
                    "status": classification["status"],
                    "reason": classification["reason"],
                }
            evidence.save(manifest)
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, "datasets": list(lines), **result,
            "receiver_positions": reclassified}


def survey_overview(dataset_ids: list | None = None) -> dict:
    """Where does this survey stand, across every line at once?"""
    try:
        if isinstance(dataset_ids, str):
            dataset_ids = [dataset_ids]
        result = overview.survey(dataset_ids)
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    return {"ok": True, **result}


def export_product(dataset_id: str, artifact: str, output_name: str = "",
                   overwrite: bool = False) -> dict:
    """Copy a product out of work/ into results/, where it can be looked at."""
    try:
        manifest = evidence.load(dataset_id)
        entry = evidence.get_artifact(manifest, artifact)
        src = safe_input_path(entry["path"])
        name = output_name or f"{dataset_id}_{artifact}{Path(entry['path']).suffix}"
        dst = safe_output_path(as_rel(config.RESULT_DIR / name),
                               overwrite=overwrite)
        dst.write_bytes(src.read_bytes())
    except _POLICY_ERRORS as exc:
        return _fail(exc)
    stale = evidence.superseded(manifest, artifact)
    return {"ok": True, "dataset_id": dataset_id, "artifact": artifact,
            "source": as_rel(src), "output": as_rel(dst),
            "bytes": dst.stat().st_size,
            **({"superseded": stale,
                "warning": "this product was made before " + stale["reason"]
                           + " (I1); it does not describe the current stack"} if stale else {})}


# ---------------------------------------------------------------------------
# Audit,------------------------------------------------------------------------- Applied last, to every public
# tool, so that adding a tool cannot forget to log itself: one entry per call, whether it succeeded, was refused
# at a gate, or raised.

_AUDIT_EXEMPT = {
    "su_status", "su_search", "su_help", "su_log", "su_list_files",
    "dataset_list", "dataset_manifest", "conditioning_menu",
}

for _tool in __all__:
    if _tool not in _AUDIT_EXEMPT:
        globals()[_tool] = provenance.audited(_tool)(globals()[_tool])
del _tool
