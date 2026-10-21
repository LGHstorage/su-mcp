"""v0.31 evaluation (results/v0310/CRITERIA.md). Evaluation harness only."""
import json, sys, importlib.util
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa
from evaluate_v027 import quality, reliability, judge  # noqa
RES = E.RES
spec = importlib.util.spec_from_file_location("em", HERE / "evaluate_migration.py")
_a = sys.argv; sys.argv = [_a[0], str(E.ROOT), str(RES / "migration_reference/er_mig_true_blend.npz")]
em = importlib.util.module_from_spec(spec); spec.loader.exec_module(em); sys.argv = _a
mref = {"agc": em.agc(np.load(RES / "migration_reference/er_mig_true_blend.npz")["section"].astype(float))}
ref = E.load_reference()
out = {}
for ds in ["v031-v2", "v031-h14-sb", "v031-h14-wn", "v031-h14-bn", "v031-h14-dl", "v031-v2n"]:
    row = {}
    for tag in ("stack0", "stack1"):
        p = RES / "v0310/stacks" / f"{ds}_{tag}.su"
        if p.exists():
            row[tag] = quality(p, ref)["best_lag"]
    row["final"] = quality(RES / f"{ds}_stack.su", ref)["best_lag"]
    for meth in ("phase_shift", "phase_shift_smooth"):
        p = RES / f"{ds}_mig_{meth}.su"
        if p.exists():
            q = em.q(p, mref)
            row[meth] = [q["best_lag"], q["windows"]["1.4-2.4s"]["best_lag_pm20ms"]]
    st, lvl, reasons, _ = reliability(ds)
    row["class"] = judge(row["final"] >= E.GOOD, lvl, st == "PASS")
    out[ds] = row
    print(ds, json.dumps(row), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
