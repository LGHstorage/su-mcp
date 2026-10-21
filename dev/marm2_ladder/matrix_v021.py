"""v0.21 judgement matrix from eval_v021.json and the released stacks' manifests (evaluation only)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ev = json.loads((ROOT / "results/v0210/eval_v021.json").read_text())
GOOD = ev["good_threshold"]
# stack-1 reliability as reported by stack_cmp before residual statics (tool output of the run)
S1_WARN = {"v021-h3-wn100", "v021-h4-st16", "v021-h5-st16bn", "v021-h5-wn150", "v021-h6-st10",
           "v021-h6-st14wn", "v021-h6-st18", "v021-h6-st28", "v021-h6-wn070", "v021-h6-wn120",
           "v021-h6-wn170", "v021-l1-nz100", "v021-l1-st20", "v021-h5-st24"}


def grade(q, warn):
    good = q >= GOOD
    if good:
        return "A*" if warn else "A"      # A* = good with a false alarm
    return "Bn" if warn else "C"


out = {"good_threshold": GOOD, "rows": {}}
for ds, r in ev["rows"].items():
    m = json.loads((ROOT / "state/datasets" / f"{ds}.json").read_text())
    ev_s = m["capabilities"]["stack.completed"]["evidence"]
    rel = ev_s["reliability"]
    conds = [(c.get("operations", [{}])[0].get("op"), c.get("accepted")) for c in m.get("conditioning") or []]
    rs = [a for op, a in conds if op == "residual_statics"]
    row = {"section": r["section"], "level": r["level"], "reference": r["reference_quality"],
           "usable": r["usable"], "stack1": r["stack1"]["best_lag"],
           "stack1_grade": grade(r["stack1"]["best_lag"], ds in S1_WARN),
           "final": r["final"]["best_lag"], "final_reliability": rel["level"],
           "final_reasons": rel["reasons"], "grade": grade(r["final"]["best_lag"], rel["level"] == "WARN"),
           "rs2_accepted": rs[0] if rs else None,
           "datum_shift": any(op == "datum_shift" and a for op, a in conds),
           "velocity_analyses": m.get("budgets", {}).get("velocity_analyses"),
           "scope_cdp": ev_s.get("scope_cdp")}
    out["rows"][ds] = row
    print(f"{ds:16s} {row['section']} ref={row['reference']:.3f} s1={row['stack1']:.3f}({row['stack1_grade']}) "
          f"fin={row['final']:.3f}({row['grade']}) rs2={row['rs2_accepted']} va={row['velocity_analyses']} "
          f"scope={row['scope_cdp']} {row['final_reasons']}")
cnt = {}
for r in out["rows"].values():
    cnt.setdefault(r["section"], {}).setdefault(r["grade"], 0)
    cnt[r["section"]][r["grade"]] += 1
out["counts"] = cnt
print(cnt)
(ROOT / "results/v0210/matrix_v0.21.json").write_text(json.dumps(out, indent=1))
