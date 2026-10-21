"""Baseline study 02: the freeze manifest."""
import glob
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/baseline02/FREEZE.json"
assert not OUT.exists(), "already frozen"
g = lambda pat: sorted(glob.glob(pat, root_dir=ROOT))
groups = {
    "criteria_and_runbook": ["results/baseline02/CRITERIA.md", "results/baseline02/RUNBOOK.md",
                             "results/baseline01/CRITERIA.md", "results/baseline01/C0_SPEC.md"],
    "production_code": ["server.py"] + g("sumcp/*.py"),
    "evaluation_server": g("evalsrv/*.py") + ["scripts/b01_c0_server.sh"],
    "task_texts": g("dev/baseline01/prompts/*.md"),
    "run_prompts": g("results/baseline02/run_prompts/*.txt"),
    "design": ["results/baseline02/run_order.json", "results/baseline02/runs.json"],
    "challenge_set": g("test_dataset/Baseline02_challenge/*.sgy") + g("_b02_hold/*.sgy"),
    "hidden": g("results/baseline02/hidden/*.json"),
    "generation_and_oracle": g("dev/baseline02/*.py") + ["dev/baseline01/make_challenge.py", "dev/baseline01/oracle.py"],
    "evaluation": ["dev/baseline01/evaluate_run.py", "dev/baseline01/score_all.py", "dev/marm2_ladder/evaluate.py",
                   "dev/marm2_oracle/run_oracle.py", "dev/marm2_oracle/common.py",
                   "results/marm2_oracle_diagnostic/er_zero_offset_reference.npz"],
}
h = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
man = {"frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "code_version": "0.33.1",
       "model": "Claude Opus family; operators are general-purpose subagents that inherit the orchestrating "
                "session's model; every run records the model it reports",
       "files": {k: {p: h(p) for p in ps} for k, ps in groups.items()}}
OUT.write_text(json.dumps(man, indent=1))
print(hashlib.sha256(OUT.read_bytes()).hexdigest(), sum(len(v) for v in man["files"].values()), man["frozen_utc"])
