"""v0.27 evaluation (results/v0270/CRITERIA.md): M6 smoothed migration velocity, W4."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402


def quality(path, ref):
    """evaluate_v020.quality without dead traces: a low-fold end whose windows are fully muted carries no
    correlation (the same live-trace filter evaluate_migration uses)."""
    s = E.read_su(path)
    d = s["data"]
    live = (np.linalg.norm(d[:, 340:710], axis=1) > 0) & (np.linalg.norm(d[:, 690:1210], axis=1) > 0)
    mm = E.match(d[live], np.asarray(s["cdp"])[live], ref, 0)
    return {"best_lag": mm["best_lag"], "zero_lag": mm["zero_lag"], "dead_traces": int((~live).sum())}

sys.path.insert(0, str(E.ROOT / "dev/marm2_oracle"))
from common import truth_vrms  # noqa: E402

RES = E.RES
IDS = ["v027-v2", "v027-h12-sb", "v027-h12-wn", "v027-h12-bn", "v027-h12-dl", "v027-h12-c064", "v027-h12-c032"]
REGRESSION = ["v027-v2n", "v027-c027"]
MIG_REF = RES / "migration_reference/er_mig_true_blend.npz"


def pick_error(model_path, vp):
    m = json.loads(Path(model_path).read_text())
    rep = {r["cdp"]: r for r in m["reports"]}
    errs, deep, per = [], [], {}
    for loc in m["locations"]:
        r = rep.get(loc["cdp"], {})
        if not r.get("valid"):
            continue
        tsup = float(r.get("supported_to_s") or 0)
        t = np.arange(0.7, tsup + 1e-9, 0.02)
        if t.size == 0:
            continue
        tf = np.array([p["t0_s"] for p in loc["function"]])
        vf = np.array([p["v_m_s"] for p in loc["function"]])
        vpk = np.interp(t, tf, vf)
        vtr = truth_vrms(loc["cdp"] * 10.0, t, vp)
        e = (vpk - vtr) / vtr
        errs.append(e)
        deep.append(e[t > 1.6])
        per[int(loc["cdp"])] = {"median": round(float(np.median(e)) * 100, 2), "to_s": tsup}
    a = np.concatenate(errs) if errs else np.array([np.nan])
    d = np.concatenate(deep) if deep else np.array([np.nan])
    return {"median_signed_pct": round(float(np.median(a)) * 100, 2),
            "median_abs_pct": round(float(np.median(np.abs(a))) * 100, 2),
            "deep_median_signed_pct": round(float(np.median(d)) * 100, 2) if d.size else None,
            "locations": per}


def reliability(ds):
    m = json.loads((E.ROOT / "state/datasets" / f"{ds}.json").read_text())
    sc = m["capabilities"].get("stack.completed", {})
    rel = (sc.get("evidence") or {}).get("reliability") or {}
    mc = (m["capabilities"].get("migration.completed", {}).get("evidence") or {}).get("reliability") or {}
    return sc.get("status"), rel.get("level"), rel.get("reasons"), mc.get("level")


def judge(good, level, released):
    if not released:
        return "D/E"
    if good:
        return {"OK": "A", "CAUTION": "A~"}.get(level, "A*")
    return {"OK": "C", "CAUTION": "Bc"}.get(level, "Bn")


def main():
    sys.argv_ = sys.argv
    import importlib.util
    spec = importlib.util.spec_from_file_location("em", HERE / "evaluate_migration.py")
    sys.argv = [sys.argv[0], str(E.ROOT), str(MIG_REF)]
    em = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(em)
    sys.argv = sys.argv_
    mref = {"agc": em.agc(np.load(MIG_REF)["section"].astype(float))}
    ref = E.load_reference()
    vp = np.load(E.VP_NPY)
    out = {"good_threshold": round(E.GOOD, 3), "rows": {}}
    for ds in IDS + REGRESSION:
        row = {}
        for tag in ("stack0", "stack1"):
            p = RES / "v0270/stacks" / f"{ds}_{tag}.su"
            if p.exists():
                row[tag] = quality(p, ref)["best_lag"]
        row["final"] = quality(RES / f"{ds}_stack.su", ref)["best_lag"]
        for tag in ("vel0", "vel1"):
            p = RES / f"{ds}_{tag}.json"
            if p.exists():
                row[tag] = pick_error(p, vp)
        qu = em.q(RES / f"{ds}_stack.su", mref)
        row["Q_unmig"] = qu["best_lag"]
        for meth in ("phase_shift", "phase_shift_smooth"):
            mig = RES / f"{ds}_mig_{meth}.su"
            if mig.exists():
                qm = em.q(mig, mref)
                row[meth] = {"Q": qm["best_lag"], "g": round(qm["best_lag"] - qu["best_lag"], 3),
                             "windows": {k: v.get("best_lag_pm20ms") for k, v in qm["windows"].items()
                                         if isinstance(v, dict)}}
        m = json.loads((E.ROOT / "state/datasets" / f"{ds}.json").read_text())
        vv = (m["capabilities"].get("velocity.validated", {}).get("evidence") or {})
        row["valid_locations"] = len(vv.get("locations_valid") or [])
        st, lvl, reasons, mlvl = reliability(ds)
        row["reliability"] = [lvl, reasons]
        row["class"] = judge(row["final"] >= E.GOOD, lvl, st == "PASS")
        out["rows"][ds] = row
        print(ds, json.dumps({k: (v if not isinstance(v, dict) or "Q" not in v else [v["Q"], v["windows"].get("1.4-2.4s")])
                              for k, v in row.items() if k not in ("vel0", "vel1")}),
              {t: (row[t]["median_signed_pct"], row[t]["deep_median_signed_pct"]) for t in ("vel0", "vel1") if t in row},
              flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
