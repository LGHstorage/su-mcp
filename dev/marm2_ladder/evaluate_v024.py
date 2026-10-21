"""v0.24 evaluation (results/v0240/CRITERIA.md): stack quality; migration quality is evaluate_migration.py: truth
match of released stacks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
from evaluate_v020 import quality, ref_quality  # noqa: E402

H9 = E.ROOT / "test_dataset/Marm2_ladder_heldout9"
ROWS = {  # dataset id: (ladder results dir, level key, delay ms, section)
    "v024-h9-st15": ("marm2_ladder_heldout9", "statics_15ms", 0, "D"),
    "v024-h9-bn100": ("marm2_ladder_heldout9", "bandnoise_1p00x", 0, "D"),
    "v024-h9-wn100": ("marm2_ladder_heldout9", "whitenoise_1p0x", 0, "D"),
    "v024-h9-dl080": ("marm2_ladder_heldout9", "delay_080ms", 80, "D"),
    "v024-h9-st15bn": ("marm2_ladder_heldout9", "statics15_bandnoise_0p80x", 0, "D"),
}
CLEAN = ["v024-v2"]


def reference_h9(only=None):
    ids = {v[1]: k for k, v in ROWS.items() if v[0] == "marm2_ladder_heldout9"}
    cfg = {"out": E.RES / "marm2_ladder_heldout9",
           "levels": {lv: (ids[lv], H9 / f"{lv}.sgy", ROWS[ids[lv]][2]) for lv in ids}}
    ref, vp = E.load_reference(), np.load(E.VP_NPY)
    base_fn = E.functions(E.RES / "v015-v2_velocity_model.json", only_valid=True)
    for lv in cfg["levels"]:
        if only and lv not in only:
            continue
        E.run(cfg, lv, ref, vp, base_fn, {})
        print("reference", lv)


def main():
    if sys.argv[1] == "reference_h9":
        reference_h9(sys.argv[2:])
        return
    out = Path(sys.argv[1])
    ref = E.load_reference()
    res = {"good_threshold": round(E.GOOD, 3), "rows": {}, "clean": {}}
    for ds in CLEAN:
        row = {}
        for tag, p in (("stack1", E.RES / "v0240" / "stacks" / f"{ds}_stack1.su"),
                       ("final", E.RES / f"{ds}_stack.su")):
            if p.exists():
                row[tag] = quality(p, ref)
        res["clean"][ds] = row
        print(ds, json.dumps(row))
    for ds, (lad, level, delay, sec) in ROWS.items():
        rq = ref_quality(lad, level)
        row = {"section": sec, "ladder": lad, "level": level, "reference_quality": rq,
               "usable": rq is not None and rq >= E.GOOD}
        s1 = E.RES / "v0240" / "stacks" / f"{ds}_stack1.su"
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
