"""Baseline study 01: balanced run order for the three conditions B, C0, C (pre-freeze log item 8)."""
import hashlib, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
SEED_ORDER = 157
cs = json.loads((ROOT / "results/baseline01/hidden/challenge_set.json").read_text())["cases"]
conds = ["B", "C0", "C"]
L1 = [[0, 1, 2], [1, 2, 0], [2, 0, 1]]
L2 = [[0, 2, 1], [1, 0, 2], [2, 1, 0]]
rng = np.random.default_rng(SEED_ORDER)
rows1 = rng.permutation(np.repeat(np.arange(3), 4)); rows2 = rng.permutation(np.repeat(np.arange(3), 4))
case_ids = [cs[c]["case_id"] for c in sorted(cs)]
case_order = list(rng.permutation(case_ids))
order = {}
for i, cid in enumerate(case_order):
    seq = [(conds[j], 1) for j in L1[rows1[i]]] + [(conds[j], 2) for j in L2[rows2[i]]]
    order[cid] = [{"position": k + 1, "condition": c, "repeat": r} for k, (c, r) in enumerate(seq)]
pos = {c: [0] * 6 for c in conds}
for seq in order.values():
    for e in seq: pos[e["condition"]][e["position"] - 1] += 1
q = ROOT / "results/baseline01/run_order_3.json"
assert not q.exists()
q.write_text(json.dumps({"seed": SEED_ORDER, "conditions": conds, "case_sequence": case_order, "order": order,
                         "condition_by_position": pos}, indent=1))
print(json.dumps(pos), hashlib.sha256(q.read_bytes()).hexdigest()[:16])
