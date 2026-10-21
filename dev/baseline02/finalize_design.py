"""Baseline study 02: challenge_set.json, the run order, the stage split and the 48 task texts (CRITERIA 4-5)."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
B02 = ROOT / "results/baseline02"
HID = B02 / "hidden"
P01 = ROOT / "dev/baseline01/prompts"
WSL_ROOT = "/path/to/su-mcp"
SEED = 181
CASES = [f"P{i}" for i in range(1, 10)] + [f"Q{i}" for i in range(1, 10)]
CONDS = ["C0", "C"]

assert not (B02 / "runs.json").exists(), "already made"
cases = {}
for c in CASES:
    g = json.loads((HID / f"generation_{c}.json").read_text())
    lab = json.loads((HID / f"label_{c}.json").read_text())
    assert hashlib.sha256((ROOT / g["file"]).read_bytes()).hexdigest() == g["sha256"], c
    cases[c] = {"case_id": g["case_id"], "file": g["file"], "sha256": g["sha256"], "kind": g["kind"],
                "mechanism": g["mechanism"], "oracle_best_lag": lab["oracle_best_lag"], "usable": lab["usable"]}
benign_bad = [c for c in CASES if cases[c]["kind"] == "benign" and not cases[c]["usable"]]
assert not benign_bad, f"benign cases not usable, generate their alternates first: {benign_bad}"
(HID / "challenge_set.json").write_text(json.dumps({"criteria": "results/baseline02/CRITERIA.md", "cases": cases},
                                                   indent=1))

rng = np.random.default_rng(SEED)
P, Q = [c for c in CASES if c[0] == "P"], [c for c in CASES if c[0] == "Q"]
n_p = int(rng.choice([4, 5]))                      # nine cases per stage: 4 + 5, which kind has five is drawn
s1 = sorted(rng.choice(P, n_p, replace=False).tolist() + rng.choice(Q, 9 - n_p, replace=False).tolist())
s2 = [c for c in CASES if c not in s1]
stages = {1: list(rng.permutation(s1)), 2: list(rng.permutation(s2))}
order, seq_cases = {}, []
for st, cs in stages.items():
    flips = [0, 0, 0, 0, 1, 1, 1, 1] + [int(st == 2)]   # 4/5 in stage 1, 5/4 in stage 2: balanced over the study
    r1 = rng.permutation(flips)
    r2 = rng.permutation([1 - f for f in flips])
    for i, c in enumerate(cs):
        pair = lambda flip: CONDS[::-1] if flip else CONDS
        seq = [(k, 1) for k in pair(r1[i])] + [(k, 2) for k in pair(r2[i])]
        order[c] = {"stage": st, "runs": [{"position": n + 1, "condition": k, "repeat": r}
                                           for n, (k, r) in enumerate(seq)]}
        seq_cases.append(c)

common = (P01 / "task_common.md").read_text().replace("results/baseline01/", "results/baseline01/, results/baseline02/")
cond = {k: (P01 / f"cond_{k}.md").read_text() for k in CONDS}
OUT = B02 / "run_prompts"
OUT.mkdir()
runs = []
for n, c in enumerate(seq_cases, 1):
    cid, rel = cases[c]["case_id"], cases[c]["file"]
    for e in order[c]["runs"]:
        run = f"b02-{cid[5:]}-{e['condition'].lower()}-r{e['repeat']}"
        text = (common + "\n" + cond[e["condition"]]).replace("{RUN}", run).replace("{CASE_FILE}", rel) \
            .replace("{CASE_PATH_WSL}", f"{WSL_ROOT}/{rel}")
        assert "{" not in text.split("```json")[0], "unfilled placeholder"
        (OUT / f"{run}.txt").write_text(text)
        runs.append({"seq": len(runs) + 1, "stage": order[c]["stage"], "case_block": n, "case_id": cid,
                     "position": e["position"], "condition": e["condition"], "repeat": e["repeat"], "run": run,
                     "prompt": f"results/baseline02/run_prompts/{run}.txt",
                     "sha256": hashlib.sha256(text.encode()).hexdigest()})
pos = {k: {st: [sum(1 for r in runs if r["condition"] == k and r["stage"] == st and r["position"] == p)
                for p in range(1, 5)] for st in (1, 2)} for k in CONDS}
# the order file names cases only by their neutral ids
(B02 / "run_order.json").write_text(json.dumps({"seed": SEED, "conditions": CONDS,
    "stage_blocks": {st: [cases[c]["case_id"] for c in cs] for st, cs in stages.items()},
    "condition_by_stage_and_position": pos}, indent=1))
(B02 / "runs.json").write_text(json.dumps(runs, indent=1))
print(len(runs), "runs;", json.dumps(pos))
print("stage 1 kinds:", sorted(cases[c]["kind"] for c in stages[1]))
