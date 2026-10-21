"""Execution of SU programs."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import config, provenance
from .suenv import find_program, su_env

__all__ = [
    "CommandNotAllowed", "ParameterError", "SURunError",
    "format_param", "validate_params", "resolve_command",
    "run_single", "run_chain", "capture_text", "run_trusted",
]


class CommandNotAllowed(PermissionError):
    """The requested SU program is outside the allowlist for this version."""


class ParameterError(ValueError):
    """A parameter name or value failed validation."""


class SURunError(RuntimeError):
    """An SU program exited non-zero."""


def format_param(key: str, value) -> str:
    """Turn a Python value into SU's ``key=value`` argument form."""
    if isinstance(value, bool):
        rendered = "1" if value else "0"
    elif isinstance(value, (list, tuple)):
        rendered = ",".join(format_scalar(v) for v in value)
    else:
        rendered = format_scalar(value)
    return f"{key}={rendered}"


def format_scalar(value) -> str:
    if isinstance(value, float):
        # Avoid 1e-05 style output; SU's parser wants plain decimals.
        text = repr(round(value, 9))
        if "e" in text or "E" in text:
            text = f"{value:.9f}".rstrip("0").rstrip(".")
        return text
    return str(value)


def validate_params(params: dict | None) -> list:
    """Validate and render parameters, returning the argv fragment."""
    if not params:
        return []
    if not isinstance(params, dict):
        raise ParameterError("params must be an object of key/value pairs.")
    argv = []
    for key, value in params.items():
        key = str(key)
        if not config.PARAM_KEY_RE.match(key):
            raise ParameterError(f"Invalid parameter name: {key!r}")
        if key.lower() in config.DENIED_PARAM_KEYS:
            raise ParameterError(
                f"Parameter {key!r} lets the program open its own file and is not allowed."
            )
        if isinstance(value, (list, tuple)) and value and all(
                isinstance(v, (list, tuple)) for v in value):
            # One argument per inner list: sunmo takes a tnmo=/vnmo= pair for every cdp it is given, which a dict
            # of unique keys cannot say.
            for item in value:
                arg = format_param(key, item)
                rendered = arg.split("=", 1)[1]
                if not config.PARAM_VALUE_RE.match(rendered):
                    raise ParameterError(
                        f"Invalid value for {key!r}: {rendered!r} "
                        "(letters, digits and . , : + - _ only; no paths or spaces)"
                    )
                argv.append(arg)
            continue
        if value is None:
            # A few SU programs take bare key names rather than key=value, susort's sort keys are the reason this
            # exists.
            argv.append(key)
            continue
        arg = format_param(key, value)
        rendered = arg.split("=", 1)[1]
        if not config.PARAM_VALUE_RE.match(rendered):
            raise ParameterError(
                f"Invalid value for {key!r}: {rendered!r} "
                "(letters, digits and . , : + - _ only; no paths or spaces)"
            )
        argv.append(arg)
    return argv


def resolve_command(command: str) -> str:
    """Check the allowlist, then locate the executable."""
    command = str(command).strip()
    if command not in config.ALLOWED_SU_COMMANDS:
        detail = ""
        if command in config.TRUSTED_SU_COMMANDS:
            detail = (f" {command} runs only from the tool that owns that step, "
                      f"after the evidence for it has been checked; a refusal "
                      f"that could be walked around by calling the program "
                      f"directly would not be a refusal.")
        raise CommandNotAllowed(
            f"{command!r} is not in the set su_run may call.{detail} Allowed: "
            + ", ".join(sorted(config.ALLOWED_SU_COMMANDS))
        )
    path = find_program(command)
    if path is None:
        raise SURunError(f"SU program not found on this system: {command}")
    return path


def _tail(data: bytes, limit: int = 4000) -> str:
    text = data.decode("utf-8", errors="replace").strip()
    return text[-limit:]


def run_single(command: str, infile: Path, outfile: Path, params: dict | None,
               timeout: int = config.TIMEOUT_RUN) -> dict:
    """Run one SU program with stdin from infile and stdout to outfile."""
    executable = resolve_command(command)
    argv = [executable] + validate_params(params)
    started = time.monotonic()
    with open(infile, "rb") as fin, open(outfile, "wb") as fout:
        proc = subprocess.run(
            argv, stdin=fin, stdout=fout, stderr=subprocess.PIPE,
            env=su_env(), timeout=timeout, shell=False,
        )
    elapsed = round(time.monotonic() - started, 3)
    stderr = _tail(proc.stderr)
    provenance.note_execution(command, [command] + argv[1:], proc.returncode, elapsed)
    if proc.returncode != 0:
        raise SURunError(f"{command} exited {proc.returncode}: {stderr or '(no message)'}")
    return {"argv": [command] + argv[1:], "returncode": proc.returncode,
            "stderr": stderr, "elapsed_s": elapsed}


