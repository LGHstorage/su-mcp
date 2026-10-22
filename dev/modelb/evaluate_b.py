"""Scores of the model-B test (results/modelb/CRITERIA.md). Evaluation only; never called by the server.
usage: evaluate_b.py   (writes results/modelb/eval_modelb.json)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
sys.path.insert(0, str(ROOT / "dev/marm2_ladder"))
from common import DT_S, cmp_sort, nmo_stack, read_segy, read_su  # noqa: E402
from run_oracle import agc, reference_match  # noqa: E402
from evaluate import functions  # noqa: E402

RES = ROOT / "results"
REF = RES / "modelb/er_reference_modelb.npz"
TD = ROOT / "test_dataset/ModelB"
WORK = Path(os.environ.get("MODELB_WORK", Path.home() / "modelb_work"))
LEVELS = {"clean": ("modelb-clean", TD / "modelb_clean_2p6s.sgy", 0),
          "delay 60": ("modelb-dl060", TD / "ladder/delay_060ms.sgy", 60),
          "band 1.0": ("modelb-bn100", TD / "ladder/bandnoise_1p00x.sgy", 0),
          "band 1.6": ("modelb-bn160", TD / "ladder/bandnoise_1p60x.sgy", 0),
          "band 2.0": ("modelb-bn200", TD / "ladder/bandnoise_2p00x.sgy", 0),
          "white 1.0": ("modelb-wn100", TD / "ladder/whitenoise_1p0x.sgy", 0),
          "statics 16": ("modelb-st16", TD / "ladder/statics_16ms.sgy", 0),
          "statics 12 + band 1.0": ("modelb-st12bn", TD / "ladder/statics12_bandnoise_1p00x.sgy", 0)}


def load_reference():
    er = np.load(REF)["section"].astype(float)
    n = 4096
    f = np.fft.rfftfreq(n, DT_S)
    er = np.fft.irfft(np.fft.rfft(er, n=n, axis=1) * np.sqrt(1j * 2 * np.pi * f)[None, :], n=n, axis=1)[:, :er.shape[1]]
    return {"raw": er, "agc": agc(er)}


def quality(section, cdp, ref, shift=0):
    return reference_match(section, cdp, ref, shift)["0.7-2.4s"]["best_lag_pm20ms"]


def verdict(ds):
    m = json.loads((ROOT / "state/datasets" / f"{ds}.json").read_text())
    cap = m["capabilities"].get("stack.completed") or {}
    if cap.get("status") != "PASS":
        return {"released": False, "status": cap.get("status")}
    ev = cap["evidence"]
    rel = ev.get("reliability", {})
    td = ev.get("time_datum", {})
    displaced = td.get("level") not in (None, "WITHIN_RESOLUTION", "CONSISTENT")
    return {"released": True, "reliability": rel.get("level"), "quality_reasons": rel.get("quality_reasons"),
            "provenance_reasons": rel.get("provenance_reasons"), "time_datum": td.get("level"),
            "lag_ms": td.get("lag_ms"), "material": rel.get("level") == "WARN" or displaced,
            "conditioning": [c.get("op") or c for c in m.get("conditioning", {}).get("adopted", [])]
            if isinstance(m.get("conditioning"), dict) else m.get("conditioning")}


def main():
    ref = load_reference()
    vel0 = RES / "modelb-clean_vel0.json"
    base = functions(vel0, only_valid=True)
    out = {"levels": {}}
    for name, (ds, sgy, delay_ms) in LEVELS.items():
        row = {"dataset": ds, "verdict": verdict(ds)}
        st = RES / f"{ds}_stack.su"
        if row["verdict"]["released"] and st.exists():
            s = read_su(st)
            row["quality"] = quality(s["data"], s["cdp"], ref)
        d = read_segy(sgy)
        cdps, tn, vn, _ = base
        s = nmo_stack(WORK / ds, "reference", d, cmp_sort(d), cdps, tn, vn, 1.5)
        (WORK / ds / "cmp_sorted.su").unlink(missing_ok=True)
        row["reference_quality"] = quality(s["data"], s["cdp"], ref, int(round(delay_ms / 1000 / DT_S)))
        out["levels"][name] = row
    clean = out["levels"]["clean"].get("quality")
    good = round(0.9 * clean, 3) if clean is not None else None
    out["good_threshold"] = good
    for name, row in out["levels"].items():
        row["usable"] = row["reference_quality"] >= good
        v = row["verdict"]
        if not v["released"]:
            row["class"] = "E" if row["usable"] else "D"
        else:
            g = row["quality"] >= good
            row["class"] = ("A*" if v["material"] else "A") if g else ("Bn" if v["material"] else "C")
    (RES / "modelb/eval_modelb.json").write_text(json.dumps(out, indent=1))
    for name, row in out["levels"].items():
        print(f"{name:24s} {row['class']:3s} q={row.get('quality')} ref={row['reference_quality']} "
              f"rel={row['verdict'].get('reliability')} td={row['verdict'].get('time_datum')}")
    print("good threshold", good)


if __name__ == "__main__":
    main()
