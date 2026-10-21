"""Baseline study 01: the final 12-case set (K2 replaced by its pre-written alternate) and the balanced run
order."""
import hashlib, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
H = ROOT / "results/baseline01/hidden"
SEED_ORDER = 157
gen = json.loads((H / "generation.json").read_text()); gen_alt = json.loads((H / "generation_alternates.json").read_text())
lab = json.loads((H / "labels.json").read_text()); lab_alt = json.loads((H / "labels_alternates.json").read_text())
cases = {}
for c in ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "K1", "K2", "K3", "K4"]:
    src, lsrc, key = (gen_alt, lab_alt, "K2alt") if c == "K2" else (gen, lab, c)
    g, l = src["cases"][key], lsrc["cases"][key]
    cases[c] = {"generated_as": key, "case_id": Path(g["file"]).stem, "file": g["file"], "sha256": g["sha256"],
                "mechanism": g["mechanism"], "oracle_best_lag": l["oracle_best_lag"], "usable": l["usable"]}
replaced = {"K2": {"original": gen["cases"]["K2"]["file"], "oracle_best_lag": lab["cases"]["K2"]["oracle_best_lag"],
                   "reason": "not usable under the oracle; replaced by the pre-written alternate (90 shots)"}}
out = {"criteria": "results/baseline01/CRITERIA.md", "cases": cases, "replaced_controls": replaced,
       "controls_all_usable": all(cases[k]["usable"] for k in ("K1", "K2", "K3", "K4"))}
p = H / "challenge_set.json"
assert not p.exists(); p.write_text(json.dumps(out, indent=1))
# balanced order: positions 1-4 (repeat 1) and 5-8 (repeat 2) each from a 4x4 Latin square row; 12 cases = each
# row three times, so every condition sits in every position 3 times
conds = ["A", "B", "C0", "C"]
L1 = [[0, 1, 2, 3], [1, 3, 0, 2], [2, 0, 3, 1], [3, 2, 1, 0]]
L2 = [[2, 3, 0, 1], [3, 2, 1, 0], [0, 1, 2, 3], [1, 0, 3, 2]]
rng = np.random.default_rng(SEED_ORDER)
rows1 = rng.permutation(np.repeat(np.arange(4), 3)); rows2 = rng.permutation(np.repeat(np.arange(4), 3))
case_ids = [cases[c]["case_id"] for c in sorted(cases)]
case_order = list(rng.permutation(case_ids))
order = {}
for i, cid in enumerate(case_order):
    seq = [(conds[j], 1) for j in L1[rows1[i]]] + [(conds[j], 2) for j in L2[rows2[i]]]
    order[cid] = [{"position": k + 1, "condition": c, "repeat": r} for k, (c, r) in enumerate(seq)]
pos = {c: [0] * 8 for c in conds}
for seq in order.values():
    for e in seq: pos[e["condition"]][e["position"] - 1] += 1
ro = {"seed": SEED_ORDER, "case_sequence": case_order, "order": order, "condition_by_position": pos}
q = ROOT / "results/baseline01/run_order.json"
assert not q.exists(); q.write_text(json.dumps(ro, indent=1))
print(json.dumps(pos)); print(out["controls_all_usable"])
print(hashlib.sha256(p.read_bytes()).hexdigest()[:16], hashlib.sha256(q.read_bytes()).hexdigest()[:16])
