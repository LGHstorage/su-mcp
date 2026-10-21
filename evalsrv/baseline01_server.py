"""Baseline study 01 evaluation server for conditions A and B (B01_MODE=A or B)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evalsrv import b01core as C  # noqa: E402

MODE = os.environ.get("B01_MODE", "").strip().upper()
if MODE not in ("A", "B"):
    raise SystemExit("B01_MODE must be A or B")
C.paths()   # fails fast unless the evaluation environment is set

PROGRAMS = ", ".join(sorted(C.SU_PROGRAMS))
TEXT = ", ".join(sorted(C.TEXT_TOOLS))
COMMON = f"""\
Seismic Unix programs for a 2D seismic processing task (evaluation environment).
SU programs available: {PROGRAMS}. Read their documentation with program_doc.
Every call names the run you were given (`run`); files you write live in that run's directory, and the input data
are read from {C.paths()['input']}. Numbers only: there is no image display.
Budgets per run: {C.BUDGET['processing_actions']} processing actions (calls that write a file),
{C.BUDGET['velocity_actions']} velocity-analysis actions (a new suvelan parameterisation or input file),
{C.BUDGET['conditioning_passes']} conditioning passes (a call that writes a file with sufilter, sugain, sumute,
sudipfilt, supef, sustatic or sudmofk applied to a whole file; a call that first selects traces with suwind does
not count as a pass), {C.BUDGET['tool_calls']} tool calls. Call budget(run) to see them.
Header writes (sushw, suchw) are limited to: {', '.join(sorted(C.HEADER_WRITE_KEYS))}.
"""
if MODE == "A":
    INSTRUCTIONS = COMMON + f"""
Run SU programs by writing shell scripts with shell(run, script): simple commands joined by |, ;, && and newlines,
with < > >> redirections at the end of a command. Text tools available in scripts: {TEXT}. No variables,
substitutions, subshells, background jobs or other programs.
"""
else:
    INSTRUCTIONS = COMMON + """
Run SU programs with run_program(run, program, params, input, output) or a chain of them with
run_pipeline(run, steps, input, output); params are key/value pairs as SU takes them, and a list value repeats
the key (for example several tnmo=/vnmo= pairs for sunmo). Without `output`, the text
the last program prints is returned. Read text files with read_text.
"""

try:
    from mcp.server import MCPServer
    mcp = MCPServer(name=f"su-baseline01-{MODE.lower()}", title=f"SU baseline01 condition {MODE}",
                    version="b01-0.1", instructions=INSTRUCTIONS)
except ImportError:                                   # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(f"su-baseline01-{MODE.lower()}", instructions=INSTRUCTIONS)


def _safe(fn, *a, count=None, **k):
    try:
        if count:
            C.tick(count)
        out = fn(*a, **k)
        return out if isinstance(out, dict) else {"ok": True, "result": out}
    except C.PolicyError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:                          # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
def program_doc(run: str, program: str) -> dict:
    """Documentation (sudoc) of one available SU program."""
    return _safe(C.program_doc, program, count=run)


@mcp.tool()
def list_files(run: str) -> dict:
    """Files in the run directory and in the input directory."""
    return _safe(C.list_files, run, count=run)


@mcp.tool()
def read_text(run: str, name: str, max_chars: int = C.TEXT_LIMIT) -> dict:
    """Read a text file from the run or input directory (not seismic files)."""
    return _safe(C.read_text, run, name, max_chars, count=run)


@mcp.tool()
def submit_artifact(run: str, name: str) -> dict:
    """Hand in the file from your run directory that your final report names as the artifact."""
    return _safe(C.submit, run, name, count=run)


@mcp.tool()
def budget(run: str) -> dict:
    """Budget used and left for this run."""
    return _safe(C.budget, run)


if MODE == "A":
    @mcp.tool()
    def shell(run: str, script: str) -> dict:
        """Run a script of allowlisted SU programs and text tools in the run directory; returns stdout (up to
        20000 characters) and stderr."""
        return _safe(C.shell, run, script)
else:
    @mcp.tool()
    def run_program(run: str, program: str, params: dict | None = None, input: str | None = None,
                    output: str | None = None) -> dict:
        """Run one SU program: stdin from `input`, stdout to `output` (or returned as text, up to 20000
        characters)."""
        return _safe(C.run_program, run, program, params, input, output)

    @mcp.tool()
    def run_pipeline(run: str, steps: list, input: str | None = None, output: str | None = None) -> dict:
        """Run SU programs in a chain: steps = [{"program": ..., "params": {...}}, ...]."""
        return _safe(C.run_pipeline, run, steps, input, output)


if __name__ == "__main__":
    mcp.run()
