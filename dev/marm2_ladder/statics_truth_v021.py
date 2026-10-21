"""Evaluation only: residual statics estimated by v0.21 RS2 against the ladder truth."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
CASES = {"v021-h4-st16": ("Marm2_ladder_heldout4", "statics_16ms"),
         "v021-h2-st18": ("Marm2_ladder_heldout2", "statics_18ms"),
         "v021-l1-st20": ("Marm2_ladder", "statics_20ms"),
         "v021-h5-st12": ("Marm2_ladder_heldout5", "statics_12ms"),
         "v021-h5-st24": ("Marm2_ladder_heldout5", "statics_24ms"),
         "v021-h5-st16bn": ("Marm2_ladder_heldout5", "statics16_bandnoise_1p00x"),
         "v021-h6-st10": ("Marm2_ladder_heldout6", "statics_10ms"),
         "v021-h6-st18": ("Marm2_ladder_heldout6", "statics_18ms"),
         "v021-h6-st28": ("Marm2_ladder_heldout6", "statics_28ms"),
         "v021-h6-st14wn": ("Marm2_ladder_heldout6", "statics14_whitenoise_0p80x"),
         "v021-cl": (None, None)}
for _ds in ["v021-h3-wn100", "v021-l1-nz100", "v021-h5-wn150", "v021-h6-wn070", "v021-h6-wn120",
            "v021-h6-wn170", "v021-h6-bn100", "v021-h6-dl060"]:
    CASES[_ds] = (None, None)
out = {}
for ds, (lad, lv) in CASES.items():
    fs = sorted((ROOT / "results").glob(f"{ds}_residual_statics_p*.json"))
    if not fs:
        continue
    d = json.loads(fs[-1].read_text())
    est_s = {v["sx"]: v["static_ms"] for v in d["shots"].values()}
    est_r = {v["gx"]: v["static_ms"] for v in d["stations"].values()}
    row = {"passes": len(fs), "amp_factor": d.get("stack_amplitude_factor"), "rms_est_ms": round(1000 * d["rms_s"], 2), "reliability": d["reliability"]}
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
(ROOT / "results/v0210/statics_truth.json").write_text(json.dumps(out, indent=1))
