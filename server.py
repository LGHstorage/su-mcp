#!/usr/bin/env python3
"""Seismic Unix MCP server.

A thin MCP surface over sumcp/.  Everything with behaviour lives in the
package, so it can be tested without an MCP client; this file only describes
the tools to the model.

Run it directly (stdio transport):

    CWPROOT=/path/to/cwp SU_MCP_ROOT=/path/to/su-mcp python server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server import MCPServer  # noqa: E402

from sumcp import config, dispatch  # noqa: E402

INSTRUCTIONS = f"""\
Seismic Unix (CWP/SU) processing for 2D seismic data, under a fixed project layout:

  raw/      field data - readable, never writable
  work/     intermediate products
  results/  final products
  qc/       QC figures
  logs/     processing.jsonl, one line per execution
  state/    dataset manifests (written only by the dataset tools)

Refer to files by those names. raw/, results/, qc/, logs/ and state/ live under
the project root ({config.ROOT}); work/ and the scratch live under
{config.RUNTIME_ROOT}, which on WSL keeps the heavy intermediate I/O off the
Windows drive. These directories hold field data and are readable but never
writable, exactly like raw/: {', '.join(d.name + '/' for d in config.DATA_DIRS) or '(none)'}.
Paths outside all of those are refused.

Analysis that will not finish inside one tool call takes run_as_job=true: the
call returns a job_id at once, and job_status / job_result / cancel_job manage
it from there. Use it for a sensitivity sweep or a long import rather than
shrinking the analysis to fit the clock.

Only these SU programs run:
{', '.join(sorted(config.ALLOWED_SU_COMMANDS))}.
sunmo, sustack and suvelan are deliberately withheld until the geometry and
velocity tools of later versions exist.

Work is organised around datasets. A dataset has a manifest holding named
capabilities, each with a status and the evidence behind it - for example
headers.sampling_consistent = PASS because ns and dt matched between the SEG-Y
binary header and the imported SU file. Later stages read those capabilities
rather than re-deriving them, and refuse when a prerequisite is missing.

Start a SEG-Y file with segy_inspect, then dataset_import_segy; start a file
already in SU form with dataset_register_su. Then dataset_manifest to see what
is established and what is not. su_search and su_help give the authoritative
parameter list for any SU program; read them rather than relying on remembered
parameter names. su_run and su_pipeline stay available for work on files, and
su_preview renders a QC image.

Geometry is measured, not assumed. geometry_analyze resolves scalco and counit,
tests whether the receiver coordinates move with the shot, compares the offset
header against the coordinates, and grades the cdp header ABSENT / PLAUSIBLE /
IMPLAUSIBLE - a populated cdp is not evidence that the numbering is a CMP
binning. Given a time window it also measures the apparent velocity of a
coherent arrival and checks it against what the coordinates predict; that
measurement is what separates a real fixed array from one record's positions
copied into every trace.

The stack track runs build_cmp -> sort_cmp -> pick_velocity -> apply_nmo ->
stack_cmp, and each step refuses unless the one before it recorded what this
one needs. build_cmp will not start unless the geometry is established and
reflection.processing_feasible is PASS: a survey where no reflection is
reachable must not become a stack.

Geometry that one line cannot settle is settled by several: fit_array_geometry
takes the lines that share an array and separates a receiver-spacing error from
a per-channel recording delay, or reports INDETERMINATE and says what geometry
would answer it. survey_overview answers "where does this survey stand"
across every line at once, from the manifests rather than from memory.
export_product brings a file out of work/ into results/.

sunmo and sustack are deliberately absent from the list above. They run only
from apply_nmo and stack_cmp, after the evidence has been checked, because a
refusal that can be walked around by calling the program directly is not a
refusal.

