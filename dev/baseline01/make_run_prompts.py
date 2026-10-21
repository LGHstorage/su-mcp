"""Baseline study 01: the 72 frozen task texts, one per run, in run order (results/baseline01/run_prompts/)."""
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "dev/baseline01/prompts"
OUT = ROOT / "results/baseline01/run_prompts"
WSL_ROOT = "/path/to/su-mcp"
assert not OUT.exists(), "already made"
OUT.mkdir(parents=True)
order = json.loads((ROOT / "results/baseline01/run_order_3.json").read_text())
common = (P / "task_common.md").read_text()
cond = {c: (P / f"cond_{c}.md").read_text() for c in order["conditions"]}
runs = []
for n, cid in enumerate(order["case_sequence"], 1):
    short = cid.replace("case_", "")
    for e in order["order"][cid]:
        run = f"b01-{short}-{e['condition'].lower()}-r{e['repeat']}"
        rel = f"test_dataset/Baseline01_challenge/{cid}.sgy"
        text = (common + "\n" + cond[e["condition"]]).replace("{RUN}", run).replace("{CASE_FILE}", rel) \
            .replace("{CASE_PATH_WSL}", f"{WSL_ROOT}/{rel}")
        f = OUT / f"{run}.txt"
        f.write_text(text)
        runs.append({"seq": len(runs) + 1, "case_block": n, "case_id": cid, "position": e["position"],
                     "condition": e["condition"], "repeat": e["repeat"], "run": run,
                     "prompt": str(f.relative_to(ROOT)), "sha256": hashlib.sha256(text.encode()).hexdigest()})
(ROOT / "results/baseline01/runs.json").write_text(json.dumps(runs, indent=1))
print(len(runs), runs[0]["run"], runs[-1]["run"])
