"""v0.22 judgement matrix from eval_v021.json and the released stacks' manifests (evaluation only)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ev = json.loads((ROOT / "results/v0220/eval_v022.json").read_text())
GOOD = ev["good_threshold"]
# stack-1 reliability as reported by stack_cmp before residual statics (tool output of the run)
S1_WARN = {"v022-" + k for k in (
    "h4-st16", "l1-st20", "h5-st24", "h5-st16bn", "h3-wn100", "l1-nz100", "h5-wn150", "h6-st10",
    "h6-st18", "h6-st28", "h6-wn070", "h6-wn120", "h6-wn170", "h6-st14wn", "h7-st16bn", "h7-wn100",
    "h7-st14", "h7-st12wn")}


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
           "scope_cdp": ev_s.get("scope_cdp"),
           "e2": (ev_s.get("velocity_support") or {}).get("measured_fraction"),
           "locations_valid": len((m["capabilities"]["velocity.validated"]["evidence"] or {}).get("locations_valid") or [])}
    out["rows"][ds] = row
    print(f"{ds:16s} {row['section']} ref={row['reference']:.3f} s1={row['stack1']:.3f}({row['stack1_grade']}) "
          f"fin={row['final']:.3f}({row['grade']}) rs2={row['rs2_accepted']} va={row['velocity_analyses']} "
          f"E2={row['e2']} nv={row['locations_valid']} {row['final_reasons']}")
cnt = {}
for r in out["rows"].values():
    cnt.setdefault(r["section"], {}).setdefault(r["grade"], 0)
    cnt[r["section"]][r["grade"]] += 1
out["counts"] = cnt
print(cnt)
(ROOT / "results/v0220/matrix_v0.22.json").write_text(json.dumps(out, indent=1))