def run_chain(steps, infile: Path, outfile: Path,
              timeout: int = config.TIMEOUT_RUN) -> dict:
    """Run several SU programs joined by pipes, as SU is meant to be used."""
    if not steps:
        raise ParameterError("A pipeline needs at least one step.")
    prepared = []
    for step in steps:
        command = step.get("command") if isinstance(step, dict) else None
        if not command:
            raise ParameterError("Each pipeline step needs a 'command'.")
        executable = resolve_command(command)
        argv = [executable] + validate_params(step.get("params"))
        prepared.append((command, argv))

    procs = []
    try:
        with open(infile, "rb") as fin, open(outfile, "wb") as fout:
            stdin = fin
            for index, (_, argv) in enumerate(prepared):
                last = index == len(prepared) - 1
                proc = subprocess.Popen(
                    argv,
                    stdin=stdin,
                    stdout=fout if last else subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=su_env(), shell=False,
                )
                if stdin is not fin:
                    stdin.close()          # let the upstream process see EOF
                stdin = proc.stdout
                procs.append(proc)
            errors = [p.communicate(timeout=timeout)[1] for p in procs]
    except subprocess.TimeoutExpired:
        for p in procs:
            p.kill()
        raise

    report = []
    for (command, argv), proc, err in zip(prepared, procs, errors):
        report.append({
            "command": command,
            "argv": [command] + argv[1:],
            "returncode": proc.returncode,
            "stderr": _tail(err or b""),
        })
        provenance.note_execution(command, [command] + argv[1:], proc.returncode)
    failed = [r for r in report if r["returncode"] != 0]
    if failed:
        first = failed[0]
        raise SURunError(
            f"{first['command']} exited {first['returncode']}: "
            f"{first['stderr'] or '(no message)'}"
        )
    return {"steps": report}


def run_trusted(command: str, args, stdout_path: Path | None = None,
                stdin_path: Path | None = None,
                timeout: int = config.TIMEOUT_RUN) -> dict:
    """Run a program from TRUSTED_SU_COMMANDS with arguments built by the caller."""
    if command not in config.TRUSTED_SU_COMMANDS:
        raise CommandNotAllowed(f"{command!r} is not a trusted domain program.")
    executable = find_program(command)
    if executable is None:
        raise SURunError(f"SU program not found on this system: {command}")
    argv = [executable] + [str(a) for a in args]
    stdin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    stdout = open(stdout_path, "wb") if stdout_path else subprocess.PIPE
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, stdin=stdin, stdout=stdout,
                              stderr=subprocess.PIPE, env=su_env(),
                              timeout=timeout, shell=False)
    finally:
        for handle in (stdin, stdout):
            if hasattr(handle, "close"):
                handle.close()
    elapsed = round(time.monotonic() - started, 3)
    stderr = _tail(proc.stderr)
    provenance.note_execution(command, [command] + [str(a) for a in args],
                              proc.returncode, elapsed)
    if proc.returncode != 0:
        raise SURunError(f"{command} exited {proc.returncode}: {stderr or '(no message)'}")
    return {
        "argv": [command] + [str(a) for a in args],
        "returncode": proc.returncode,
        "stderr": stderr,
        "elapsed_s": elapsed,
        "stdout": b"" if stdout_path else (proc.stdout or b""),
    }


def capture_text(command: str, args=(), stdin_path: Path | None = None,
                 timeout: int = config.TIMEOUT_QUICK, allowlisted: bool = True) -> str:
    """Run an SU program and capture its text output (for surange, sudoc, sufind)."""
    executable = resolve_command(command) if allowlisted else find_program(command)
    if executable is None:
        raise SURunError(f"SU program not found on this system: {command}")
    argv = [executable] + [str(a) for a in args]
    if stdin_path is not None:
        with open(stdin_path, "rb") as fin:
            proc = subprocess.run(argv, stdin=fin, capture_output=True,
                                  env=su_env(), timeout=timeout, shell=False)
    else:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                              env=su_env(), timeout=timeout, shell=False)
    provenance.note_execution(command, [command] + [str(a) for a in args],
                              proc.returncode)
    text = proc.stdout.decode("utf-8", errors="replace") + \
        proc.stderr.decode("utf-8", errors="replace")
    return text[: config.MAX_TEXT_CHARS]
