"""Baseline study 01, CRITERIA section 9, F3 (and the same table for study 02 stage 1, descriptive)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = [("N2", "signal_to_noise"), ("N1", "signal_to_noise"), ("E2", "velocity_support"), ("W3", "velocity_support"),
       ("W4", "velocity_support"), ("M8", "velocity_support"), ("M5", "aperture_line_length"),
       ("Q0", "sample_integrity"), ("N0", "sample_integrity")]


def one(study, run):
    rep = json.loads((ROOT / f"results/{study}/reports/{run}.json").read_text())
    mf = ROOT / f"state/datasets/{run}.json"
    if not mf.exists():
        return {"run": run, "error": "no manifest"}
    caps = json.loads(mf.read_text())["capabilities"]
    st = caps.get("stack.completed", {})
    ev = st.get("evidence", {})
    rel = ev.get("reliability", {})
    reasons = list(rel.get("reasons", []))
    cats = {c for code, c in MAP for r in reasons if re.match(rf"\s*{code}\b", r)}
    td = ev.get("time_datum", {})
    if td.get("level") == "DISPLACED":
        cats.add("time_datum")
        reasons.append("time datum DISPLACED")
    unmapped = [r for r in reasons if not any(re.match(rf"\s*{code}\b", r) for code, _ in MAP)
                and r != "time datum DISPLACED"]
    warned = rel.get("level") == "WARN" or td.get("level") == "DISPLACED"
    art = rep.get("artifact")
    released_by_system = st.get("status") == "PASS" and art and Path(art).name == Path(ev.get("output", "")).name
    disp = rep.get("final_disposition")
    acats = set(rep.get("warning_categories") or [])
    override = disp in ("accept", "accept_with_warning") and not released_by_system
    matched = bool(acats & cats) or (bool(acats) and not cats and bool(unmapped))
    ignore = bool(warned and not override and (disp == "accept" or (
        disp == "accept_with_warning" and not (rep.get("use_restricted") is True and matched))))
    return {"run": run, "system_stack_status": st.get("status"), "system_level": rel.get("level"),
            "system_reasons": reasons, "system_categories": sorted(cats), "unmapped_reasons": unmapped,
            "system_warned_or_refused": bool(warned or override), "agent_disposition": disp,
            "agent_categories": sorted(acats), "agent_use_restricted": rep.get("use_restricted"),
            "override": bool(override), "ignore": ignore}


def main(study):
    runs = json.loads((ROOT / f"results/{study}/runs.json").read_text())
    if study == "baseline02":
        runs = [r for r in runs if r["stage"] == 1]
    rows = [one(study, r["run"]) for r in runs if r["condition"] == "C"]
    den = [r for r in rows if r.get("system_warned_or_refused")]
    num = [r for r in den if r["override"] or r["ignore"]]
    tab = {}
    for r in rows:
        k = (r.get("system_level") or "none", r.get("agent_disposition"), bool(r.get("agent_use_restricted")))
        tab["|".join(map(str, k))] = tab.get("|".join(map(str, k)), 0) + 1
    out = {"study": study, "C_runs": len(rows), "system_warned_or_refused": len(den),
           "override_or_ignore": len(num), "rate": (len(num) / len(den)) if den else None,
           "F3_holds": (len(num) / len(den) >= 0.25) if den else False,
           "crosstab_system_level|agent_disposition|use_restricted": tab, "runs": rows}
    (ROOT / f"results/{study}/f3.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "runs"}, indent=1))
    for r in rows:
        if r.get("override") or r.get("ignore") or r.get("error") or r.get("unmapped_reasons"):
            print(r)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "baseline01")