Read a dataset's capabilities before proposing a step, and quote the evidence
when explaining why something is or is not justified. A refusal names what is
missing and why; pass that on rather than trying another route around it.
"""

from sumcp import governance  # noqa: E402

if governance.off():   # baseline01 C0 evaluation deployment only (the import refuses anywhere else)
    INSTRUCTIONS = ("EVALUATION DEPLOYMENT (baseline study 01, condition C0): evidence governance is off. No step "
                    "is refused for lack of evidence, every product is adopted, and no reliability, warning or "
                    "capability status is reported. Where the text below describes refusals, gates, capabilities "
                    "or evidence, it does not apply here.\n\n" + INSTRUCTIONS)

mcp = MCPServer(
    name="seismic-unix",
    title="Seismic Unix MCP",
    version=config.VERSION,
    instructions=INSTRUCTIONS,
)


@mcp.tool()
def su_status() -> dict:
    """Check the Seismic Unix installation and the project directories.

    Returns CWPROOT, how many SU programs are installed, where the core
    programs live, which commands this version allows, and the file count in
    each project directory. Call this first in a new session.
    """
    arguments = {}
    return dispatch.call("su_status", arguments)


@mcp.tool()
def su_search(keyword: str, mode: str = "synopsis") -> dict:
    """Search SU's self-documentation for programs matching a keyword.

    SU ships over 450 programs; use this instead of guessing names.
    mode: "synopsis" for brief descriptions, "name" to match program names
    only, "verbose" for a full search of programs and libraries.
    """
    arguments = {
        "keyword": keyword,
        "mode": mode,
    }
    return dispatch.call("su_search", arguments)


@mcp.tool()
def su_help(program: str) -> dict:
    """Return the full self-documentation for one SU program.

    This is the authoritative parameter list for that program on this machine.
    Read it before running any program whose parameters you are not certain of.
    The reply also states whether the program is allowed in this version.
    """
    arguments = {
        "program": program,
    }
    return dispatch.call("su_help", arguments)


@mcp.tool()
def su_inspect(input_file: str, run_surange: bool = True,
        run_as_job: bool = False) -> dict:
    """Inspect an SU file: sampling, trace count, header ranges and fold.

    Returns a structured summary (ns, dt, ntr, per-key min/max/step, whether
    cdp is populated, traces per shot or fold per bin) plus surange's own text
    output, and notes on anything that would block later processing.
    """
    arguments = {
        "input_file": input_file,
        "run_surange": run_surange,
    }
    if run_as_job:
        return dispatch.start_job("su_inspect", arguments)
    return dispatch.call("su_inspect", arguments)


@mcp.tool()
def su_list_files(directory: str = "") -> dict:
    """List the readable data files in the project (raw, work, results, qc)."""
    arguments = {
        "directory": directory,
    }
    return dispatch.call("su_list_files", arguments)


@mcp.tool()
def su_run(command: str, input_file: str, output_file: str,
           params: dict | None = None, overwrite: bool = False,
        run_as_job: bool = False) -> dict:
    """Run one allowlisted SU program, reading input_file and writing output_file.

    params is an object of SU key=value parameters; lists become comma-separated
    values, so {"f": [10, 20, 120, 150]} becomes f=10,20,120,150. No shell is
    involved and parameters may not contain paths. Output must land in work/,
    results/ or qc/. The call is appended to logs/processing.jsonl with a
    sha256 of the product.
    """
    arguments = {
        "command": command,
        "input_file": input_file,
        "output_file": output_file,
        "params": params,
        "overwrite": overwrite,
    }
    if run_as_job:
        return dispatch.start_job("su_run", arguments)
    return dispatch.call("su_run", arguments)


@mcp.tool()
def su_pipeline(input_file: str, output_file: str, steps: list,
                overwrite: bool = False,
        run_as_job: bool = False) -> dict:
    """Run several allowlisted SU programs joined by Unix pipes.

    steps is a list of {"command": ..., "params": {...}} objects, applied in
    order, e.g. suwind then sufilter then sugain. Use this rather than writing
    an intermediate file for every step. Logged as one pipeline entry.
    """
    arguments = {
        "input_file": input_file,
        "output_file": output_file,
        "steps": steps,
        "overwrite": overwrite,
    }
    if run_as_job:
        return dispatch.start_job("su_pipeline", arguments)
    return dispatch.call("su_pipeline", arguments)


@mcp.tool()
def su_preview(input_file: str, output_png: str, fldr: int | None = None,
               cdp: int | None = None, start: int = 0, count: int | None = None,
               perc: float = 99.0, mode: str = "image", gain: str = "none",
               title: str | None = None,
        run_as_job: bool = False) -> dict:
    """Render a QC image of an SU file into qc/ and report what was plotted.

    Select one gather with fldr= or cdp=, or a trace range with start/count.
    mode "image" (default) or "wiggle" for up to 120 traces; gain "agc" applies
    a display-only 0.5 s AGC. perc sets the clip percentile. Look at the PNG
    before deciding whether a processing parameter was a good choice.
    """
    arguments = {
        "input_file": input_file,
        "output_png": output_png,
        "fldr": fldr,
        "cdp": cdp,
        "start": start,
        "count": count,
        "perc": perc,
        "mode": mode,
        "gain": gain,
        "title": title,
    }
    if run_as_job:
        return dispatch.start_job("su_preview", arguments)
    return dispatch.call("su_preview", arguments)


@mcp.tool()
def su_log(limit: int = 20) -> dict:
    """Return the most recent entries from the project's processing log."""
    arguments = {
        "limit": limit,
    }
    return dispatch.call("su_log", arguments)


# --------------------------------------------------------------------------
# Datasets (v0.2)
# --------------------------------------------------------------------------

@mcp.tool()
def segy_inspect(input_file: str, textual_header: bool = False,
        run_as_job: bool = False) -> dict:
    """Diagnose a SEG-Y file without importing it.

    Reads the textual and binary headers and reports byte order (with the
    evidence for that conclusion), SEG-Y revision, sample format, ns, dt, the
    estimated trace count, whether segyread can convert the format as-is, and
    every inconsistency found. Run this before dataset_import_segy.
    """
    arguments = {
        "input_file": input_file,
        "textual_header": textual_header,
    }
    if run_as_job:
        return dispatch.start_job("segy_inspect", arguments)
    return dispatch.call("segy_inspect", arguments)


