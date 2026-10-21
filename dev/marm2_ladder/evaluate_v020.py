"""v0.20 evaluation (results/v0200/CRITERIA.md): truth match of released stacks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402

H5 = E.ROOT / "test_dataset/Marm2_ladder_heldout5"
ROWS = {  # dataset id: (ladder results dir, level key, delay ms, section)
    "v020-ho-dl110": ("marm2_ladder_heldout", "delay_110", 110, "B"),
    "v020-l1-dl124": ("marm2_ladder", "delay_124", 124, "B"),
    "v020-h4-dl105": ("marm2_ladder_heldout4", "delay_105", 105, "B"),
    "v020-ho-wn100": ("marm2_ladder_heldout", "whitenoise_1p0x", 0, "B"),
    "v020-h2-wn050": ("marm2_ladder_heldout2", "whitenoise_0p5x", 0, "B"),
    "v020-h3-wn100": ("marm2_ladder_heldout3", "whitenoise_1p0x", 0, "B"),
    "v020-h4-st16": ("marm2_ladder_heldout4", "statics_16ms", 0, "B"),
    "v020-l1-nz100": ("marm2_ladder", "noise_1p0x", 0, "B"),
    "v020-l1-st20": ("marm2_ladder", "statics_20ms", 0, "B"),
    "v020-h2-st18": ("marm2_ladder_heldout2", "statics_18ms", 0, "C"),
    "v020-h5-st12": ("marm2_ladder_heldout5", "statics_12ms", 0, "D"),
    "v020-h5-st24": ("marm2_ladder_heldout5", "statics_24ms", 0, "D"),
    "v020-h5-dl045": ("marm2_ladder_heldout5", "delay_045", 45, "D"),
    "v020-h5-dl080": ("marm2_ladder_heldout5", "delay_080", 80, "D"),
    "v020-h5-dl140": ("marm2_ladder_heldout5", "delay_140", 140, "D"),
    "v020-h5-bn060": ("marm2_ladder_heldout5", "bandnoise_0p60x", 0, "D"),
    "v020-h5-bn130": ("marm2_ladder_heldout5", "bandnoise_1p30x", 0, "D"),
    "v020-h5-bn240": ("marm2_ladder_heldout5", "bandnoise_2p40x", 0, "D"),
    "v020-h5-wn150": ("marm2_ladder_heldout5", "whitenoise_1p5x", 0, "D"),
    "v020-h5-st16bn": ("marm2_ladder_heldout5", "statics16_bandnoise_1p00x", 0, "D"),
}
H5_FILES = {"statics_12ms": "statics_12ms.sgy", "statics_24ms": "statics_24ms.sgy",
            "delay_045": "delay_045ms.sgy", "delay_080": "delay_080ms.sgy",
            "delay_140": "delay_140ms.sgy", "bandnoise_0p60x": "bandnoise_0p60x.sgy",
            "bandnoise_1p30x": "bandnoise_1p30x.sgy", "bandnoise_2p40x": "bandnoise_2p40x.sgy",
            "whitenoise_1p5x": "whitenoise_1p5x.sgy",
            "statics16_bandnoise_1p00x": "statics16_bandnoise_1p00x.sgy"}
CLEAN = ["v020-v2", "v020-c1", "v020-c3"]


def reference_h5():
    ids = {v[1]: k for k, v in ROWS.items() if v[0] == "marm2_ladder_heldout5"}
    cfg = {"out": E.RES / "marm2_ladder_heldout5",
           "levels": {lv: (ids[lv], H5 / f, ROWS[ids[lv]][2]) for lv, f in H5_FILES.items()}}
    ref, vp = E.load_reference(), np.load(E.VP_NPY)
    base_fn = E.functions(E.RES / "v015-v2_velocity_model.json", only_valid=True)
    for lv in cfg["levels"]:
        E.run(cfg, lv, ref, vp, base_fn, {})
        print("reference", lv)


def ref_quality(lad, level):
    m = json.loads((E.RES / lad / "metrics" / f"{level}.json").read_text())
    b = m["stacks"]["baseline_picks_supplementary"]
    return ((b.get("lag_corrected") or {}).get("best_lag")
            or (b.get("delay_compensated") or {}).get("best_lag") or b.get("best_lag"))


def quality(path, ref, delay_ms=0):
    """Truth match; a delayed level whose time axis v0.20 corrected is compared as is."""
    s = E.read_su(path)
    mm = E.match(s["data"], s["cdp"], ref, 0)
    return {"best_lag": mm["best_lag"], "zero_lag": mm["zero_lag"], "traces": int(len(s["cdp"])),
            "cdp_range": [int(np.min(s["cdp"])), int(np.max(s["cdp"]))]}


def main():
    if sys.argv[1] == "reference_h5":
        reference_h5()
        return
    out = Path(sys.argv[1])
    ref = E.load_reference()
    res = {"good_threshold": round(E.GOOD, 3), "rows": {}, "clean": {}}
    for ds in CLEAN:
        p = E.RES / f"{ds}_stack.su"
        if p.exists():
            res["clean"][ds] = quality(p, ref)
    for ds, (lad, level, delay, sec) in ROWS.items():
        rq = ref_quality(lad, level)
        row = {"section": sec, "ladder": lad, "level": level, "reference_quality": rq,
               "usable": rq is not None and rq >= E.GOOD}
        s1 = E.RES / "v0200" / "stacks" / f"{ds}_stack1.su"
        final = E.RES / f"{ds}_stack.su"
        if s1.exists():
            row["stack1"] = quality(s1, ref)
        if final.exists():
            row["final"] = quality(final, ref)
            row["good"] = row["final"]["best_lag"] >= E.GOOD
        res["rows"][ds] = row
        print(ds, json.dumps({k: v for k, v in row.items() if k not in ("ladder",)}))
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
