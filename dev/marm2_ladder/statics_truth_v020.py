"""Evaluation only: residual statics estimated by v0.20 RS against the ladder truth."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
CASES = {"v020-h4-st16": ("Marm2_ladder_heldout4", "statics_16ms"),
         "v020-h2-st18": ("Marm2_ladder_heldout2", "statics_18ms"),
         "v020-l1-st20": ("Marm2_ladder", "statics_20ms"),
         "v020-h5-st12": ("Marm2_ladder_heldout5", "statics_12ms"),
         "v020-h5-st24": ("Marm2_ladder_heldout5", "statics_24ms"),
         "v020-h5-st16bn": ("Marm2_ladder_heldout5", "statics16_bandnoise_1p00x"),
         "v020-c3": (None, None)}
out = {}
for ds, (lad, lv) in CASES.items():
    fs = sorted((ROOT / "results").glob(f"{ds}_residual_statics_p*.json"))
    if not fs:
        continue
    d = json.loads(fs[-1].read_text())
    est_s = {v["sx"]: v["static_ms"] for v in d["shots"].values()}
    est_r = {v["gx"]: v["static_ms"] for v in d["stations"].values()}
    row = {"rms_est_ms": round(1000 * d["rms_s"], 2), "reliability": d["reliability"]}
    if lad:
        prov = json.loads((ROOT / "test_dataset" / lad / "provenance.json").read_text())["levels"][lv]
        ts = {int(k): v for k, v in prov["source_statics_ms"].items()}
        tr = {int(k): v for k, v in prov["receiver_statics_ms"].items()}
        ks = [k for k in est_s if k in ts]; kr = [k for k in est_r if k in tr]
        a, b = np.array([est_s[k] for k in ks]), np.array([ts[k] for k in ks])
        c, e = np.array([est_r[k] for k in kr]), np.array([tr[k] for k in kr])
        # total per-trace is what matters; compare components (sign: static = delay)
        row.update(source_corr=round(float(np.corrcoef(a, b)[0, 1]), 3), source_n=len(ks),
                   source_slope=round(float(np.polyfit(b, a, 1)[0]), 2),
                   receiver_corr=round(float(np.corrcoef(c, e)[0, 1]), 3) if len(kr) > 2 else None,
                   receiver_n=len(kr), true_rms_ms=prov.get("realised_rms_ms"))
    out[ds] = row
    print(ds, row)
(ROOT / "results/v0200/statics_truth.json").write_text(json.dumps(out, indent=1))