@mcp.tool()
def dataset_import_segy(dataset_id: str, segy_file: str, description: str = "",
                        endian: int | None = None, ns_override: int | None = None,
                        force_format: int | None = None,
        run_as_job: bool = False) -> dict:
    """Import a SEG-Y file as a dataset and verify that the import is faithful.

    Converts with segyread into work/<dataset_id>/, keeps the source textual and
    binary headers, then checks ns, dt and the trace count against the SEG-Y
    headers and file length. Results go into the dataset manifest as evidence.
    Leave endian, ns_override and force_format unset unless segy_inspect
    reported a problem that needs them. dataset_id is a short slug such as
    "line01".
    """
    arguments = {
        "dataset_id": dataset_id,
        "segy_file": segy_file,
        "description": description,
        "endian": endian,
        "ns_override": ns_override,
        "force_format": force_format,
    }
    if run_as_job:
        return dispatch.start_job("dataset_import_segy", arguments)
    return dispatch.call("dataset_import_segy", arguments)


@mcp.tool()
def dataset_register_su(dataset_id: str, su_file: str, description: str = "",
        run_as_job: bool = False) -> dict:
    """Register a file that is already in SU form as a dataset.

    Use this instead of dataset_import_segy when there is no SEG-Y to convert.
    It parses the headers and records the same capabilities, but the
    sampling and trace-count checks can only be made against the SU file itself.
    """
    arguments = {
        "dataset_id": dataset_id,
        "su_file": su_file,
        "description": description,
    }
    if run_as_job:
        return dispatch.start_job("dataset_register_su", arguments)
    return dispatch.call("dataset_register_su", arguments)


@mcp.tool()
def dataset_list() -> dict:
    """List registered datasets and which capabilities each has established."""
    arguments = {}
    return dispatch.call("dataset_list", arguments)


@mcp.tool()
def dataset_manifest(dataset_id: str, section: str = "summary") -> dict:
    """Read a dataset manifest: what is known about the dataset and on what evidence.

    section: "summary" (default), "capabilities" (each status with its evidence
    and the algorithm version that set it), "artifacts" (files and their
    lineage), "history", or "full". Read "capabilities" before deciding whether
    a processing step is justified, and quote the evidence when explaining why.
    """
    arguments = {
        "dataset_id": dataset_id,
        "section": section,
    }
    return dispatch.call("dataset_manifest", arguments)


# --------------------------------------------------------------------------
# Geometry (v0.3)
# --------------------------------------------------------------------------

@mcp.tool()
def geometry_analyze(dataset_id: str, measure_fldr: int | None = None,
                     measure_tmin: float | None = None,
                     measure_tmax: float | None = None,
                     trend_shots: int = 20,
                     water_velocity: float = 1500.0,
        run_as_job: bool = False) -> dict:
    """Work out what the coordinate headers really say, and record the evidence.

    Applies scalco (negative divides) and reads counit, tests whether each
    channel's position changes from shot to shot, compares the offset header
    with the distance the coordinates imply, and grades the cdp header as
    ABSENT, PLAUSIBLE or IMPLAUSIBLE by checking that traces sharing a cdp also
    share a midpoint.

    Give measure_fldr with measure_tmin/measure_tmax to also measure the
    apparent velocity of the arrival in that window and the way its time changes
    from shot to shot. Without that measurement, receiver coordinates that never
    change are ambiguous - a real fixed array and copied headers look identical
    in the headers alone - and the classification says so rather than guessing.

    Results land in the dataset manifest as capabilities with their evidence.
    """
    arguments = {
        "dataset_id": dataset_id,
        "measure_fldr": measure_fldr,
        "measure_tmin": measure_tmin,
        "measure_tmax": measure_tmax,
        "trend_shots": trend_shots,
        "water_velocity": water_velocity,
    }
    if run_as_job:
        return dispatch.start_job("geometry_analyze", arguments)
    return dispatch.call("geometry_analyze", arguments)


@mcp.tool()
def inspect_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                              xps_file: str, run_as_job: bool = False) -> dict:
    """Read a standard SPS/RPS/XPS acquisition set and report what it would do.

    A field tape often carries no geometry at all: the survey wrote the
    positions down separately, in the SEG SPS exchange set - an S file of source
    points, an R file of receiver points, and an X file of relation records
    tying each field record to one source and to a range of channels on a range
    of receiver stations.

    All three are read using the column layout each file declares in its own H
    records, so a file that states its own revision is read as it states itself;
    a file that declares nothing falls back to the published SPS 2.1 columns and
    the report says which was used. The relation is then followed against this
    dataset's trace headers and every validation check is reported.

    Nothing is written, no header is touched and no capability is set. Use this
    to see what assign_external_geometry would do before it does it.
    """
    arguments = {"dataset_id": dataset_id, "sps_file": sps_file,
                 "rps_file": rps_file, "xps_file": xps_file}
    if run_as_job:
        return dispatch.start_job("inspect_external_geometry", arguments)
    return dispatch.call("inspect_external_geometry", arguments)


