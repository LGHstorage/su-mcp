"""Baseline study 01: the freeze manifest (CRITERIA.md section 12)."""
import hashlib, json, glob
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/baseline01/FREEZE.json"
assert not OUT.exists(), "already frozen"
groups = {
    "production_code": ["server.py"] + sorted(glob.glob("sumcp/*.py", root_dir=ROOT)),
    "evaluation_servers": sorted(glob.glob("evalsrv/*.py", root_dir=ROOT)) + ["scripts/b01_ab_server.sh",
                                                                                 "scripts/b01_c0_server.sh"],
    "task_texts": sorted(glob.glob("dev/baseline01/prompts/*.md", root_dir=ROOT)),
    "run_prompts": sorted(glob.glob("results/baseline01/run_prompts/*.txt", root_dir=ROOT)),
    "design": ["results/baseline01/C0_SPEC.md", "results/baseline01/run_order_3.json", "results/baseline01/runs.json"],
    "challenge_set": sorted(glob.glob("test_dataset/Baseline01_challenge/*.sgy", root_dir=ROOT)),
    "hidden": sorted(glob.glob("results/baseline01/hidden/*.json", root_dir=ROOT)),
    "generation_and_oracle": ["dev/baseline01/make_challenge.py", "dev/baseline01/oracle.py",
                              "dev/baseline01/neutral_textual_header.py", "dev/baseline01/finalize_set.py",
                              "dev/baseline01/finalize_order3.py", "dev/baseline01/make_run_prompts.py"],
    "evaluation": ["dev/baseline01/evaluate_run.py", "dev/marm2_ladder/evaluate.py", "dev/marm2_oracle/run_oracle.py",
                   "dev/marm2_oracle/common.py", "results/marm2_oracle_diagnostic/er_zero_offset_reference.npz"],
}
h = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
man = {"frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "code_version": "0.33.1",
       "model": "Claude Opus family; operators are general-purpose subagents that inherit the orchestrating "
                "session's model (configured id at freeze: claude-opus-5-5); every run records the model it reports",
       "files": {g: {p: h(p) for p in ps} for g, ps in groups.items()}}
OUT.write_text(json.dumps(man, indent=1))
print(hashlib.sha256(OUT.read_bytes()).hexdigest(), sum(len(v) for v in man["files"].values()), man["frozen_utc"])
