"""Run tool calls in worker processes, synchronously or as background jobs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config

__all__ = ["call", "start_job", "job_status", "job_result", "cancel_job",
           "list_jobs", "JobError"]

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class JobError(ValueError):
    """A job id that does not name a job, or a job in the wrong state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _python() -> str:
    return os.environ.get("SU_MCP_PYTHON") or sys.executable


def _job_file(job_id: str) -> Path:
    if not config.DATASET_ID_RE.match(job_id or ""):
        raise JobError(f"Not a job id: {job_id!r}")
    path = config.JOB_DIR / f"{job_id}.json"
    if not path.exists():
        raise JobError(f"No job {job_id!r}. Known jobs: "
                       + (", ".join(sorted(j['job_id'] for j in list_jobs())) or "none"))
    return path


# ---------------------------------------------------------------- synchronous
def call(tool: str, arguments: dict, timeout: float | None = None) -> dict:
    """Run one tool in a worker process and return its result."""
    timeout = config.WORKER_TIMEOUT if timeout is None else timeout
    request = json.dumps({"tool": tool, "arguments": arguments})
    started = time.monotonic()
    try:
        done = subprocess.run(
            [_python(), "-m", "sumcp.worker"], input=request, capture_output=True,
            text=True, cwd=str(_PACKAGE_ROOT), timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "error_type": "Timeout",
            "error": (f"{tool} did not finish within {timeout:g}s. Run it as a "
                      f"background job (run_as_job=true) or reduce its scope."),
            "elapsed_s": round(time.monotonic() - started, 2),
        }
    elapsed = round(time.monotonic() - started, 2)
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False, "error_type": "WorkerFailed",
            "error": f"{tool} produced no result (exit {done.returncode}).",
            "stderr": (done.stderr or "")[-config.MAX_TEXT_CHARS:],
            "elapsed_s": elapsed,
        }
    if done.stderr.strip():
        result.setdefault("worker_stderr", done.stderr[-4000:])
    result.setdefault("elapsed_s", elapsed)
    return result


# ---------------------------------------------------------------------- jobs
def start_job(tool: str, arguments: dict) -> dict:
    config.JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_id = f"j{uuid.uuid4().hex[:11]}"
    path = config.JOB_DIR / f"{job_id}.json"
    path.write_text(json.dumps({
        "job_id": job_id, "tool": tool, "arguments": arguments,
        "started": _now(),
    }), encoding="utf-8")
    # The child dups the descriptor, so the server closes its own copy at once; a long-lived server that leaked
    # one per job would run out of them.
    with path.with_suffix(".log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [_python(), "-m", "sumcp.worker", "--job", str(path)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            cwd=str(_PACKAGE_ROOT), start_new_session=True,
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    record["pid"] = proc.pid
    path.write_text(json.dumps(record), encoding="utf-8")
    return {"job_id": job_id, "tool": tool, "status": "running",
            "started": record["started"]}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def job_status(job_id: str) -> dict:
    path = _job_file(job_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    result_path = path.with_suffix(".result.json")
    if result_path.exists():
        status = "cancelled" if record.get("cancelled") else "finished"
    elif record.get("cancelled"):
        status = "cancelled"
    elif _alive(int(record.get("pid", -1))):
        status = "running"
    else:
        status = "died"
    out = {"job_id": job_id, "tool": record["tool"], "status": status,
           "started": record["started"]}
    if status == "died":
        log = path.with_suffix(".log")
        out["error"] = "The worker exited without writing a result."
        if log.exists():
            out["log_tail"] = log.read_text(encoding="utf-8")[-4000:]
    return out


def job_result(job_id: str) -> dict:
    path = _job_file(job_id)
    result_path = path.with_suffix(".result.json")
    if not result_path.exists():
        state = job_status(job_id)
        raise JobError(
            f"Job {job_id} is {state['status']}; there is no result to read yet.")
    return json.loads(result_path.read_text(encoding="utf-8"))


def cancel_job(job_id: str) -> dict:
    path = _job_file(job_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    pid = int(record.get("pid", -1))
    if _alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    record["cancelled"] = _now()
    path.write_text(json.dumps(record), encoding="utf-8")
    return {"job_id": job_id, "status": "cancelled"}


def list_jobs(limit: int = 20) -> list:
    if not config.JOB_DIR.exists():
        return []
    files = sorted(config.JOB_DIR.glob("j*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for path in files:
        if path.name.endswith(".result.json"):
            continue
        try:
            out.append(job_status(path.stem))
        except (JobError, json.JSONDecodeError, OSError):
            continue
        if len(out) >= limit:
            break
    return out
