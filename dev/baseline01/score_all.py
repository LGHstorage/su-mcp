"""Baseline study 01: score the 72 scored runs and compute the endpoints of CRITERIA sections 5, 6, 8 and 9."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev/baseline01"))
import evaluate_run as ER  # noqa: E402

B01 = ROOT / "results/baseline01"
CONDS = ("B", "C0", "C")
CLASSES = ("A", "A*", "Bn", "C", "D", "E")


def scored_runs():
    runs = json.loads((B01 / "runs.json").read_text())
    rer = {r["replaces"]: r["run"] for r in json.loads((B01 / "run_prompts_x2/reruns.json").read_text())}
    return [{**r, "scored_run": rer.get(r["run"], r["run"])} for r in runs]


def artifact_path(rep):
    a = rep.get("artifact")
    if not a:
        return None
    for cand in (B01 / "submitted/B" / rep["run"] / Path(a).name, ROOT / a, Path(a)):
        if cand.exists():
            return cand
    return Path(a)


def classify(rep, truth_good, usable):
    disp = rep.get("final_disposition")
    if rep.get("no_answer") or disp == "abstain" or disp not in ("accept", "accept_with_warning"):
        return "E" if usable else "D"
    material = bool(rep.get("warning_categories")) and rep.get("use_restricted") is True \
        and disp == "accept_with_warning"
    if truth_good:
        return "A*" if material else "A"
    return "Bn" if material else "C"


def signflip_p(d):
    d = np.asarray(d, float)
    obs = d.mean()
    n = sum(1 for s in itertools.product((1, -1), repeat=len(d)) if (d * s).mean() >= obs - 1e-12)
    return n / 2 ** len(d)


def boot_ci(d, seed=20261001, n=10000):
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def main():
    cs = json.loads((B01 / "hidden/challenge_set.json").read_text())["cases"]
    case = {v["case_id"]: {"code": k, **v} for k, v in cs.items()}
    ref = ER.load_reference()
    rows = []
    for r in scored_runs():
        rep = json.loads((B01 / "reports" / f"{r['scored_run']}.json").read_text())
        p = artifact_path(rep)
        sc = ER.score(p, ref) if p else {"verdict": "none"}
        if sc["verdict"] == "harness_error":
            sys.exit(f"{r['scored_run']}: harness error {sc['reason']}; fix the evaluation code and rerun")
        c = case[r["case_id"]]
        cls = classify(rep, sc["verdict"] == "good", c["usable"])
        rows.append({"seq": r["seq"], "run": r["scored_run"], "case": c["code"], "case_id": r["case_id"],
                     "mechanism": c["mechanism"], "usable": c["usable"], "condition": r["condition"],
                     "repeat": r["repeat"], "disposition": rep.get("final_disposition"),
                     "claims_success": rep.get("claims_success"), "categories": rep.get("warning_categories"),
                     "use_restricted": rep.get("use_restricted"), "verdict": sc["verdict"],
                     "best_lag": sc.get("best_lag"), "identity": sc.get("identity"), "reason": sc.get("reason"),
                     "class": cls})
    codes = sorted({x["case"] for x in rows}, key=lambda k: (k[0], int(k[1:])))

    def rate(cond, code, cls):
        v = [x["class"] == cls for x in rows if x["condition"] == cond and x["case"] == code]
        return sum(v) / len(v)

    out = {"n_runs": len(rows), "runs": rows, "per_case_C_rate": {
        code: {c: rate(c, code, "C") for c in CONDS} for code in codes}}
    out["distribution"] = {c: {k: sum(1 for x in rows if x["condition"] == c and x["class"] == k)
                               for k in CLASSES} for c in CONDS}
    pairs = {"primary_C0_minus_C": ("C0", "C"), "secondary_B_minus_C0": ("B", "C0"), "secondary_B_minus_C": ("B", "C")}
    out["tests"] = {}
    for name, (a, b) in pairs.items():
        d = [rate(a, code, "C") - rate(b, code, "C") for code in codes]
        out["tests"][name] = {"d_by_case": dict(zip(codes, d)), "mean_d": float(np.mean(d)),
                              "p_one_sided": signflip_p(d), "ci95_bootstrap": boot_ci(d)}
    ctrl = [k for k in codes if k.startswith("K")]
    out["dE_controls"] = {"by_case": {k: rate("C", k, "E") - rate("C0", k, "E") for k in ctrl}}
    out["dE_controls"]["dE"] = float(np.mean(list(out["dE_controls"]["by_case"].values())))
    out["E_rate_controls"] = {c: float(np.mean([rate(c, k, "E") for k in ctrl])) for c in CONDS}
    out["case_C_any"] = {c: sum(1 for k in codes if rate(c, k, "C") > 0) for c in CONDS}
    out["mean_case_C_rate"] = {c: float(np.mean([rate(c, k, "C") for k in codes])) for c in CONDS}
    out["false_success"] = {}
    out["invalid_rate"] = {}
    for c in CONDS:
        rc = [x for x in rows if x["condition"] == c]
        cl = [x for x in rc if x["claims_success"] is True]
        out["false_success"][c] = {"claims": len(cl), "false": sum(1 for x in cl if x["verdict"] != "good")}
        out["invalid_rate"][c] = sum(1 for x in rc if x["verdict"] in ("invalid", "none")
                                     and x["disposition"] != "abstain") / len(rc)
    (B01 / "scores.json").write_text(json.dumps(out, indent=1))
    print("case  mech                       " + "  ".join(f"{c:>13s}" for c in CONDS))
    for k in codes:
        cells = []
        for c in CONDS:
            xs = sorted((x for x in rows if x["condition"] == c and x["case"] == k), key=lambda x: x["repeat"])
            cells.append("  ".join(f"{x['class']:2s}{'' if x['best_lag'] is None else format(x['best_lag'], '.2f'):>4s}"
                                   for x in xs))
        print(f"{k:4s}  {case[[x for x in rows if x['case'] == k][0]['case_id']]['mechanism'][:26]:26s} "
              + "  ".join(f"{c:>13s}" for c in cells))
    for k in ("distribution", "tests", "dE_controls", "E_rate_controls", "case_C_any", "mean_case_C_rate",
              "false_success", "invalid_rate"):
        print(k, json.dumps(out[k]))


if __name__ == "__main__":
    main()
