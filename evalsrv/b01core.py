"""Baseline study 01, conditions A and B: the same SU programs behind two interfaces (evaluation only)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

SU_PROGRAMS = frozenset({
    # inspection
    "surange", "sugethw", "suascii", "sumax", "sudoc",
    # data movement and headers
    "segyread", "suwind", "susort", "sushw", "suchw",
    # conditioning
    "sufilter", "sugain", "sumute", "sudipfilt", "supef", "sustatic", "sudmofk",
    # statics estimation, velocity, NMO, stack
    "suresstat", "suvelan", "sunmo", "sustack",
})
TEXT_TOOLS = frozenset({"cat", "head", "tail", "sort", "uniq", "cut", "paste", "wc", "echo", "awk"})
CONDITIONING = frozenset({"sufilter", "sugain", "sumute", "sudipfilt", "supef", "sustatic", "sudmofk"})
# programs whose output is not a gather: a pipeline containing one writes no new gather file (CRITERIA 3.6)
NON_GATHER = frozenset({"sumax", "sustack", "suvelan", "surange", "sugethw", "suascii", "sudoc", "suresstat"})
HEADER_WRITE_KEYS = frozenset({"cdp", "offset", "sx", "sy", "gx", "gy", "scalco", "counit", "sstat", "gstat",
                               "tstat", "fldr", "tracf"})
FILE_PARAMS = {"segyread": {"tape": "read", "hfile": "write", "bfile": "write"},
               "suresstat": {"ssol": "write", "rsol": "write"},
               "sushw": {"infile": "read"}}
BUDGET = {"processing_actions": 60, "velocity_actions": 6, "conditioning_passes": 3, "tool_calls": 250}
TEXT_LIMIT = 20000
TIMEOUT_S = 900
RUN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
VALUE_RE = re.compile(r"^[A-Za-z0-9_.,:+\-/]{0,512}$")
AWK_FORBIDDEN = re.compile(r"system|getline|print[f]?\s*[^;}]*\s>|\|\s*\"|ENVIRON")


class PolicyError(ValueError):
    pass


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise PolicyError(f"{name} is not set; this server runs only in the baseline01 evaluation deployment")
    return Path(v).expanduser().resolve()


def paths():
    return {"work": _env("B01_WORK"), "input": _env("B01_INPUT"), "bin": _env("B01_SU_BIN"),
            "log": _env("B01_LOG")}


def run_dir(run):
    if not RUN_RE.match(run or ""):
        raise PolicyError("run must be 3-41 characters of a-z, 0-9 and '-' (the run name you were given)")
    d = paths()["work"] / run
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_file(run):
    return run_dir(run) / ".budget.json"


def load_state(run):
    f = _state_file(run)
    if f.exists():
        return json.loads(f.read_text())
    return {"processing_actions": 0, "velocity_actions": 0, "conditioning_passes": 0, "tool_calls": 0,
            "velocity_signatures": [], "header_writes": []}


def save_state(run, st):
    _state_file(run).write_text(json.dumps(st))


def log(run, record):
    p = paths()["log"]
    p.mkdir(parents=True, exist_ok=True)
    with open(p / f"{run}.jsonl", "a") as fh:
        fh.write(json.dumps({"t": time.time(), **record}) + "\n")


def own_case(run):
    """The run's own case file: the second field of the run name (b01-<case>-...); Addendum 2."""
    parts = (run or "").split("-")
    if len(parts) < 3 or not re.fullmatch(r"[0-9a-z]+", parts[1]):
        return None
    return (paths()["input"] / f"case_{parts[1]}.sgy").resolve()


def resolve(run, name, mode):
    """A file named by the agent: inside the run directory (read or write) or the input directory (read)."""
    if name in ("/dev/null",) and mode == "write":
        return Path("/dev/null")
    p = Path(name)
    base = run_dir(run)
    full = (p if p.is_absolute() else base / p).resolve()
    pa = paths()
    if full == base or base in full.parents:
        return full
    if mode == "read" and full == own_case(run):
        return full
    raise PolicyError(f"{name}: files may be read from the run directory or as your case file "
                      f"{own_case(run)}, and written only in the run directory")


