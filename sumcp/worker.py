"""Run exactly one tool call, in a process of its own, and print its result."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

__all__ = ["run", "main"]


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.flush()


def run(tool: str, arguments: dict) -> dict:
    """Import the tool layer and call one function from it."""
    from . import tools                      # imported here, never at module load
    fn = getattr(tools, tool, None)
    if fn is None or tool not in getattr(tools, "__all__", ()):
        return {"ok": False, "error": f"Unknown tool {tool!r}.",
                "error_type": "UnknownTool"}
    from . import governance
    return governance.scrub(tool, fn(**arguments))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    job_path = None
    if argv[:1] == ["--job"]:
        job_path = Path(argv[1])
        request = json.loads(job_path.read_text(encoding="utf-8"))
    else:
        request = json.loads(sys.stdin.read() or "{}")

    tool = request.get("tool", "")
    arguments = request.get("arguments") or {}

    # Real work writes to stdout at its peril; give it stderr instead.
    saved, sys.stdout = sys.stdout, sys.stderr
    try:
        result = run(tool, arguments)
    except Exception as exc:                                   # noqa: BLE001
        traceback.print_exc()
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                  "error_type": type(exc).__name__}
    finally:
        sys.stdout = saved

    if job_path is not None:
        out = job_path.with_suffix(".result.json")
        tmp = out.with_suffix(".part")
        tmp.write_text(json.dumps(result, default=str), encoding="utf-8")
        os.replace(tmp, out)
        return 0
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
