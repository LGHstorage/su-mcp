"""v0.22 evaluation (results/v0220/CRITERIA.md): truth match of released stacks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
from evaluate_v020 import quality, ref_quality  # noqa: E402

H7 = E.ROOT / "test_dataset/Marm2_ladder_heldout7"
ROWS = {  # dataset id: (ladder results dir, level key, delay ms, section)
    "v022-h2-st18": ("marm2_ladder_heldout2", "statics_18ms", 0, "B"),
    "v022-h4-st16": ("marm2_ladder_heldout4", "statics_16ms", 0, "B"),
    "v022-l1-st20": ("marm2_ladder", "statics_20ms", 0, "B"),
    "v022-h5-st12": ("marm2_ladder_heldout5", "statics_12ms", 0, "B"),
    "v022-h5-st24": ("marm2_ladder_heldout5", "statics_24ms", 0, "B"),
    "v022-h5-st16bn": ("marm2_ladder_heldout5", "statics16_bandnoise_1p00x", 0, "B"),
    "v022-h3-wn100": ("marm2_ladder_heldout3", "whitenoise_1p0x", 0, "B"),
    "v022-l1-nz100": ("marm2_ladder", "noise_1p0x", 0, "B"),
    "v022-h5-wn150": ("marm2_ladder_heldout5", "whitenoise_1p5x", 0, "B"),
    "v022-h6-st10": ("marm2_ladder_heldout6", "statics_10ms", 0, "B"),
    "v022-h6-st18": ("marm2_ladder_heldout6", "statics_18ms", 0, "B"),
    "v022-h6-st28": ("marm2_ladder_heldout6", "statics_28ms", 0, "B"),
    "v022-h6-wn070": ("marm2_ladder_heldout6", "whitenoise_0p7x", 0, "B"),
    "v022-h6-wn120": ("marm2_ladder_heldout6", "whitenoise_1p2x", 0, "B"),
    "v022-h6-wn170": ("marm2_ladder_heldout6", "whitenoise_1p7x", 0, "B"),
    "v022-h6-bn100": ("marm2_ladder_heldout6", "bandnoise_1p00x", 0, "B"),
    "v022-h6-dl060": ("marm2_ladder_heldout6", "delay_060ms", 60, "B"),
    "v022-h6-st14wn": ("marm2_ladder_heldout6", "statics14_whitenoise_0p80x", 0, "B"),
    "v022-h7-st16bn": ("marm2_ladder_heldout7", "statics16_bandnoise_1p00x", 0, "C"),
    "v022-h7-bn080": ("marm2_ladder_heldout7", "bandnoise_0p80x", 0, "C"),
    "v022-h7-bn160": ("marm2_ladder_heldout7", "bandnoise_1p60x", 0, "C"),
    "v022-h7-wn100": ("marm2_ladder_heldout7", "whitenoise_1p0x", 0, "C"),
    "v022-h7-st14": ("marm2_ladder_heldout7", "statics_14ms", 0, "C"),
    "v022-h7-dl090": ("marm2_ladder_heldout7", "delay_090ms", 90, "C"),
    "v022-h7-tail": ("marm2_ladder_heldout7", "tailnoise_2p0x", 0, "C"),
    "v022-h7-st12wn": ("marm2_ladder_heldout7", "statics12_whitenoise_0p60x", 0, "C"),
}
CLEAN = ["v022-v2", "v022-v2c"]


def reference_h7(only=None):
    ids = {v[1]: k for k, v in ROWS.items() if v[0] == "marm2_ladder_heldout7"}
    cfg = {"out": E.RES / "marm2_ladder_heldout7",
           "levels": {lv: (ids[lv], H7 / f"{lv}.sgy", ROWS[ids[lv]][2]) for lv in ids}}
    ref, vp = E.load_reference(), np.load(E.VP_NPY)
    base_fn = E.functions(E.RES / "v015-v2_velocity_model.json", only_valid=True)
    for lv in cfg["levels"]:
        if only and lv not in only:
            continue
        E.run(cfg, lv, ref, vp, base_fn, {})
        print("reference", lv)


def main():
    if sys.argv[1] == "reference_h7":
        reference_h7(sys.argv[2:])
        return
    out = Path(sys.argv[1])
    ref = E.load_reference()
    res = {"good_threshold": round(E.GOOD, 3), "rows": {}, "clean": {}}
    for ds in CLEAN:
        row = {}
        for tag, p in (("stack1", E.RES / "v0220" / "stacks" / f"{ds}_stack1.su"),
                       ("final", E.RES / f"{ds}_stack.su")):
            if p.exists():
                row[tag] = quality(p, ref)
        res["clean"][ds] = row
        print(ds, json.dumps(row))
    for ds, (lad, level, delay, sec) in ROWS.items():
        rq = ref_quality(lad, level)
        row = {"section": sec, "ladder": lad, "level": level, "reference_quality": rq,
               "usable": rq is not None and rq >= E.GOOD}
        s1 = E.RES / "v0220" / "stacks" / f"{ds}_stack1.su"
        final = E.RES / f"{ds}_stack.su"
        if s1.exists():
            row["stack1"] = quality(s1, ref)
        if final.exists():
            row["final"] = quality(final, ref)
            row["good"] = row["final"]["best_lag"] >= E.GOOD
        res["rows"][ds] = row
        print(ds, json.dumps({k: v for k, v in row.items() if k != "ladder"}))
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
