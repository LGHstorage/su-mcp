"""Append-only processing log."""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .paths import as_rel

__all__ = ["new_run_id", "file_fingerprint", "record", "read_log",
           "AUDIT_VERSION", "note_execution", "note_gate", "note_artifact",
           "audit_call", "audited"]


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def file_fingerprint(path) -> dict:
    """Size, mtime and (for reasonably sized files) a sha256."""
    path = Path(path)
    if not path.exists():
        return {"exists": False}
    size = path.stat().st_size
    info = {
        "exists": True,
        "bytes": size,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }
    if size <= config.HASH_SIZE_LIMIT:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        info["sha256"] = digest.hexdigest()
    return info


LOG_RETRIES = 8


def record(entry: dict) -> dict:
    """Timestamp an entry, append it to the log, return it."""
    full = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        **entry,
    }
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(full, ensure_ascii=False) + "\n"
    # v0.23 L1: parallel tool calls on a Windows-mounted project can meet a transient file lock (PermissionError);
    # wait it out before giving up.
    for attempt in range(LOG_RETRIES):
        try:
            with open(config.PROCESSING_LOG, "a", encoding="utf-8") as fh:
                fh.write(line)
            break
        except PermissionError:
            if attempt == LOG_RETRIES - 1:
                raise
            time.sleep(min(0.8, 0.1 * (attempt + 1)))
    return full


def read_log(limit: int = 50) -> list:
    """The most recent log entries, oldest first."""
    if not config.PROCESSING_LOG.exists():
        return []
    with open(config.PROCESSING_LOG, encoding="utf-8") as fh:
        lines = fh.readlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out




# --------------------------------------------------------------------------- Tool-call audit
# trail,------------------------------------------------------------------------- The log used to record only what
# succeeded in a few domain modules.

AUDIT_VERSION = "audit-0.2"

_AUDIT = None          # one tool call per worker process; see sumcp/worker.py


def note_execution(command: str, argv=None, returncode: int = 0,
                   elapsed_s=None) -> None:
    """Record that an SU program started."""
    if _AUDIT is None:
        return
    _AUDIT["commands"].append({
        "command": command,
        "argv": [str(a) for a in (argv or [command])],
        "returncode": int(returncode),
        "elapsed_s": elapsed_s,
    })


def note_gate(capability: str, status: str, kind: str = "required",
              detail=None) -> None:
    """A capability was consulted (kind='required') or written (kind='set')."""
    if _AUDIT is None:
        return
    entry = {"capability": capability, "status": status, "kind": kind}
    if detail:
        entry["detail"] = detail
    _AUDIT["gates"].append(entry)


def note_artifact(path, role=None) -> None:
    if _AUDIT is None:
        return
    _AUDIT["artifacts"].append({"path": as_rel(path), "role": role})


def _decide_gate(gates, refused: bool):
    """Which single capability decided this call, if any."""
    if refused:
        for g in gates:
            if g["kind"] == "required" and g["status"] != "PASS":
                return g["capability"], g["status"]
    for g in gates:
        if g["kind"] == "set" and g["status"] == "FAIL":
            return g["capability"], g["status"]
    return None, None


def audit_call(tool: str, arguments: dict, fn):
    """Run one tool call and write its audit entry, whatever the outcome."""
    global _AUDIT
    if _AUDIT is not None:                 # nested call: still one entry per tool
        return fn()
    _AUDIT = {"commands": [], "gates": [], "artifacts": []}
    started = time.monotonic()
    result = error = None
    try:
        result = fn()
        return result
    except BaseException as exc:           # noqa: BLE001 - re-raised by `raise`
        error = exc
        raise
    finally:
        collected, _AUDIT = _AUDIT, None
        try:
            _write_audit(tool, arguments, result, error, collected,
                         round(time.monotonic() - started, 3))
        except Exception:                  # noqa: BLE001
            pass                           # logging must never break a call


def _write_audit(tool, arguments, result, error, collected, elapsed) -> None:
    if isinstance(result, dict):
        ok = bool(result.get("ok", True))
        error_type = result.get("error_type")
        reason = None if ok else result.get("error")
    else:
        ok = error is None
        error_type = type(error).__name__ if error else None
        reason = str(error) if error else None

    status = "SUCCESS" if ok else (
        "REFUSED" if error_type == "PrerequisiteError" else "ERROR")
    gate, gate_status = _decide_gate(collected["gates"], status == "REFUSED")
    commands = collected["commands"]
    record({
        "kind": "tool_call",
        "audit_version": AUDIT_VERSION,
        "tool": tool,
        "dataset": arguments.get("dataset_id"),
        "status": status,
        "gate": gate,
        "gate_status": gate_status,
        "gate_evaluation": collected["gates"],
        "underlying_commands_executed": sorted({c["command"] for c in commands}),
        "commands_detail": commands,
        "artifacts_created": [a["path"] for a in collected["artifacts"]],
        "refusal_reason": reason,
        "error_type": error_type,
        "arguments": {k: v for k, v in arguments.items() if v is not None},
        "elapsed_s": elapsed,
    })


def audited(tool: str):
    """Decorator applied to every public function in sumcp/tools.py."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                bound = inspect.signature(fn).bind_partial(*args, **kwargs)
                arguments = dict(bound.arguments)
            except TypeError:
                arguments = dict(kwargs)
            return audit_call(tool, arguments, lambda: fn(*args, **kwargs))
        inner.__wrapped_tool__ = tool
        return inner
    return wrap


class Timer:
    """Wall-clock timer for a processing step."""

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.monotonic() - self._t0, 3)
        return False
