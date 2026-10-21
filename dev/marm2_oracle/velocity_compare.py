"""Picked stacking velocity against the truth-column Vrms proxy, before and after the time-zero correction
(evaluation only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, VP_NPY, picked_functions, truth_vrms  # noqa: E402

OUT = ROOT / "results/marm2_oracle_diagnostic"
RUNS = {"asis": ROOT / "results/marm2_matched_pair/original_window_processing.json",
        "t0fix": OUT / "t0fix_processing.json",
        "v2": ROOT / "results/marm2_v2/v2_2p6_processing.json"}
HALF_APERTURE_M = 1050          # half the 2.1 km spread, as in the earlier evaluation
V_MIN_SCAN = 1400.0


def main() -> None:
    vp = np.load(VP_NPY)
    report = {}
    for name, path in RUNS.items():
        cdps, tn, vn = picked_functions(path)
        rows = []
        for c, ts, vs in zip(cdps, tn, vn):
            x = c * 10.0
            xs = np.arange(max(4000.0, x - HALF_APERTURE_M), min(12000.0, x + HALF_APERTURE_M) + 1, 100.0)
            for t0, v in zip(ts, vs):
                if not 0.6 <= t0 <= 2.28:
                    continue
                col = float(truth_vrms(x, np.array([t0]), vp)[0])
                band = [float(truth_vrms(xx, np.array([t0]), vp)[0]) for xx in xs]
                rows.append({"cdp": c, "t0_s": t0, "picked_m_s": v, "column_vrms_m_s": round(col, 1),
                             "band_m_s": [round(min(band), 1), round(max(band), 1)],
                             "in_band": bool(min(band) <= v <= max(band)),
                             "signed_error_percent": round((v / col - 1) * 100, 1),
                             "at_scan_floor": bool(v <= V_MIN_SCAN),
                             "below_water_velocity": bool(v < 1500.0)})
        err = np.array([r["signed_error_percent"] for r in rows])
        report[name] = {"points": len(rows), "in_band": int(sum(r["in_band"] for r in rows)),
                        "median_signed_error_percent": round(float(np.median(err)), 1),
                        "median_abs_error_percent": round(float(np.median(np.abs(err))), 1),
                        "points_at_scan_floor": int(sum(r["at_scan_floor"] for r in rows)),
                        "points_below_water_velocity": int(sum(r["below_water_velocity"] for r in rows)),
                        "rows": rows}
        print(name, {k: v for k, v in report[name].items() if k != "rows"})
    report["warning"] = ("Vertical-column Vrms is a proxy; 2D stacking velocity in dipping, "
                         "faulted media differs from it. Band = columns within half the spread.")
    (OUT / "velocity_vs_truth.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