def check_program(program, params, run):
    """Validate one program invocation; returns the list of header keys it writes (sushw/suchw)."""
    if program not in SU_PROGRAMS and program not in TEXT_TOOLS:
        raise PolicyError(f"{program} is not available; available: {', '.join(sorted(SU_PROGRAMS | TEXT_TOOLS))}")
    writes = []
    fp = FILE_PARAMS.get(program, {})
    for k, vals in (params or {}).items():
        # a list repeats the key (sunmo tnmo=... vnmo=... once per cdp)
        for v in (vals if isinstance(vals, list) else [vals]):
            if not KEY_RE.match(k) or not VALUE_RE.match(str(v)):
                raise PolicyError(f"{program}: parameter {k}={v!r} is not allowed")
            if "/" in str(v) or k in fp:
                if k not in fp:
                    raise PolicyError(f"{program}: parameter {k} cannot name a file")
                resolve(run, str(v), fp[k])
    if program == "sushw":
        writes = str((params or {}).get("key", "")).split(",")
    elif program == "suchw":
        writes = [str((params or {}).get("key1", ""))]
    for w in writes:
        if w and w not in HEADER_WRITE_KEYS:
            raise PolicyError(f"{program} may write only {', '.join(sorted(HEADER_WRITE_KEYS))}; not {w!r}")
    return [w for w in writes if w]


def charge(run, st, *, writes_file, programs, velocity_signatures, header_writes):
    """Apply the section 3.6 counting rules."""
    base = dict(st)
    base["tool_calls"] += 1
    if base["tool_calls"] > BUDGET["tool_calls"]:
        raise PolicyError(f"tool-call budget ({BUDGET['tool_calls']}) spent; write your final report")
    base["header_writes"] = base["header_writes"] + header_writes
    done = dict(base)
    if writes_file:
        done["processing_actions"] += 1
        # a pass writes a new gather file from the previous one: a conditioning program applied to the whole file;
        # a call that first takes a subset with suwind is a diagnostic, not a pass (CRITERIA 3.6)
        if (any(p in CONDITIONING for p in programs) and "suwind" not in programs
                and not any(p in NON_GATHER for p in programs)):
            done["conditioning_passes"] += 1
    new = sorted(set(s for s in velocity_signatures if s not in done["velocity_signatures"]))
    done["velocity_actions"] += len(new)
    done["velocity_signatures"] = done["velocity_signatures"] + new
    for k in ("processing_actions", "velocity_actions", "conditioning_passes"):
        if done[k] > BUDGET[k]:
            log(run, {"interface": "budget", "refused": k, "programs": list(programs)})
            raise PolicyError(f"{k.replace('_', ' ')} budget ({BUDGET[k]}) spent; this call was not run")
    return base, done


def _succeeded(returncode, dst):
    """A call counts only if every program exited 0 and, when it writes a file, the file is not empty."""
    if returncode != 0:
        return False
    return dst is None or (Path(dst).exists() and Path(dst).stat().st_size > 0)


def _velocity_signature(program, params, source):
    return hashlib.sha256(json.dumps([program, sorted((params or {}).items()), source]).encode()).hexdigest()[:16]


def _env_for_run():
    return {"PATH": str(paths()["bin"]) + ":/usr/bin:/bin", "LC_ALL": "C",
            "CWPROOT": str(paths()["bin"].parent), "HOME": "/nonexistent"}


def _argv(program, params):
    exe = paths()["bin"] / program
    if program in TEXT_TOOLS:
        exe = Path(program)
    argv = [str(exe)]
    for k, vals in (params or {}).items():
        argv += [f"{k}={v}" for v in (vals if isinstance(vals, list) else [vals])]
    return argv


def _finish(run, record, proc, started):
    out = (proc.stdout or b"").decode("utf-8", "replace") if isinstance(proc.stdout, bytes) else (proc.stdout or "")
    err = (proc.stderr or b"").decode("utf-8", "replace") if isinstance(proc.stderr, bytes) else (proc.stderr or "")
    res = {"ok": proc.returncode == 0, "returncode": proc.returncode,
           "stdout": out[:TEXT_LIMIT], "stdout_truncated": len(out) > TEXT_LIMIT,
           "stderr": err[-4000:], "elapsed_s": round(time.monotonic() - started, 2)}
    log(run, {**record, "returncode": proc.returncode, "elapsed_s": res["elapsed_s"]})
    return res


