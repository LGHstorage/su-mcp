"""Locating and running the CWP/SU installation."""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

__all__ = ["cwproot", "su_bindir", "find_program", "su_env", "list_programs",
           "su_output_byte_order"]


def cwproot() -> Path | None:
    value = os.environ.get("CWPROOT")
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_dir() else None


def su_bindir() -> Path | None:
    root = cwproot()
    if root is None:
        return None
    bindir = root / "bin"
    return bindir if bindir.is_dir() else None


def find_program(name: str) -> str | None:
    """Absolute path of an SU program, or None."""
    if not name or "/" in name or name.startswith("."):
        return None
    bindir = su_bindir()
    if bindir is not None:
        candidate = bindir / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)


def su_env() -> dict:
    """Environment for SU child processes: no pager, bin on PATH."""
    env = os.environ.copy()
    env["PAGER"] = "cat"
    env["MANPAGER"] = "cat"
    env["LC_ALL"] = "C"
    bindir = su_bindir()
    if bindir is not None:
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    return env


@lru_cache(maxsize=1)
def list_programs() -> tuple:
    """Every executable in $CWPROOT/bin, sorted."""
    bindir = su_bindir()
    if bindir is None:
        return ()
    names = [
        p.name for p in bindir.iterdir()
        if p.is_file() and os.access(p, os.X_OK)
    ]
    return tuple(sorted(names))


@lru_cache(maxsize=1)
def su_output_byte_order() -> dict:
    """Ask the installation which byte order it writes SU files in."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    program = find_program("suplane")
    if program is None:
        return {"detected": None, "reason": "suplane not found"}
    try:
        from .sufile import detect_byte_order, SUFormatError
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "probe.su"
            with open(probe, "wb") as out:
                subprocess.run([program, "nt=16", "ntr=2"], stdout=out,
                               stderr=subprocess.DEVNULL, env=su_env(),
                               timeout=30, check=True)
            order, ns, dt = detect_byte_order(probe)
    except (subprocess.SubprocessError, OSError, Exception) as exc:  # noqa: BLE001
        return {"detected": None, "reason": str(exc)}
    name = {"<": "little", ">": "big"}[order]
    return {
        "detected": name,
        "machine": sys.byteorder,
        "xdr_build": name != sys.byteorder,
        "probe": {"ns": ns, "dt_us": dt},
    }
