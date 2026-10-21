"""v0.19 evaluation B/D: truth match of released stacks (results/v0190/CRITERIA.md)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402

ROWS = {  # dataset id: (ladder results dir, level key, delay ms)
    "v019-ho-st15": ("marm2_ladder_heldout", "statics_15ms", 0),
    "v019-ho-bn300": ("marm2_ladder_heldout", "bandnoise_3p00x", 0),
    "v019-ho-dl110": ("marm2_ladder_heldout", "delay_110", 110),
    "v019-h2-bn250": ("marm2_ladder_heldout2", "bandnoise_2p50x", 0),
    "v019-h2-st18": ("marm2_ladder_heldout2", "statics_18ms", 0),
    "v019-h3-bn175": ("marm2_ladder_heldout3", "bandnoise_1p75x", 0),
    "v019-h3-bn225": ("marm2_ladder_heldout3", "bandnoise_2p25x", 0),
    "v019-h4-bn030": ("marm2_ladder_heldout4", "bandnoise_0p30x", 0),
    "v019-h4-bn160": ("marm2_ladder_heldout4", "bandnoise_1p60x", 0),
    "v019-h4-bn220": ("marm2_ladder_heldout4", "bandnoise_2p20x", 0),
    "v019-h4-bn280": ("marm2_ladder_heldout4", "bandnoise_2p80x", 0),
    "v019-h4-st16": ("marm2_ladder_heldout4", "statics_16ms", 0),
    "v019-h4-st22": ("marm2_ladder_heldout4", "statics_22ms", 0),
    "v019-h4-dl105": ("marm2_ladder_heldout4", "delay_105", 105),
}
CONDITIONED = ["v019-v2", "v019-c1", "v019-c2", "v019-c3"]   # clean v2, section C

H4 = E.ROOT / "test_dataset/Marm2_ladder_heldout4"
H4_FILES = {"bandnoise_0p30x": "bandnoise_0p30x.sgy", "bandnoise_1p60x": "bandnoise_1p60x.sgy",
            "bandnoise_2p20x": "bandnoise_2p20x.sgy", "bandnoise_2p80x": "bandnoise_2p80x.sgy",
            "statics_16ms": "statics_16ms.sgy", "statics_22ms": "statics_22ms.sgy",
            "delay_105": "delay_105ms.sgy"}


def reference_h4():
    """Clean-baseline-pick reference stack for each fourth-ladder level (E.run)."""
    import numpy as np
    ids = {v[1]: k for k, v in ROWS.items() if v[0] == "marm2_ladder_heldout4"}
    cfg = {"out": E.RES / "marm2_ladder_heldout4",
           "levels": {lv: (ids[lv], H4 / f, ROWS[ids[lv]][2]) for lv, f in H4_FILES.items()}}
    ref, vp = E.load_reference(), np.load(E.VP_NPY)
    base_fn = E.functions(E.RES / "v015-v2_velocity_model.json", only_valid=True)
    for lv in cfg["levels"]:
        E.run(cfg, lv, ref, vp, base_fn, {})
        print("reference", lv)


def main():
    if sys.argv[1] == "reference_h4":
        reference_h4()
        return
    out_path = Path(sys.argv[1])
    ids = sys.argv[2:] or list(ROWS)
    if ids == ["conditioned"]:
        ref = E.load_reference()
        res = {}
        for ds in CONDITIONED:
            s = E.read_su(E.RES / f"{ds}_stack.su")
            mm = E.match(s["data"], s["cdp"], ref, 0)
            res[ds] = {"released_quality": mm["best_lag"], "zero_lag": mm["zero_lag"],
                       "good": mm["best_lag"] >= E.GOOD}
            print(ds, res[ds])
        out_path.write_text(json.dumps({"good_threshold": round(E.GOOD, 3), "rows": res}, indent=1))
        return
    ref = E.load_reference()
    res = {}
    for ds in ids:
        lad, level, delay = ROWS[ds]
        m = json.loads((E.RES / lad / "metrics" / f"{level}.json").read_text())
        b = m["stacks"]["baseline_picks_supplementary"]
        # a delayed level is judged after removing the delay (R1 lag, else the true delay)
        ref_q = ((b.get("lag_corrected") or {}).get("best_lag")
                 or (b.get("delay_compensated") or {}).get("best_lag") or b.get("best_lag"))
        row = {"ladder": lad, "level": level, "reference_quality": ref_q,
               "usable": ref_q is not None and ref_q >= E.GOOD}
        st = E.RES / f"{ds}_stack.su"
        if st.exists():
            s = E.read_su(st)
            mm = E.match(s["data"], s["cdp"], ref, int(round(delay / 1000 / E.DT)))
            row.update(released_quality=mm["best_lag"], zero_lag=mm["zero_lag"],
                       good=mm["best_lag"] >= E.GOOD)
        res[ds] = row
        print(ds, row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"good_threshold": round(E.GOOD, 3), "rows": res}, indent=1))


if __name__ == "__main__":
    main()
