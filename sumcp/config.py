"""Static configuration for the Seismic Unix MCP server (v0.1)."""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "VERSION", "ROOT", "RUNTIME_ROOT", "RAW_DIR", "WORK_DIR", "RESULT_DIR",
    "QC_DIR", "LOG_DIR", "JOB_DIR", "TMP_DIR", "DIR_ALIASES", "DATA_DIRS",
    "READABLE_DIRS", "WRITABLE_DIRS", "PROJECT_DIRS",
    "STATE_DIR", "DATASET_DIR", "DATASET_ID_RE", "WORKER_TIMEOUT",
    "ALLOWED_SU_COMMANDS", "TRUSTED_SU_COMMANDS", "PARAM_KEY_RE", "PARAM_VALUE_RE",
    "DENIED_PARAM_KEYS", "TIMEOUT_QUICK", "TIMEOUT_INSPECT", "TIMEOUT_RUN",
    "MAX_TEXT_CHARS", "HASH_SIZE_LIMIT", "PROCESSING_LOG",
]


# One version string.
VERSION = "0.33.3"


def _resolve_root() -> Path:
    """Project root: SU_MCP_ROOT if set, otherwise the package's parent."""
    env = os.environ.get("SU_MCP_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


ROOT = _resolve_root()


def _resolve_runtime() -> Path:
    """Where the heavy intermediate files live."""
    env = os.environ.get("SU_MCP_RUNTIME")
    if env:
        return Path(env).expanduser().resolve()
    parts = ROOT.parts
    on_windows_mount = len(parts) > 2 and parts[1] == "mnt" and len(parts[2]) == 1
    if on_windows_mount:
        return Path.home().resolve() / "su-mcp-runtime"
    return ROOT


RUNTIME_ROOT = _resolve_runtime()

RAW_DIR = ROOT / "raw"                  # field data, read-only for the agent
RESULT_DIR = ROOT / "results"           # final deliverables
QC_DIR = ROOT / "qc"                    # figures and QC output
def _resolve_log_dir():
    """Where the processing log lives."""
    declared = os.environ.get("SU_MCP_LOG_DIR", "").strip()
    return Path(declared).expanduser().resolve() if declared else ROOT / "logs"


LOG_DIR = _resolve_log_dir()            # provenance
# dataset manifests - domain layer only; SU_MCP_STATE moves them (evaluation deployments only)
STATE_DIR = (Path(os.environ["SU_MCP_STATE"]).expanduser().resolve() if os.environ.get("SU_MCP_STATE")
             else ROOT / "state")

WORK_DIR = RUNTIME_ROOT / "work"        # intermediate processing products
JOB_DIR = RUNTIME_ROOT / "jobs"         # background analysis jobs
TMP_DIR = RUNTIME_ROOT / "tmp"          # scratch

def _data_dirs() -> tuple:
    """Read-only directories of field data, besides raw/."""
    declared = os.environ.get("SU_MCP_DATA_DIRS", "")
    if declared.strip():
        found = [Path(p).expanduser().resolve()
                 for p in declared.split(os.pathsep) if p.strip()]
    else:
        found = [ROOT / name for name in ("data", "test_dataset")]
    return tuple(d for d in found if d.is_dir())


DATA_DIRS = _data_dirs()

# The names the agent uses.
DIR_ALIASES = {
    "raw": RAW_DIR, "work": WORK_DIR, "results": RESULT_DIR,
    "qc": QC_DIR, "logs": LOG_DIR, "state": STATE_DIR,
}
DIR_ALIASES.update({d.name: d for d in DATA_DIRS})

PROJECT_DIRS = (RAW_DIR, WORK_DIR, RESULT_DIR, QC_DIR, LOG_DIR, STATE_DIR,
                JOB_DIR, TMP_DIR) + DATA_DIRS
READABLE_DIRS = (RAW_DIR, WORK_DIR, RESULT_DIR, QC_DIR) + DATA_DIRS
WRITABLE_DIRS = (WORK_DIR, RESULT_DIR, QC_DIR)

PROCESSING_LOG = LOG_DIR / "processing.jsonl"
DATASET_DIR = STATE_DIR / "datasets"

# A dataset identifier names a manifest file, so keep it to a safe slug.
DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# --------------------------------------------------------------------------- Command
# policy,------------------------------------------------------------------------- The agent may run these on any
# readable file, because none of them can turn unvalidated data into a result that looks validated.
ALLOWED_SU_COMMANDS = frozenset({
    "surange",    # header ranges
    "sugethw",    # header values
    "suwind",     # trace / time windowing
    "sugain",     # gain, agc, scaling
    "sufilter",   # zero-phase sine-squared bandpass
    "susort",     # sort by header keys
})

# Programs the domain layer may call although the agent may not reach them through su_run.
TRUSTED_SU_COMMANDS = frozenset({
    "segyread",     # SEG-Y -> SU
    "segyhdrs",     # make the textual/binary header files
    "segywrite",    # SU -> SEG-Y (test fixtures, export)
    # The interpretive steps.
    "sunmo",        # NMO, behind velocity.validated
    "sustack",      # stack, behind nmo.applied
    "sustatic",     # acquisition-log statics, only from validated header words
    # v0.19 conditioning menu: reachable only through condition_gathers, which builds their arguments from the
    # registry and gates the result on signal preservation.
    "sufilter", "sugain", "sumute", "sudipfilt", "supef",
    # v0.20: residual statics (surface-consistent, Ronen-Claerbout), driven only by condition_gathers, which
    # writes its temporary inputs and the ssol/rsol output paths itself; and suwind for the scoped stack (S1),
    # whose cdp range comes from the validated velocity model, never from the agent.
    "suresstat",
    "suwind",
    # v0.24: post-stack phase-shift time migration, only through migrate_stack, which builds the velocity file
    # from the validated model and releases the section only after the impulse gate (M1).
    "sumigps",
    # v0.26: dip moveout, only as condition_gathers' "dmo" operation; susort is also ALLOWED for inspection, here
    # it may write the product DMO reads.
    "sudmofk", "susort",
    # v0.28: post-stack depth migration, only through migrate_stack "depth_pspi" (velocity file built from the
    # validated model, released after Z1).
    "sumigpspi",
})

# SU takes every argument as key=value.
PARAM_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
PARAM_VALUE_RE = re.compile(r"^[A-Za-z0-9_.,:+\-]{0,512}$")

# Parameters that make an SU program touch the filesystem on its own.
DENIED_PARAM_KEYS = frozenset({
    "par", "outpar", "datain", "dataout", "tmpdir", "file", "infile",
    "outfile", "hfile", "bfile", "xfile", "tape", "vfile", "wfile",
})

# ---------------------------------------------------------------------------
# Limits,-------------------------------------------------------------------------
WORKER_TIMEOUT = 45       # a synchronous tool call, inside the MCP 60 s limit
TIMEOUT_QUICK = 20        # sudoc / sufind
TIMEOUT_INSPECT = 300     # surange over a whole line
TIMEOUT_RUN = 3600        # a processing step
MAX_TEXT_CHARS = 20000    # cap on text returned to the model
HASH_SIZE_LIMIT = 512 * 1024 * 1024   # sha256 outputs up to 512 MB