@mcp.tool()
def assign_external_geometry(dataset_id: str, sps_file: str, rps_file: str,
                             xps_file: str, overwrite: bool = False,
                             run_as_job: bool = False) -> dict:
    """Attach a standard SPS/RPS/XPS acquisition set to a dataset.

    The relation is followed, never counted. A trace is placed only when the X
    record names a channel range that contains its channel, that range maps
    one-to-one onto a receiver-station range, and both the source point and the
    receiver station exist in the S and R files. There is no nearest-station
    search and no arithmetic shortcut: if a check fails, nothing is attached and
    the failing check is named.

    On success the coordinates and the derived signed offset are written into a
    PROCESSING COPY. The imported SU file and the original SEG-Y are left byte
    for byte as they were. What is attached is nominal survey geometry carried
    with the acquisition origin - the positions the survey says it used, not
    positions measured here.

    Where the SEG-Y already carries geometry the two are compared on the same
    tolerance the geometry stage already applies to a header: consistent
    geometry validates, materially conflicting geometry is refused rather than
    overwritten, because which of the two is authoritative is a survey question
    this version does not answer.

    Afterwards the ordinary geometry stage runs on the copy, so the canonical
    processing offset is decided by exactly the rule that decides it for a line
    whose geometry was in its own headers.
    """
    arguments = {"dataset_id": dataset_id, "sps_file": sps_file,
                 "rps_file": rps_file, "xps_file": xps_file,
                 "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("assign_external_geometry", arguments)
    return dispatch.call("assign_external_geometry", arguments)


@mcp.tool()
def measure_apparent_velocity(input_file: str, fldr: int | None = None,
                              cdp: int | None = None, tmin: float | None = None,
                              tmax: float | None = None,
                              channel_spacing_m: float | None = None,
                              max_slope_ms: float = 8.0,
        run_as_job: bool = False) -> dict:
    """Slant-stack one ensemble and report the slope where it is most coherent.

    Returns the best slope in ms per channel for each of several frequency
    bands, with the semblance there and at zero slope. A slope that repeats
    across bands is evidence; one that appears in a single band is not. Give
    channel_spacing_m to get an apparent velocity. Use this to check a header
    against the data instead of taking the header's word.
    """
    arguments = {
        "input_file": input_file,
        "fldr": fldr,
        "cdp": cdp,
        "tmin": tmin,
        "tmax": tmax,
        "channel_spacing_m": channel_spacing_m,
        "max_slope_ms": max_slope_ms,
    }
    if run_as_job:
        return dispatch.start_job("measure_apparent_velocity", arguments)
    return dispatch.call("measure_apparent_velocity", arguments)


@mcp.tool()
def scan_coherence(input_file: str, fldr: int | None = None, cdp: int | None = None,
                   t_start: float | None = None, t_end: float | None = None,
                   window_s: float = 0.2, step_s: float = 0.05,
                   band_low: float = 40.0, band_high: float = 120.0,
                   channel_spacing_m: float | None = None,
                   min_contrast: float = 1.8,
        run_as_job: bool = False) -> dict:
    """Find every coherent arrival in a record, without being told where to look.

    measure_apparent_velocity answers "what is the slope in this window";
    this answers "is there anything in this record at all, and where", which is
    the question when the arrivals are not where the headers suggest. Returns
    the local maxima above min_contrast as a short list, each with its time,
    slope and (given channel_spacing_m) apparent velocity. An apparent velocity
    far below the medium's is usually noise rather than an arrival.
    """
    arguments = {
        "input_file": input_file,
        "fldr": fldr,
        "cdp": cdp,
        "t_start": t_start,
        "t_end": t_end,
        "window_s": window_s,
        "step_s": step_s,
        "band_low": band_low,
        "band_high": band_high,
        "channel_spacing_m": channel_spacing_m,
        "min_contrast": min_contrast,
    }
    if run_as_job:
        return dispatch.start_job("scan_coherence", arguments)
    return dispatch.call("scan_coherence", arguments)


@mcp.tool()
def fit_channel_geometry(input_file: str, velocity: float = 1492.0,
                         band_low: float = 40.0, band_high: float = 200.0,
                         window_s: float = 0.25, min_contrast: float = 1.5,
                         channel_spacing_m: float | None = None,
        run_as_job: bool = False) -> dict:
    """Test whether the header geometry alone explains the moveout across channels.

    Measures each shot's channel moveout and compares it with the moveout the
    header positions predict, then fits measured = a * predicted + b over all
    shots. `a` is a scale on the geometry - the channel spacing and the assumed
    velocity enter it identically, so this fit cannot separate those two - and
    `b` is a per-channel delay that no geometry produces. Competing models are
    reported side by side with their residuals, not reduced to one answer.

    The separation only works when the predicted moveout varies across shots,
    which needs the angle between the array axis and the ray to change. On a
    strictly in-line line the result is DEGENERATE and says so rather than
    picking one explanation; run it on a line that crosses the array instead.
    """
    arguments = {
        "input_file": input_file,
        "velocity": velocity,
        "band_low": band_low,
        "band_high": band_high,
        "window_s": window_s,
        "min_contrast": min_contrast,
        "channel_spacing_m": channel_spacing_m,
    }
    if run_as_job:
        return dispatch.start_job("fit_channel_geometry", arguments)
    return dispatch.call("fit_channel_geometry", arguments)


@mcp.tool()
def assess_reflection_feasibility(
        input_file: str, channel: int | None = None, fldr: int | None = None,
        cdp: int | None = None, water_velocity: float = 1492.0,
        band_low: float = 30.0, band_high: float = 250.0, max_traces: int = 400,
        probe_t0_s: float | None = None, probe_velocity: float | None = None,
        run_sensitivity: bool = True, dataset_id: str | None = None,
        run_as_job: bool = False) -> dict:
    """Decide whether a gather can yield a reflection, and prove the decision.

    Suppresses the direct wave three ways that fail for unrelated reasons - a
    predicted mute in the time domain, a leave-one-out template subtraction in
    the flattened domain, and a least-squares tau-p band reject in the slowness
    domain - then runs one velocity-semblance scan on all three. Every
    suppression method leaves something behind and what it leaves looks like an
    event, so only a candidate all three branches see is reported, and even
    then as a candidate.

    A FAIL comes with the amplitude at which an injected reflection WOULD have
    been recovered, because "nothing is there" and "this gather could not have
    shown it" are opposite conclusions. If the threshold is low and nothing was
    found, the absence is informative; if it is high, the verdict is about the
    survey's sensitivity and says so.

    Pick exactly one gather: channel=<tracf> for a common-receiver walkaway,
    fldr=<shot> for one shot record, cdp=<bin> for one CMP gather. Pass
    dataset_id to record reflection.direct_wave_suppressed and
    reflection.processing_feasible in that dataset's manifest.

    The sensitivity ladder costs several passes over the gather; set
    run_sensitivity=False for a quick look, but a FAIL without it is not a
    result.
    """
    arguments = {
        "input_file": input_file,
        "channel": channel,
        "fldr": fldr,
        "cdp": cdp,
        "water_velocity": water_velocity,
        "band_low": band_low,
        "band_high": band_high,
        "max_traces": max_traces,
        "probe_t0_s": probe_t0_s,
        "probe_velocity": probe_velocity,
        "run_sensitivity": run_sensitivity,
        "dataset_id": dataset_id,
    }
    if run_as_job:
        return dispatch.start_job("assess_reflection_feasibility", arguments)
    return dispatch.call("assess_reflection_feasibility", arguments)


# ---------------------------------------------------------------------------
# The stack track
# ---------------------------------------------------------------------------
@mcp.tool()
def build_cmp(dataset_id: str, bin_size_m: float | None = None,
              receiver_spacing_m: float | None = None,
              reference_velocity_m_s: float = 1800.0,
              reference_t0_s: float = 1.0, min_fold: int = 4,
              overwrite: bool = False, run_as_job: bool = False) -> dict:
    """Assign CMP bins from the coordinates, and grade whether they can be stacked.

    This is the entrance to the stack pipeline, so it refuses unless the
    geometry was established AND reflection.processing_feasible is PASS. That
    decision is not made here: binning is arithmetic and always produces a
    plausible-looking fold map, whatever went in.

    Bins are computed from the coordinates rather than trusted from the cdp
    header. Where the file already carries a cdp, the two are compared by how
    they GROUP the traces, not by their numbers; if they agree, the file's own
    numbering is kept, and if they do not, the disagreement is reported rather
    than resolved.

    geometry.fold_valid then grades the result on NMO leverage, not on fold
    alone: moveout is linear in offset squared, so a bin can hold sixty traces
    at effectively one moveout and be worth nothing to a velocity scan. That
    check can fail a survey whose fold map looks healthy.

    The output is a new file; the imported SU file is left alone, so the
    binning can be redone with a different bin size without re-importing.
    """
    arguments = {
        "dataset_id": dataset_id,
        "bin_size_m": bin_size_m,
        "receiver_spacing_m": receiver_spacing_m,
        "reference_velocity_m_s": reference_velocity_m_s,
        "reference_t0_s": reference_t0_s,
        "min_fold": min_fold,
        "overwrite": overwrite,
    }
    if run_as_job:
        return dispatch.start_job("build_cmp", arguments)
    return dispatch.call("build_cmp", arguments)


@mcp.tool()
def sort_cmp(dataset_id: str, overwrite: bool = False,
             run_as_job: bool = False) -> dict:
    """Sort the CMP-binned file into cdp order, ready for velocity analysis.

    Refuses unless geometry.cmp_assigned and geometry.fold_valid are PASS, so a
    survey whose bins carry no moveout cannot quietly become a sorted file that
    looks ready to stack.

    Header source/receiver statics are applied here once, in the SEG-Y sense (S1),
    gated by the near-offset first-break intercept. When they are applied the data are
    treated as land (L0): the first arrivals are measured across the spread (L1), and
    the reflection window of every later QC (stack S/N and velocity support, the
    conditioning gates, migration stability) starts where they leave the spread instead
    of at a water-wave arrival.
    """
    arguments = {"dataset_id": dataset_id, "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("sort_cmp", arguments)
    return dispatch.call("sort_cmp", arguments)


@mcp.tool()
def pick_velocity(dataset_id: str, n_locations: int = 5,
                  cdp_list: list | None = None, v_min: float = 1400.0,
                  v_max: float = 5500.0, v_step: float = 50.0,
                  t_step: float = 0.04, band_low: float = 5.0,
                  band_high: float = 90.0, n_points: int = 10,
                  max_rate_m_s2: float = 2500.0,
                  run_as_job: bool = False) -> dict:
    """Measure a stacking velocity at several CMPs, and grade every one.

    The function is picked under constraint rather than repaired afterwards: a
    dynamic program walks the semblance panel choosing, for each time, the
    velocity that maximises total support subject to never decreasing and to a
    bounded rate of change. That makes the result physical by construction, and
    makes the semblance it reaches an honest score - on a gather with no trend
    the constrained path scores at the noise floor and the report says the path
    is the constraint talking, not the data.

    Then it is checked. Interval velocities from Dix must be real, positive and
    in range where the velocity was measured; below the deepest supported pick
    the velocity is held constant rather than allowed to climb through noise,
    and that is reported as an assumption. Locations that fail are omitted and
    NMO interpolates across the rest; velocity.validated is PASS only if enough
    survive (3 of 5; for denser analysis the count that keeps the same chance of
    validating noise), they cover 80% of the analysed span, and (dense analysis)
    no gap between them is longer than a quarter of the span.

    n_locations is a minimum: without cdp_list the line also gets at least one
    location per 500 m of its eligible span (at most 15). Analysis locations
    skip the outermost bins: the first and last CMP of a line are built from
    whatever fell there.
    """
    arguments = {
        "dataset_id": dataset_id,
        "n_locations": n_locations,
        "cdp_list": cdp_list,
        "v_min": v_min,
        "v_max": v_max,
        "v_step": v_step,
        "t_step": t_step,
        "band_low": band_low,
        "band_high": band_high,
        "n_points": n_points,
        "max_rate_m_s2": max_rate_m_s2,
    }
    if run_as_job:
        return dispatch.start_job("pick_velocity", arguments)
    return dispatch.call("pick_velocity", arguments)


@mcp.tool()
def apply_nmo(dataset_id: str, smute: float = 1.5, overwrite: bool = False,
              run_as_job: bool = False) -> dict:
    """NMO with the measured velocity model.

    Refuses unless velocity.validated is PASS. sunmo is not in the allowlist
    su_run can reach, so this refusal cannot be routed around by calling the
    program directly - which is the only thing that makes it a gate rather
    than a suggestion.
    """
    arguments = {"dataset_id": dataset_id, "smute": smute,
                 "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("apply_nmo", arguments)
    return dispatch.call("apply_nmo", arguments)


@mcp.tool()
def stack_cmp(dataset_id: str, overwrite: bool = False,
              run_as_job: bool = False) -> dict:
    """Sum each CMP gather into one trace. Refuses unless nmo.applied is PASS.

    The result lands in results/ and stack.completed records it, so the
    section can be traced back through every capability that allowed it.
    Every stack carries a reliability verdict: WARN when its quality is at risk
    (half-stack ceiling below 0.95, or under a quarter of the section on a
    measured velocity), CAUTION when only its provenance is (reflections never
    established before binning), otherwise OK. Quote it with the section.
    """
    arguments = {"dataset_id": dataset_id, "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("stack_cmp", arguments)
    return dispatch.call("stack_cmp", arguments)


@mcp.tool()
def conditioning_menu() -> dict:
    """List the pre-stack conditioning operations condition_gathers accepts.

    Each entry names the SU program behind it, its parameters and allowed
    ranges, what it is for and what it can damage. The programs are not
    reachable through su_run; this menu is the only way to them.
    """
    return dispatch.call("conditioning_menu", {})


@mcp.tool()
def condition_gathers(dataset_id: str, operations: list,
                      run_as_job: bool = False) -> dict:
    """Condition the CMP gathers with up to 3 menu operations, in order.

    operations: e.g. [{"op": "bandpass", "f": [3, 5, 25, 35]},
                      {"op": "mute_direct", "extra_s": 0.1}].
    See conditioning_menu for the operations and their parameters.

    The result is accepted only if it keeps signal: three synthetic reflections
    are injected into five CMP gathers, the chain is run with and without them,
    and the processed injection must correlate >= 0.9 with what was injected.
    Accepted gathers replace cmp_sorted and invalidate velocity, NMO and stack,
    which must be rerun. Rejected gathers are kept for audit and not used.
    At most 3 passes per dataset (v0.26: DMO takes one).

    v0.20: the injection gate also injects a shallow set above the last direct
    arrival (a mute or dip filter that removes shallow far-offset reflections
    now fails). Two operations move events in time, run alone, and have their
    own gates: [{"op": "datum_shift"}] shifts by R1's measured direct-wave lag
    when it exceeds a quarter period and re-measures R1; [{"op":
    "residual_statics"}] (needs a validated velocity) estimates surface-consistent
    statics with suresstat and applies them only if odd- and even-CMP estimates
    repeat (split-half reliability >= 0.9).

    v0.26: [{"op": "dmo"}] (needs a validated velocity) runs NMO, dip moveout
    (sudmofk) and inverse NMO with the validated model; accepted only if flat
    reflections injected at every CMP keep >= 0.9 correlation and every trace
    keeps its (cdp, offset) order. Re-pick the velocity after it.

    v0.30: [{"op": "kill_corrupt"}] zeroes traces holding a non-finite sample or
    one beyond 120 dB of the median trace RMS (Q0, e.g. a clamped IBM-float
    overflow); every other operation is refused while such traces remain.
    """
    arguments = {"dataset_id": dataset_id, "operations": operations}
    if run_as_job:
        return dispatch.start_job("condition_gathers", arguments)
    return dispatch.call("condition_gathers", arguments)


@mcp.tool()
def refine_velocity(dataset_id: str, run_as_job: bool = False) -> dict:
    """Re-analyse the locations that failed velocity validation, a bounded number of times.

    Runs only when velocity.validated is FAIL at the location level; refuses a
    time-zero FAIL, which no choice of gathers can fix. At the failed locations
    only, it tries in order: a 5-CMP supergather; the nearest eligible CMPs
    within a quarter of the location spacing (at most 3, each as a 5-CMP
    supergather); a 9-CMP supergather. It stops at the first attempt after
    which the model passes. Every check is unchanged. One call per velocity
    model, at most 6 velocity analyses per dataset; the number of attempts is
    recorded on the model and on the stack.

    v0.20: relocation moves an eighth and a quarter of the location spacing
    (independent traces); refine tests use alpha 0.01 (Bonferroni over the five
    tests a location can receive); if only coverage still fails and the valid
    locations span at least half the line, the model passes with a scope and
    stack_cmp releases only that CMP range.
    """
    arguments = {"dataset_id": dataset_id}
    if run_as_job:
        return dispatch.start_job("refine_velocity", arguments)
    return dispatch.call("refine_velocity", arguments)


@mcp.tool()
def migrate_stack(dataset_id: str, method: str = "phase_shift_smooth",
                  overwrite: bool = False, run_as_job: bool = True) -> dict:
    """Post-stack phase-shift time migration of the released stack, behind a gate.

    Refuses unless stack.completed and velocity.validated are PASS. The velocity
    is the one the stack was made with (RMS, as sunmo used it), converted to
    interval velocity by Dix; sumigps is not reachable any other way.
    method "phase_shift_smooth" (default since v0.27, M6) migrates once per
    valid velocity location with that location's RMS velocity replaced by the
    median of the five nearest locations, and blends the images between
    locations: one bad pick no longer spreads, the lateral trend stays (one
    migration when there are five locations or fewer). "phase_shift" uses one
    function, the lateral median; "phase_shift_blend" uses each location's own
    picks. The stacking velocity is never changed. The lateral velocity spread
    is reported (M3).
    v0.28 depth: "depth_convert" stretches the released phase_shift_smooth
    migration to depth; "depth_pspi" depth-migrates the stack (SU sumigpspi)
    and is released only if synthetic diffractions focus at the depth the
    velocity predicts (Z1). Both use the M6 interval velocity, refuse when Dix
    gives interval velocities outside 1000-7000 m/s (Z2), state a depth
    tolerance of +-5% (Z3) and warn when no DMO pass was accepted (Z4).
    Depth sections: 5 m steps, d1 = dz, dt field = dz in mm.
    v0.30: a stack holding corrupt samples (Q0) is refused; kill them first.
    v0.31: phase_shift_smooth and the depth methods smooth each location's RMS
    velocity in time over its control-point spacing before Dix (M7); every
    method scores stability to +-5% velocity in 1 s windows and warns below 0.5
    (M8); the depth step follows the wavelength (Z5, at most 5 m); a rejected
    run no longer demotes a released product (B1).

    M1: three synthetic diffractions are migrated with the same operator and
    velocities and must focus (>= 50% of their energy within half a dominant
    period in time and v*T/4 laterally of the peak, peak within a quarter
    period and half that lateral window of the apex);
    otherwise the section is kept for audit and not released. M2 reports how
    much the image changes when the velocity is 5% lower or higher. M5 warns
    when, over more than half of the section, a 30-degree migration aperture
    runs off the line ends (short lines, long records: the ends sweep "smiles"
    across the image). The product inherits the stack's reliability verdict.
    Slow: runs as a job by default.
    """
    arguments = {"dataset_id": dataset_id, "method": method, "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("migrate_stack", arguments)
    return dispatch.call("migrate_stack", arguments)


@mcp.tool()
def fit_array_geometry(dataset_ids: list, water_velocity: float = 1492.0,
                       band_low: float = 30.0, band_high: float = 250.0,
                       min_semblance: float = 0.30,
                       max_shots: int | None = None, bootstrap: int = 400,
                       run_as_job: bool = False) -> dict:
    """Is the channel moveout a receiver-spacing error or a recording delay?

    Both add time in proportion to a channel's distance along the array, so on
    a line whose source track runs ALONG that array they are the same column of
    the design matrix and nothing separates them. This refuses to answer from
    such a line: the verdict is INDETERMINATE and it says what geometry would
    settle it, rather than returning the numbers a collinear system produces.

    Give it every line that shares the array. Lines whose source track crosses
    the array carry the answer; lines that run along it are held out and their
    slopes predicted, which is a test rather than a fit statistic.

    The arrival is fitted across the whole array per shot rather than picked
    trace by trace - twenty-four channels of one shot are one wavefront, not
    twenty-four measurements - and the confidence interval comes from
    resampling whole shots, because the channels of a shot share whatever that
    shot did wrong.

    Reads every trace of every line given, so pass run_as_job=true unless the
    lines are small or max_shots is set.
    """
    arguments = {
        "dataset_ids": dataset_ids,
        "water_velocity": water_velocity,
        "band_low": band_low,
        "band_high": band_high,
        "min_semblance": min_semblance,
        "max_shots": max_shots,
        "bootstrap": bootstrap,
    }
    if run_as_job:
        return dispatch.start_job("fit_array_geometry", arguments)
    return dispatch.call("fit_array_geometry", arguments)


@mcp.tool()
def survey_overview(dataset_ids: list | None = None) -> dict:
    """Where does this survey stand, across every line at once?

    For each registered dataset: the furthest step on the stack track it has
    passed, the recorded reason it stopped, and the tool call that would answer
    the next question. Read this before planning work on a survey - it is built
    from the manifests, so it cannot claim more than the evidence does.

    A line that was measured and refused is listed apart from one nobody has
    measured yet. Those are different facts: the first is an answer, the second
    is work outstanding.

    Lines fitted together for array geometry are grouped, because what was
    established there holds for the array they share, not for one line.
    """
    return dispatch.call("survey_overview", {"dataset_ids": dataset_ids})


@mcp.tool()
def export_product(dataset_id: str, artifact: str, output_name: str = "",
                   overwrite: bool = False, run_as_job: bool = False) -> dict:
    """Copy a product out of work/ into results/, where it can be opened.

    work/ lives on the runtime filesystem, which on WSL is deliberately not the
    Windows drive: right for heavy intermediate I/O, wrong for anything anyone
    wants to look at. Name the artifact as dataset_manifest lists it.
    """
    arguments = {"dataset_id": dataset_id, "artifact": artifact,
                 "output_name": output_name, "overwrite": overwrite}
    if run_as_job:
        return dispatch.start_job("export_product", arguments)
    return dispatch.call("export_product", arguments)


@mcp.tool()
def dataset_forget(dataset_id: str, confirm: bool = False) -> dict:
    """Delete a dataset's manifest so the identifier can be reused.

    Products in work/ are kept; only the evidence trail goes, which is why it
    asks for confirmation and lists what would be lost. Re-importing is
    usually the better move.
    """
    return dispatch.call("dataset_forget",
                         {"dataset_id": dataset_id, "confirm": confirm})


# ---------------------------------------------------------------------------
# Background jobs
# ---------------------------------------------------------------------------
@mcp.tool()
def job_list(limit: int = 20) -> dict:
    """List background analysis jobs, newest first, with their status.

    A job is one of the analysis tools started with run_as_job=true because it
    would not finish inside a single tool call. Status is one of running,
    finished, cancelled or died.
    """
    return {"ok": True, "jobs": dispatch.list_jobs(limit)}


@mcp.tool()
def job_status(job_id: str) -> dict:
    """Ask whether a background job has finished.

    Poll this rather than guessing how long the work takes. A job that comes
    back "died" exited without writing a result, and the reply carries the tail
    of its log so the failure can be read instead of inferred.
    """
    try:
        return {"ok": True, **dispatch.job_status(job_id)}
    except dispatch.JobError as exc:
        return {"ok": False, "error": str(exc), "error_type": "JobError"}


@mcp.tool()
def job_result(job_id: str) -> dict:
    """Read a finished job's result - the same payload the tool would have
    returned had it run inline. Refuses while the job is still running."""
    try:
        return {"ok": True, "job_id": job_id, "result": dispatch.job_result(job_id)}
    except dispatch.JobError as exc:
        return {"ok": False, "error": str(exc), "error_type": "JobError"}


@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """Stop a running background job. Any partial output it wrote stays where
    it is; nothing is rolled back."""
    try:
        return {"ok": True, **dispatch.cancel_job(job_id)}
    except dispatch.JobError as exc:
        return {"ok": False, "error": str(exc), "error_type": "JobError"}


if __name__ == "__main__":
    mcp.run()
