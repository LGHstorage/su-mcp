"""v0.23 evaluation (results/v0230/CRITERIA.md): truth match of released stacks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
from evaluate_v020 import quality, ref_quality  # noqa: E402

H8 = E.ROOT / "test_dataset/Marm2_ladder_heldout8"
ROWS = {  # dataset id: (ladder results dir, level key, delay ms, section)
    "v023-h8-bn120": ("marm2_ladder_heldout8", "bandnoise_1p20x", 0, "C"),
    "v023-h8-bn140": ("marm2_ladder_heldout8", "bandnoise_1p40x", 0, "C"),
    "v023-h8-bn200": ("marm2_ladder_heldout8", "bandnoise_2p00x", 0, "C"),
    "v023-h8-wn130": ("marm2_ladder_heldout8", "whitenoise_1p3x", 0, "C"),
    "v023-h8-wn150": ("marm2_ladder_heldout8", "whitenoise_1p5x", 0, "C"),
    "v023-h8-st20bn": ("marm2_ladder_heldout8", "statics20_bandnoise_1p20x", 0, "C"),
    "v023-h8-st18wn": ("marm2_ladder_heldout8", "statics18_whitenoise_1p00x", 0, "C"),
    "v023-h8-dl120bn": ("marm2_ladder_heldout8", "delay120_bandnoise_0p80x", 120, "C"),
}
CLEAN = ["v023-v2", "v023-v2c"]


def reference_h8(only=None):
    ids = {v[1]: k for k, v in ROWS.items() if v[0] == "marm2_ladder_heldout8"}
    cfg = {"out": E.RES / "marm2_ladder_heldout8",
           "levels": {lv: (ids[lv], H8 / f"{lv}.sgy", ROWS[ids[lv]][2]) for lv in ids}}
    ref, vp = E.load_reference(), np.load(E.VP_NPY)
    base_fn = E.functions(E.RES / "v015-v2_velocity_model.json", only_valid=True)
    for lv in cfg["levels"]:
        if only and lv not in only:
            continue
        E.run(cfg, lv, ref, vp, base_fn, {})
        print("reference", lv)


def main():
    if sys.argv[1] == "reference_h8":
        reference_h8(sys.argv[2:])
        return
    out = Path(sys.argv[1])
    ref = E.load_reference()
    res = {"good_threshold": round(E.GOOD, 3), "rows": {}, "clean": {}}
    for ds in CLEAN:
        row = {}
        for tag, p in (("stack1", E.RES / "v0230" / "stacks" / f"{ds}_stack1.su"),
                       ("final", E.RES / f"{ds}_stack.su")):
            if p.exists():
                row[tag] = quality(p, ref)
        res["clean"][ds] = row
        print(ds, json.dumps(row))
    for ds, (lad, level, delay, sec) in ROWS.items():
        rq = ref_quality(lad, level)
        row = {"section": sec, "ladder": lad, "level": level, "reference_quality": rq,
               "usable": rq is not None and rq >= E.GOOD}
        s1 = E.RES / "v0230" / "stacks" / f"{ds}_stack1.su"
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
