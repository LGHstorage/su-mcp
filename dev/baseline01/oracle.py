"""Baseline study 01: usability labels of the challenge set (results/baseline01/CRITERIA.md, section 4)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
sys.path.insert(0, str(ROOT / "dev/marm2_ladder"))
from common import cmp_sort, nmo_stack, read_segy  # noqa: E402
from run_oracle import load_reference, reference_match, truth_functions  # noqa: E402
import evaluate as E  # noqa: E402

HIDDEN = ROOT / "results/baseline01/hidden"
WORK = Path.home() / "baseline01_oracle_work"
DT = 0.002
SMUTE = 1.5
CONTROLS = ("K1", "K2", "K3", "K4")


def shift(data, seconds):
    ntr, ns = data.shape
    n = 2 * ns
    f = np.fft.rfftfreq(n, DT)
    spec = np.fft.rfft(data, n=n, axis=1)
    spec *= np.exp(-2j * np.pi * f[None, :] * np.asarray(seconds)[:, None])
    return np.fft.irfft(spec, n=n, axis=1)[:, :ns]


def correct(d, info):
    data = d["data"].astype(np.float64)
    applied = []
    if "samples" in info and info.get("delay_ms"):
        k = int(info["samples"])
        out = np.zeros_like(data)
        out[:, :data.shape[1] - k] = data[:, k:]
        data = out
        applied.append(f"bulk shift -{info['delay_ms']} ms")
    if "per_trace_statics_s" in info:
        data = shift(data, -np.asarray(info["per_trace_statics_s"]))
        applied.append("known statics reversed")
    if "trace_index" in info:
        data[int(info["trace_index"])] = 0.0
        applied.append(f"trace {info['trace_index']} zeroed")
    d = dict(d)
    d["data"] = data.astype(np.float32)
    return d, applied or ["none"]


def main(gen_name="generation.json"):
    gen = json.loads((HIDDEN / gen_name).read_text())
    out_path = HIDDEN / gen_name.replace("generation", "labels")
    if out_path.exists():
        raise SystemExit(f"{out_path} exists")
    ref = load_reference()
    WORK.mkdir(parents=True, exist_ok=True)
    labels = {"criteria": "results/baseline01/CRITERIA.md", "good_threshold": round(float(E.GOOD), 4),
              "oracle": "known correction + true-Vrms NMO (smute 1.5) + SU sunmo/sustack; best-lag 0.7-2.4 s",
              "oracle_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "cases": {}}
    for case, info in gen["cases"].items():
        path = ROOT / info["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise SystemExit(f"{case}: file hash differs from generation record")
        (WORK / "cmp_sorted.su").unlink(missing_ok=True)   # nmo_stack caches this file; never reuse another case's
        d = read_segy(path)
        d, applied = correct(d, info)
        order = cmp_sort(d)
        u = np.unique(d["cdp"])
        cdps = list(u[::20]) + ([int(u[-1])] if u[-1] not in u[::20] else [])
        c, tn, vn = truth_functions(cdps)
        s = nmo_stack(WORK, case, d, order, c, tn, vn, SMUTE)
        # the live-trace filter of evaluate_v027 / evaluate_migration: a trace muted to zero carries no
        # correlation
        dd = np.asarray(s["data"])
        live = (np.linalg.norm(dd[:, 340:710], axis=1) > 0) & (np.linalg.norm(dd[:, 690:1210], axis=1) > 0)
        m = reference_match(dd[live], np.asarray(s["cdp"])[live], ref, 0)
        best = m["0.7-2.4s"]["best_lag_pm20ms"]
        labels["cases"][case] = {"file": info["file"], "applied": applied,
                                 "oracle_best_lag": best, "oracle_zero_lag": m["0.7-2.4s"]["zero_lag"],
                                 "traces_scored": m["traces"], "dead_traces": int((~live).sum()), "usable": bool(best >= E.GOOD)}
        (WORK / "cmp_sorted.su").unlink(missing_ok=True)
        print(case, applied, best, labels["cases"][case]["usable"], flush=True)
    bad = [k for k in CONTROLS if k in labels["cases"] and not labels["cases"][k]["usable"]]
    labels["controls_not_usable"] = bad
    out_path.write_text(json.dumps(labels, indent=1))
    print("controls not usable:", bad)


if __name__ == "__main__":
    main(*sys.argv[1:])
