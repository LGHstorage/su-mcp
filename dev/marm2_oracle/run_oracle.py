"""Oracle NMO/stack grid for the Marmousi2 benchmark (evaluation only)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ROOT, SOURCE_DELAY_S, DT_S, read_segy, cmp_sort, nmo_stack,  # noqa: E402
                    truth_vrms, picked_functions, read_su)

WORK = Path(os.environ.get("ORACLE_WORK", Path.home() / "oracle_work"))
OUT = ROOT / "results/marm2_oracle_diagnostic"
INPUTS = {"asis": ROOT / "test_dataset/Marm2_matched_pair/marm2_original_2p6s.sgy",
          "t0fix": ROOT / "test_dataset/Marm2_time_corrected/marm2_t0fix_2p6s.sgy",
          "v2": ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"}
PICKS = {"asis": ROOT / "results/marm2_matched_pair/original_window_processing.json",
         "t0fix": OUT / "t0fix_processing.json",
         "v2": ROOT / "results/marm2_v2/v2_2p6_processing.json"}
SHIFT = int(round(SOURCE_DELAY_S / DT_S))
T_KNOTS = np.round(np.arange(0.0, 2.6001, 0.04), 3)
CDP_METRIC = (640, 1100)          # reference comparison range
CDP_SPEC = (700, 1050)            # same range as the earlier spectrum check
WIN = (0.7, 2.4)                  # corrected-time window


def truth_functions(cdps):
    return ([int(c) for c in cdps], [list(T_KNOTS)] * len(cdps),
            [list(np.round(truth_vrms(c * 10.0, T_KNOTS), 1)) for c in cdps])


def spectrum(section, cdp, frame_shift):
    sel = (cdp >= CDP_SPEC[0]) & (cdp <= CDP_SPEC[1])
    i0 = int(round(0.6 / DT_S)) + frame_shift
    i1 = int(round(2.5 / DT_S)) + frame_shift
    seg = section[sel, i0:min(i1, section.shape[1])]
    seg = seg * np.hanning(seg.shape[1])[None, :]
    p = (np.abs(np.fft.rfft(seg, n=2048, axis=1)) ** 2).mean(0)
    f = np.fft.rfftfreq(2048, DT_S)
    c = np.cumsum(p) / p.sum()
    return {"peak_hz": round(float(f[np.argmax(p)]), 2),
            "median_hz": round(float(f[np.searchsorted(c, 0.5)]), 2),
            "p95_hz": round(float(f[np.searchsorted(c, 0.95)]), 2)}


def agc(x, win=101):
    k = np.ones(win) / win
    env = np.sqrt(np.apply_along_axis(lambda r: np.convolve(r * r, k, "same"), 1,
                                      np.asarray(x, float)) + 1e-30)
    return x / env


def load_reference():
    """ER section with the 2D line-versus-plane correction."""
    er = np.load(OUT / "er_zero_offset_reference.npz")["section"].astype(float)
    n = 4096
    f = np.fft.rfftfreq(n, DT_S)
    er = np.fft.irfft(np.fft.rfft(er, n=n, axis=1) * np.sqrt(1j * 2 * np.pi * f)[None, :],
                      n=n, axis=1)[:, :er.shape[1]]
    return {"raw": er, "agc": agc(er)}


WINDOWS = {"0.7-1.4s": (0.7, 1.4), "1.4-2.4s": (1.4, 2.4), "0.7-2.4s": (0.7, 2.4)}


def reference_match(section, cdp, ref, frame_shift):
    """Median per-trace correlation with the ER reference, AGC on both."""
    g = agc(section)
    out = {}
    for name, (lo, hi) in WINDOWS.items():
        i0, i1 = int(round(lo / DT_S)), int(round(hi / DT_S))
        zero, best = [], []
        for row, c in zip(g, cdp):
            if not CDP_METRIC[0] <= c <= CDP_METRIC[1]:
                continue
            r = ref["agc"][int(c) - 400, i0:i1]
            cc = {}
            for lag in range(-10, 11):
                a = row[i0 + frame_shift + lag:i1 + frame_shift + lag]
                if a.size == r.size and np.linalg.norm(a) > 0:
                    cc[lag] = float(a @ r / (np.linalg.norm(a) * np.linalg.norm(r)))
            zero.append(cc.get(0, np.nan))
            best.append(max(cc.values()))
        out[name] = {"zero_lag": round(float(np.nanmedian(zero)), 3),
                     "best_lag_pm20ms": round(float(np.nanmedian(best)), 3)}
    out["traces"] = int(np.sum((cdp >= CDP_METRIC[0]) & (cdp <= CDP_METRIC[1])))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = load_reference()
    data = {k: read_segy(p) for k, p in INPUTS.items()}
    orders = {k: cmp_sort(d) for k, d in data.items()}
    asis_picks = picked_functions(PICKS["asis"])
    grid = {
        "asis_picked_s1.5": ("asis", asis_picks, 1.5),
        "asis_picked_s1.2": ("asis", asis_picks, 1.2),
        "asis_truth5_s1.5": ("asis", truth_functions(asis_picks[0]), 1.5),
        "t0fix_truth5_s1.5": ("t0fix", truth_functions(asis_picks[0]), 1.5),
        "t0fix_truth5_s1.2": ("t0fix", truth_functions(asis_picks[0]), 1.2),
        "t0fix_truthdense_s1.5": ("t0fix", truth_functions(range(545, 1141, 10)), 1.5),
        "t0fix_truthdense_s1.2": ("t0fix", truth_functions(range(545, 1141, 10)), 1.2),
    }
    for key in ("t0fix", "v2"):
        tp = picked_functions(PICKS[key])
        grid[f"{key}_picked_s1.5"] = (key, tp, 1.5)
        grid[f"{key}_picked_s1.2"] = (key, tp, 1.2)
    grid["v2_truth5_s1.5"] = ("v2", truth_functions(asis_picks[0]), 1.5)
    grid["v2_truth5_s1.2"] = ("v2", truth_functions(asis_picks[0]), 1.2)
    metrics, stacks = {}, {}
    for name, (key, (cdps, tn, vn), smute) in grid.items():
        s = nmo_stack(WORK / key, name.replace(".", "p"), data[key], orders[key],
                      cdps, tn, vn, smute)
        frame = SHIFT if key == "asis" else 0
        metrics[name] = {"input": key, "smute": smute, "velocity_locations": len(cdps),
                         "spectrum": spectrum(s["data"], s["cdp"], frame),
                         "reference": reference_match(s["data"], s["cdp"], ref, frame)}
        stacks[name] = s["data"][:, frame:frame + 1301 - SHIFT].astype(np.float32)
        stacks["cdp"] = s["cdp"]
        print(name, json.dumps(metrics[name]))
    # baselines: all pre-NMO traces (direct-wave dominated), the unprocessed 200 m near-offset section, and the
    # reference itself
    for key in ("asis", "t0fix", "v2"):
        d = data[key]
        frame = SHIFT if key == "asis" else 0
        metrics[f"{key}_prenmo_all_traces"] = {"spectrum": spectrum(d["data"], d["cdp"], frame)}
        near = np.abs(d["offset"]) == 200
        o = np.argsort(d["cdp"][near])
        nd, nc = d["data"][near][o], d["cdp"][near][o]
        metrics[f"{key}_near_offset_200m"] = {"spectrum": spectrum(nd, nc, frame),
                                              "reference": reference_match(nd, nc, ref, frame)}
        stacks[f"{key}_near_offset_200m"] = nd[:, frame:frame + 1301 - SHIFT].astype(np.float32)
        stacks[f"{key}_near_cdp"] = nc
    metrics["er_reference"] = {"spectrum": spectrum(ref["raw"], np.arange(ref["raw"].shape[0]) + 400, 0)}
    (OUT / "oracle_metrics.json").write_text(json.dumps(metrics, indent=2))
    np.savez_compressed(OUT / "oracle_stacks.npz",
                        **stacks, note="time axis: corrected zero-offset time, 0-2.45 s")


if __name__ == "__main__":
    main()
