"""Baseline study 02: score the runs and compute the endpoints of results/baseline02/CRITERIA.md sections 3, 6,
7."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev/baseline01"))
import evaluate_run as ER  # noqa: E402
_spec = importlib.util.spec_from_file_location("b01_score_all", ROOT / "dev/baseline01/score_all.py")
S1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S1)

B02 = ROOT / "results/baseline02"
CONDS = ("C0", "C")
CLASSES = ("A", "A*", "Bn", "C", "D", "E")
CONCORDANT = ("A", "Bn", "D")
BOOT_SEED = 20261101


def main(stage=None):
    runs = json.loads((B02 / "runs.json").read_text())
    rr = B02 / "run_prompts_x2/reruns.json"
    rer = {r["replaces"]: r["run"] for r in json.loads(rr.read_text())} if rr.exists() else {}
    if stage:
        runs = [r for r in runs if r["stage"] == stage]
    cs = json.loads((B02 / "hidden/challenge_set.json").read_text())["cases"]
    case = {v["case_id"]: {"code": k, **v} for k, v in cs.items()}
    ref = ER.load_reference()
    rows = []
    for r in runs:
        run = rer.get(r["run"], r["run"])
        rep = json.loads((B02 / "reports" / f"{run}.json").read_text())
        a = rep.get("artifact")
        p = next((q for q in ((ROOT / a) if a else None, Path(a) if a else None) if q and q.exists()), None)
        sc = ER.score(p, ref) if p else {"verdict": "none" if not a else "invalid", "reason": "no artifact file"}
        if sc["verdict"] == "harness_error":
            sys.exit(f"{run}: harness error {sc['reason']}; fix the evaluation code and rerun")
        c = case[r["case_id"]]
        cls = S1.classify(rep, sc["verdict"] == "good", c["usable"])
        rows.append({"seq": r["seq"], "stage": r["stage"], "run": run, "case": c["code"], "case_id": r["case_id"],
                     "kind": c["kind"], "mechanism": c["mechanism"], "usable": c["usable"],
                     "condition": r["condition"], "repeat": r["repeat"], "disposition": rep.get("final_disposition"),
                     "claims_success": rep.get("claims_success"), "categories": rep.get("warning_categories"),
                     "use_restricted": rep.get("use_restricted"), "verdict": sc["verdict"],
                     "best_lag": sc.get("best_lag"), "reason": sc.get("reason"), "class": cls,
                     "concordant": cls in CONCORDANT})
    codes = sorted({x["case"] for x in rows})

    def rate(cond, code, pred):
        v = [pred(x) for x in rows if x["condition"] == cond and x["case"] == code]
        return sum(v) / len(v)

    conc = lambda x: x["concordant"]
    d = [rate("C", k, conc) - rate("C0", k, conc) for k in codes]
    dC = [rate("C", k, lambda x: x["class"] == "C") - rate("C0", k, lambda x: x["class"] == "C") for k in codes]
    out = {"stage": stage or "final", "n_runs": len(rows), "n_cases": len(codes), "runs": rows,
           "concordance_by_case": {k: {c: rate(c, k, conc) for c in CONDS} for k in codes},
           "d_by_case": dict(zip(codes, d)), "mean_d": float(np.mean(d)),
           "distribution": {c: {k: sum(1 for x in rows if x["condition"] == c and x["class"] == k)
                                for k in CLASSES} for c in CONDS},
           "C_rate_excess_cases_C_over_C0": float(np.sum(dC))}
    if stage:
        out["interim_rule"] = "stop for futility if mean d <= 0; no claim of support at the interim"
        out["interim_decision"] = "STOP (futility)" if out["mean_d"] <= 0 else "CONTINUE to stage 2"
    else:
        out["p_one_sided"] = S1.signflip_p(d)
        out["ci95_bootstrap"] = S1.boot_ci(d, seed=BOOT_SEED)
        out["C_concordant_both_runs_cases"] = sum(1 for k in codes if rate("C", k, conc) == 1.0)
        good = lambda c: [x for x in rows if x["condition"] == c and x["verdict"] == "good"]
        bad = lambda c: [x for x in rows if x["condition"] == c and x["verdict"] != "good"
                         and x["disposition"] != "abstain"]
        out["secondary"] = {c: {
            "restricted_good": [sum(1 for x in good(c) if x["class"] == "A*"), len(good(c))],
            "warned_bad": [sum(1 for x in bad(c) if x["class"] == "Bn"), len(bad(c))],
            "mean_best_lag": float(np.mean([x["best_lag"] for x in rows if x["condition"] == c
                                            and x["best_lag"] is not None])),
            "false_success": [sum(1 for x in rows if x["condition"] == c and x["claims_success"] is True
                                  and x["verdict"] != "good"),
                              sum(1 for x in rows if x["condition"] == c and x["claims_success"] is True)],
            "invalid_rate": sum(1 for x in rows if x["condition"] == c and x["verdict"] in ("invalid", "none")
                                and x["disposition"] != "abstain") / max(1, sum(1 for x in rows
                                                                                 if x["condition"] == c)),
        } for c in CONDS}
        inv = [out["secondary"][c]["invalid_rate"] for c in CONDS]
        out["not_supported_if"] = {"mean_d_below_one_case_or_p_ge_0.05": out["mean_d"] < 1 / len(codes) or out["p_one_sided"] >= 0.05,
                                   "C_rate_excess_over_one_case": out["C_rate_excess_cases_C_over_C0"] > 1.0,
                                   "invalid_rates_differ_over_20pp": abs(inv[0] - inv[1]) > 0.20}
        out["claim_supported"] = not any(out["not_supported_if"].values())
    name = "scores_stage1.json" if stage else "scores.json"
    (B02 / name).write_text(json.dumps(out, indent=1))
    for k in codes:
        cells = []
        for c in CONDS:
            xs = sorted((x for x in rows if x["condition"] == c and x["case"] == k), key=lambda x: x["repeat"])
            cells.append("  ".join(f"{x['class']:2s}{'' if x['best_lag'] is None else format(x['best_lag'], '.2f'):>5s}"
                                   for x in xs))
        print(f"{k:3s} {case[[x for x in rows if x['case'] == k][0]['case_id']]['mechanism'][:24]:24s} "
              + " | ".join(cells) + f" | d {out['d_by_case'][k]:+.1f}")
    print(json.dumps({k: v for k, v in out.items() if k not in ("runs", "concordance_by_case", "d_by_case")}))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[1]) if a[:1] == ["--stage"] else None)