# ------------------------------------------------------------------ B: typed calls
def run_pipeline(run, steps, input=None, output=None):
    """B: run SU programs in sequence, stdin from `input`, stdout to `output` (or returned as text)."""
    if not isinstance(steps, list) or not steps:
        raise PolicyError("steps must be a non-empty list of {program, params}")
    progs, vsigs, hw = [], [], []
    src = str(resolve(run, input, "read")) if input else None
    for s in steps:
        prog, params = s.get("program"), s.get("params") or {}
        if prog in TEXT_TOOLS:
            raise PolicyError("run_program/run_pipeline run SU programs; read text with read_text")
        hw += check_program(prog, params, run)
        progs.append(prog)
        if prog == "suvelan":
            vsigs.append(_velocity_signature(prog, params, src))
    dst = resolve(run, output, "write") if output else None
    st_fail, st_ok = charge(run, load_state(run), writes_file=bool(dst), programs=progs,
                            velocity_signatures=vsigs, header_writes=hw)
    import tempfile
    started = time.monotonic()
    procs, prev = [], None
    fin = open(src, "rb") if src else subprocess.DEVNULL
    fout = open(dst, "wb") if dst else subprocess.PIPE
    ferr = tempfile.TemporaryFile()
    try:
        for i, s in enumerate(steps):
            last = i == len(steps) - 1
            p = subprocess.Popen(_argv(s["program"], s.get("params")), stdin=prev.stdout if prev else fin,
                                 stdout=fout if last else subprocess.PIPE, stderr=ferr,
                                 cwd=run_dir(run), env=_env_for_run())
            if prev:
                prev.stdout.close()
            procs.append(p)
            prev = p
        out, _ = procs[-1].communicate(timeout=TIMEOUT_S)
        for p in procs[:-1]:
            p.wait(timeout=60)
        rc = max(abs(p.returncode or 0) for p in procs)
        ferr.seek(0)
        errs = ferr.read()
    finally:
        ferr.close()
        if src:
            fin.close()
        if dst:
            fout.close()
    save_state(run, st_ok if _succeeded(rc, dst) else st_fail)

    class P:
        pass
    pr = P()
    pr.returncode, pr.stdout, pr.stderr = rc, out or b"", errs
    return _finish(run, {"interface": "B", "steps": steps, "input": input, "output": output,
                         "header_writes": hw}, pr, started)


def run_program(run, program, params=None, input=None, output=None):
    """B: one SU program."""
    return run_pipeline(run, [{"program": program, "params": params or {}}], input, output)


# ------------------------------------------------------------------ A: shell composition
SHELL_OPS = {"|", ";", "&&", "<", ">", ">>", "\n"}


def parse_shell(run, script):
    """Validate a script: simple commands of allowlisted programs joined by | ; && and < > >> redirections."""
    if any(c in script for c in "`\\") or "$(" in script:
        raise PolicyError("substitutions and escapes are not allowed")
    lex = shlex.shlex(script.replace("\n", " ; "), posix=True, punctuation_chars="|;&<>()")
    lex.whitespace_split = True
    toks = list(lex)
    commands, cur = [], []
    for t in toks:
        if t in ("(", ")", "&", "||", "<<", ";;", "&>", ">&"):
            raise PolicyError(f"'{t}' is not allowed")
        if t in SHELL_OPS or t in ("|", ";", "&&"):
            commands.append((cur, t))
            cur = []
        else:
            cur.append(t)
    commands.append((cur, None))
    progs, vsigs, hw, writes = [], [], [], False
    segment_input = None
    i = 0
    flat = []
    for words, op in commands:
        flat.append(("words", words))
        if op:
            flat.append(("op", op))
    k = 0
    while k < len(flat):
        kind, val = flat[k]
        if kind == "op" and val in ("<", ">", ">>"):
            if k + 1 >= len(flat) or flat[k + 1][0] != "words" or not flat[k + 1][1]:
                raise PolicyError(f"'{val}' needs a file name")
            target, rest = flat[k + 1][1][0], flat[k + 1][1][1:]
            if val == "<":
                segment_input = str(resolve(run, target, "read"))
            else:
                resolve(run, target, "write")
                writes = writes or target != "/dev/null"
            flat[k + 1] = ("words", rest)
            if rest:
                raise PolicyError("put redirections at the end of a command")
            k += 2
            continue
        if kind == "op" and val in (";", "&&"):
            segment_input = None
        if kind == "words" and val:
            prog, args = val[0], val[1:]
            if "/" in prog:
                raise PolicyError(f"{prog}: run programs by name, not by path")
            if "$" in prog or "=" in prog:
                raise PolicyError("variables are not allowed")
            params = {}
            if prog in SU_PROGRAMS:
                for a in args:
                    if "=" not in a:
                        raise PolicyError(f"{prog}: arguments are key=value ({a!r})")
                    kk, vv = a.split("=", 1)
                    params[kk] = vv
                hw += check_program(prog, params, run)
                if prog == "suvelan":
                    vsigs.append(_velocity_signature(prog, params, segment_input))
            elif prog in TEXT_TOOLS:
                if prog == "awk" and any(AWK_FORBIDDEN.search(a) for a in args):
                    raise PolicyError("awk programs may not call system(), getline, ENVIRON or redirect")
                for a in args:
                    if not a.startswith("-") and ("/" in a or Path(a).suffix in (".su", ".sgy", ".txt", ".dat")):
                        if prog != "awk" or not a.startswith(("{", "BEGIN", "NR", "$")):
                            resolve(run, a, "read")
                if "$" in " ".join(args) and prog != "awk":
                    raise PolicyError("variables are not allowed")
            else:
                raise PolicyError(f"{prog} is not available; available: "
                                  f"{', '.join(sorted(SU_PROGRAMS | TEXT_TOOLS))}")
            progs.append(prog)
        k += 1
    return progs, vsigs, hw, writes


