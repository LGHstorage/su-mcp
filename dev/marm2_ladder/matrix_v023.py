"""v0.23 judgement matrix (tiers) and the retrospective application to v0.21/v0.22 (evaluation only)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sumcp import stack as S                     # noqa: E402  (pure function, no I/O)

GOOD = 0.9 * 0.622
S1_LEVEL = {"v023-h8-bn120": "WARN", "v023-h8-bn140": "WARN", "v023-h8-bn200": "WARN",
            "v023-h8-wn130": "WARN", "v023-h8-wn150": "WARN", "v023-h8-st20bn": "WARN",
            "v023-h8-st18wn": "WARN", "v023-h8-dl120bn": "OK"}


def grade(q, level):
    good = q >= GOOD
    return {("OK", True): "A", ("CAUTION", True): "A~", ("WARN", True): "A*",
            ("OK", False): "C", ("CAUTION", False): "Bc", ("WARN", False): "Bn"}[(level, good)]


def evidence(ds):
    m = json.loads((ROOT / "state/datasets" / f"{ds}.json").read_text())
    return m, m["capabilities"]["stack.completed"]["evidence"]


out = {"good_threshold": round(GOOD, 4), "rows": {}, "retrospective": {}}
ev = json.loads((ROOT / "results/v0230/eval_v023.json").read_text())
for ds, r in ev["rows"].items():
    m, e = evidence(ds)
    rel = e["reliability"]
    row = {"level": r["level"], "reference": r["reference_quality"], "stack1": r["stack1"]["best_lag"],
           "stack1_grade": grade(r["stack1"]["best_lag"], S1_LEVEL[ds]), "final": r["final"]["best_lag"],
           "reliability": rel["level"], "quality_reasons": rel.get("quality_reasons"),
           "provenance_reasons": rel.get("provenance_reasons"),
           "ceiling": e["signal_to_noise"].get("correlation_ceiling"),
           "e2": e["velocity_support"].get("measured_fraction"),
           "grade": grade(r["final"]["best_lag"], rel["level"])}
    out["rows"][ds] = row
    print(f"{ds:18s} ref={row['reference']:.3f} s1={row['stack1']:.3f}({row['stack1_grade']}) "
          f"fin={row['final']:.3f}({row['grade']}) ceil={row['ceiling']} E2={row['e2']} {rel['reasons']}")

# retrospective: the v0.23 rule on the recorded evidence of released v0.21 / v0.22 stacks
for ver in ("v0210", "v0220"):
    evv = json.loads((ROOT / f"results/{ver}" / f"eval_{ver[:4]}{ver[4]}.json".replace("v021", "v021")).read_text()) \
        if False else json.loads((ROOT / f"results/{ver}" / ("eval_v021.json" if ver == "v0210" else "eval_v022.json")).read_text())
    cnt = {}
    for ds, r in evv["rows"].items():
        _, e = evidence(ds)
        feas = e.get("feasibility")
        rel = S.reliability_warning(e["signal_to_noise"], e["velocity_support"], feas)
        g = grade(r["final"]["best_lag"], rel["level"])
        cnt[g] = cnt.get(g, 0) + 1
        out["retrospective"].setdefault(ver, {})[ds] = {"final": r["final"]["best_lag"], "tier": rel["level"], "grade": g}
    out["retrospective"][ver + "_counts"] = cnt
    print(ver, "retrospective", cnt)
cnt = {}
for r in out["rows"].values():
    cnt[r["grade"]] = cnt.get(r["grade"], 0) + 1
out["counts"] = cnt
print("v0.23 ladder 8", cnt)
(ROOT / "results/v0230/matrix_v0.23.json").write_text(json.dumps(out, indent=1))
