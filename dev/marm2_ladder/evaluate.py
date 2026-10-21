"""Evaluate a Marmousi2 v2 degradation ladder (evaluation only)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import (VP_NPY, cmp_sort, nmo_stack, read_segy, read_su,  # noqa: E402
                    truth_vrms)
from run_oracle import load_reference, reference_match  # noqa: E402

WORK = Path(os.environ.get("LADDER_WORK", Path.home() / "ladder_work"))
RES = ROOT / "results"
DT = 0.002
SMUTE = 1.5
V_T_RANGE = (0.6, 2.28)
BASELINE_BEST = 0.622          # clean v2 released stack, first ladder
GOOD = 0.9 * BASELINE_BEST     # results/v0160/CRITERIA.md
V2 = ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"
METRICS = os.environ.get("LADDER_METRICS", "metrics")  # sub-directory of the ladder's results


def ladder_config(name: str) -> dict:
    if name == "ladder1":
        lad = ROOT / "test_dataset/Marm2_ladder"
        lv = {"baseline": ("v015-v2", V2, 0)}
        for d in (24, 50, 76, 100, 124, 150):
            lv[f"delay_{d:03d}"] = (f"lad-delay{d:03d}", lad / f"delay_{d:03d}ms.sgy", d)
        for tag in ("0p5", "1p0", "2p0", "4p0"):
            lv[f"noise_{tag}x"] = (f"lad-noise{tag}", lad / f"noise_{tag}x.sgy", 0)
        for s in (10, 20, 40):
            lv[f"statics_{s}ms"] = (f"lad-statics{s}", lad / f"statics_{s}ms.sgy", 0)
        return {"out": RES / "marm2_ladder", "levels": lv}
    if name == "heldout":
        lad = ROOT / "test_dataset/Marm2_ladder_heldout"
        lv = {"baseline": ("v016-v2", V2, 0)}
        for d in (12, 30, 40, 60, 90, 110):
            lv[f"delay_{d:03d}"] = (f"ho-delay{d:03d}", lad / f"delay_{d:03d}ms.sgy", d)
        for tag in ("0p75", "1p50", "3p00"):
            lv[f"bandnoise_{tag}x"] = (f"ho-bnoise{tag}", lad / f"bandnoise_{tag}x.sgy", 0)
        for tag in ("1p0", "4p0"):
            lv[f"whitenoise_{tag}x"] = (f"ho-wnoise{tag}", lad / f"whitenoise_{tag}x.sgy", 0)
        for s in (5, 15, 30):
            lv[f"statics_{s:02d}ms"] = (f"ho-statics{s:02d}", lad / f"statics_{s:02d}ms.sgy", 0)
        return {"out": RES / "marm2_ladder_heldout", "levels": lv}
    if name == "heldout2":
        lad = ROOT / "test_dataset/Marm2_ladder_heldout2"
        lv = {"baseline": ("v017-v2", V2, 0)}
        for d in (20, 70):
            lv[f"delay_{d:03d}"] = (f"h2-delay{d:03d}", lad / f"delay_{d:03d}ms.sgy", d)
        for tag in ("1p00", "2p00", "2p50"):
            lv[f"bandnoise_{tag}x"] = (f"h2-bnoise{tag}", lad / f"bandnoise_{tag}x.sgy", 0)
        for tag in ("0p5", "2p0"):
            lv[f"whitenoise_{tag}x"] = (f"h2-wnoise{tag}", lad / f"whitenoise_{tag}x.sgy", 0)
        for s_ in (12, 18):
            lv[f"statics_{s_:02d}ms"] = (f"h2-statics{s_:02d}", lad / f"statics_{s_:02d}ms.sgy", 0)
        return {"out": RES / "marm2_ladder_heldout2", "levels": lv}
    if name == "heldout3":
        lad = ROOT / "test_dataset/Marm2_ladder_heldout3"
        lv = {"baseline": ("v018-v2", V2, 0),
              "delay_045": ("h3-delay045", lad / "delay_045ms.sgy", 45),
              "statics_08ms": ("h3-statics08", lad / "statics_08ms.sgy", 0),
              "whitenoise_1p0x": ("h3-wnoise1p0", lad / "whitenoise_1p0x.sgy", 0)}
        for tag in ("0p50", "1p25", "1p75", "2p25"):
            lv[f"bandnoise_{tag}x"] = (f"h3-bnoise{tag}", lad / f"bandnoise_{tag}x.sgy", 0)
        return {"out": RES / "marm2_ladder_heldout3", "levels": lv}
    raise SystemExit(f"unknown ladder {name}")


def functions(vel_json: Path, only_valid: bool):
    rec = json.loads(vel_json.read_text())
    reps = [r for r in rec["reports"] if r.get("valid") or not only_valid]
    return ([int(r["cdp"]) for r in reps],
            [[p["t0_s"] for p in r["function"]] for r in reps],
            [[p["v_m_s"] for p in r["function"]] for r in reps],
            [bool(r.get("valid")) for r in reps])


def velocity_error(cdps, tn, vn, delay_s, vp):
    """Signed error in percent."""
    out = {}
    for mode in ("event", "same_time"):
        errs = []
        for c, ts, vs in zip(cdps, tn, vn):
            for t, v in zip(ts, vs):
                tt = t - delay_s if mode == "event" else t
                if not V_T_RANGE[0] <= tt <= V_T_RANGE[1]:
                    continue
                ref = float(truth_vrms(c * 10.0, np.array([tt]), vp)[0])
                errs.append((v / ref - 1) * 100)
        out[mode] = {"points": len(errs),
                     "median_signed_percent": round(float(np.median(errs)), 1) if errs else None,
                     "median_abs_percent": round(float(np.median(np.abs(errs))), 1) if errs else None}
    return out


def match(section, cdp, ref, shift, lag_shift=None):
    m = reference_match(section, cdp, ref, 0)
    res = {"zero_lag": m["0.7-2.4s"]["zero_lag"], "best_lag": m["0.7-2.4s"]["best_lag_pm20ms"],
           "windows": {k: v for k, v in m.items() if k != "traces"}}
    if shift:
        mc = reference_match(section, cdp, ref, shift)
        res["delay_compensated"] = {"zero_lag": mc["0.7-2.4s"]["zero_lag"],
                                    "best_lag": mc["0.7-2.4s"]["best_lag_pm20ms"]}
    if lag_shift is not None:
        ml = reference_match(section, cdp, ref, lag_shift)
        res["lag_corrected"] = {"zero_lag": ml["0.7-2.4s"]["zero_lag"],
                                "best_lag": ml["0.7-2.4s"]["best_lag_pm20ms"],
                                "shift_samples": lag_shift}
    return res


def _samples(ms):
    return None if ms is None else int(round(ms / 1000 / DT))


def run(cfg, level, ref, vp, base_fn, gates) -> dict:
    ds, sgy, delay_ms = cfg["levels"][level]
    shift = int(round(delay_ms / 1000 / DT))
    g = gates.get(level, {})
    measured = _samples(g.get("intercept_ms"))
    disclosed = _samples(g.get("datum_lag_ms"))
    work = WORK / f"{cfg['out'].name}_{level}"
    d = read_segy(sgy)
    order = cmp_sort(d)
    out = {"level": level, "dataset": ds, "delay_ms": delay_ms, "stacks": {}}
    keep = {}
    gated = RES / f"{ds}_stack.su"
    if gated.exists():
        s = read_su(gated)
        out["stacks"]["gated"] = match(s["data"], s["cdp"], ref, shift, disclosed)
        keep["gated"] = s["data"]
    vel = RES / f"{ds}_velocity_model.json"
    if vel.exists():
        cdps, tn, vn, valid = functions(vel, only_valid=False)
        out["picks"] = {"locations": len(cdps), "valid": int(sum(valid))}
        out["velocity"] = velocity_error(cdps, tn, vn, delay_ms / 1000, vp)
        s = nmo_stack(work, "ungated", d, order, cdps, tn, vn, SMUTE)
        out["stacks"]["ungated_all_picks"] = match(s["data"], s["cdp"], ref, shift, measured)
        keep["ungated_all_picks"] = s["data"]
        if gated.exists():
            out["gated_vs_ungated_max_abs_diff"] = float(np.max(np.abs(keep["gated"] - s["data"])))
    cdps, tn, vn, _ = base_fn
    s = nmo_stack(work, "oracle", d, order, cdps, tn, vn, SMUTE)
    out["stacks"]["baseline_picks_supplementary"] = match(s["data"], s["cdp"], ref, shift, measured)
    keep["baseline_picks_supplementary"] = s["data"]
    keep["cdp"] = s["cdp"]
    (work / "cmp_sorted.su").unlink(missing_ok=True)
    np.savez_compressed(work / "stacks.npz", **{k: v.astype(np.float32) for k, v in keep.items()})
    (cfg["out"] / METRICS).mkdir(parents=True, exist_ok=True)
    (cfg["out"] / METRICS / f"{level}.json").write_text(json.dumps(out, indent=1))
    return out


def summarize(cfg) -> None:
    gates = json.loads((cfg["out"] / os.environ.get("LADDER_GATES", "gate_outcomes.json")).read_text())["levels"]
    rows = {}
    for level in cfg["levels"]:
        p = cfg["out"] / METRICS / f"{level}.json"
        m = json.loads(p.read_text()) if p.exists() else {}
        g = gates.get(level, {})
        st = m.get("stacks", {})
        rows[level] = {
            "gate": {k: g.get(k) for k in ("time_zero", "intercept_ms", "feasibility", "velocity",
                                            "stack", "first_refusal")},
            "gated_best": st.get("gated", {}).get("best_lag"),
            "gated_zero": st.get("gated", {}).get("zero_lag"),
            "ungated_best": st.get("ungated_all_picks", {}).get("best_lag"),
            "ungated_zero": st.get("ungated_all_picks", {}).get("zero_lag"),
            "ungated_delay_comp_best": st.get("ungated_all_picks", {}).get("delay_compensated", {}).get("best_lag"),
            "baseline_picks_best": st.get("baseline_picks_supplementary", {}).get("best_lag"),
            "baseline_picks_zero": st.get("baseline_picks_supplementary", {}).get("zero_lag"),
            "velocity_event_signed": (m.get("velocity") or {}).get("event", {}).get("median_signed_percent"),
            "velocity_same_time_signed": (m.get("velocity") or {}).get("same_time", {}).get("median_signed_percent"),
            "picks_valid": (m.get("picks") or {}).get("valid"),
            "gated_vs_ungated_max_abs_diff": m.get("gated_vs_ungated_max_abs_diff"),
        }
    (cfg["out"] / os.environ.get("LADDER_SUMMARY", "ladder_summary.json")).write_text(json.dumps(rows, indent=1))
    for k, r in rows.items():
        print(k, json.dumps({x: y for x, y in r.items() if x != "gate"}), r["gate"]["first_refusal"] or "-")


def cell(metrics: dict, gate: dict) -> dict:
    """Judgement-matrix cell of results/v0160/CRITERIA.md for one level."""
    st = metrics.get("stacks", {})
    ref = st.get("baseline_picks_supplementary", {})
    ref_q = (ref.get("lag_corrected") or {}).get("best_lag", ref.get("best_lag"))
    usable = ref_q is not None and ref_q >= GOOD
    false_claim = gate.get("feasibility") == "FAIL"
    noise_warned = (gate.get("snr_level") == "NOISE_LIMITED"   # v0.17 N1
                    or gate.get("support_level") == "PARTIAL")  # v0.18 E1
    if gate.get("stack") == "done":
        q = st["gated"]["best_lag"]
        if q >= GOOD:
            c = "A"
        else:
            corr = (st["gated"].get("lag_corrected") or {}).get("best_lag")
            if gate.get("datum_level") == "DISPLACED" and corr is not None and corr >= GOOD:
                c = "B"
            elif noise_warned:
                c = "Bn"
            else:
                c = "C"
        return {"cell": c, "released_quality": q, "reference_quality": ref_q,
                "disclosed_corrected": (st["gated"].get("lag_corrected") or {}).get("best_lag"),
                "snr_level": gate.get("snr_level"),
                "false_alarm": bool(c == "A" and noise_warned),
                "false_claim": false_claim}
    return {"cell": "E" if usable else "D", "released_quality": None,
            "reference_quality": ref_q, "false_claim": false_claim,
            "refusal_honest": not false_claim}


def matrix(cfg, gates_path: Path, tag: str) -> None:
    gates = json.loads(gates_path.read_text())["levels"]
    rows, counts = {}, {c: 0 for c in ("A", "B", "Bn", "C", "D", "E")}
    claims = 0
    for level in cfg["levels"]:
        if level == "baseline" or level not in gates:
            continue
        m = json.loads((cfg["out"] / METRICS / f"{level}.json").read_text())
        r = cell(m, gates[level])
        rows[level] = r
        counts[r["cell"]] += 1
        claims += int(r["false_claim"])
    out = {"version": tag, "good_threshold": round(GOOD, 3), "counts": counts,
           "false_claims": claims, "levels": rows}
    (cfg["out"] / f"matrix_{tag}.json").write_text(json.dumps(out, indent=1))
    print(tag, counts, "false claims", claims)
    for k, r in rows.items():
        print(" ", k, r)


def main() -> None:
    cfg = ladder_config(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "summarize":
        summarize(cfg)
        return
    if cmd == "matrix":
        matrix(cfg, Path(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "v0.16")
        return
    gates_file = cfg["out"] / os.environ.get("LADDER_GATES", "gate_outcomes.json")
    gates = json.loads(gates_file.read_text())["levels"] if gates_file.exists() else {}
    ref = load_reference()
    vp = np.load(VP_NPY)
    base_fn = functions(RES / "v015-v2_velocity_model.json", only_valid=True)
    for level in sys.argv[3:]:
        r = run(cfg, level, ref, vp, base_fn, gates)
        print(level, json.dumps({k: v for k, v in r.items() if k != "stacks"}),
              {k: (v["zero_lag"], v["best_lag"], (v.get("lag_corrected") or {}).get("best_lag"))
               for k, v in r["stacks"].items()})


if __name__ == "__main__":
    main()