def shell(run, script):
    """A: run a validated script in the run directory, with only the allowlisted programs on PATH."""
    if not isinstance(script, str) or not script.strip():
        raise PolicyError("script is empty")
    progs, vsigs, hw, writes = parse_shell(run, script)
    st_fail, st_ok = charge(run, load_state(run), writes_file=writes, programs=progs,
                            velocity_signatures=vsigs, header_writes=hw)
    started = time.monotonic()
    env = _env_for_run()
    env["PATH"] = str(allowed_path_dir())
    proc = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", script], cwd=run_dir(run), env=env,
                          capture_output=True, timeout=TIMEOUT_S)
    save_state(run, st_ok if proc.returncode == 0 else st_fail)
    return _finish(run, {"interface": "A", "script": script, "header_writes": hw}, proc, started)


def allowed_path_dir():
    """A directory of symlinks to exactly the allowed executables (the only PATH entry in A)."""
    d = paths()["work"] / ".allowed_bin"
    d.mkdir(parents=True, exist_ok=True)
    for prog in SU_PROGRAMS:
        link = d / prog
        if not link.exists():
            link.symlink_to(paths()["bin"] / prog)
    for prog in TEXT_TOOLS - {"echo"}:
        link = d / prog
        if not link.exists():
            for base in ("/usr/bin", "/bin"):
                if Path(base, prog).exists():
                    link.symlink_to(Path(base, prog))
                    break
    return d


# ------------------------------------------------------------------ both
def program_doc(program):
    if program not in SU_PROGRAMS:
        raise PolicyError(f"{program} is not available")
    p = subprocess.run([str(paths()["bin"] / "sudoc"), program], capture_output=True, text=True,
                       env=_env_for_run(), timeout=60)
    return {"ok": p.returncode == 0, "doc": (p.stdout or p.stderr)[:TEXT_LIMIT]}


def list_files(run):
    d = run_dir(run)
    inp = paths()["input"]
    return {"run_directory": [{"name": f.name, "bytes": f.stat().st_size} for f in sorted(d.iterdir())
                              if f.is_file() and not f.name.startswith(".")],
            "input_directory": str(inp),
            "input_files": [{"name": f.name, "bytes": f.stat().st_size} for f in [own_case(run)]
                            if f is not None and f.is_file()]}


def read_text(run, name, max_chars=TEXT_LIMIT):
    p = resolve(run, name, "read")
    if p.suffix in (".su", ".sgy", ".segy"):
        raise PolicyError("read_text reads text files; inspect seismic files with SU programs")
    txt = p.read_text(errors="replace")
    n = max(1, min(int(max_chars), TEXT_LIMIT))
    return {"ok": True, "text": txt[:n], "truncated": len(txt) > n}


def budget(run):
    st = load_state(run)
    return {k: {"used": st[k], "limit": BUDGET[k]} for k in BUDGET}


def tick(run):
    """Count a non-processing call (listing, reading, documentation) against the tool-call budget."""
    st, _ = charge(run, load_state(run), writes_file=False, programs=[], velocity_signatures=[], header_writes=[])
    save_state(run, st)


def submit(run, name):
    """Copy the file the agent names as its final artifact to B01_SUBMIT/<run>/ (readable by the evaluator)."""
    import shutil
    src = resolve(run, name, "read")
    if run_dir(run) not in src.parents:
        raise PolicyError("submit a file from your run directory")
    dest_root = _env("B01_SUBMIT") / run
    dest_root.mkdir(parents=True, exist_ok=True)
    dst = dest_root / src.name
    shutil.copyfile(src, dst)
    log(run, {"submit": name, "bytes": dst.stat().st_size})
    return {"ok": True, "submitted": src.name, "bytes": dst.stat().st_size}
