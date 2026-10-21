"""Measurement-only audit: how often do velocity picks sit on the scan edge?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402

OUT = ROOT / "results/marm2_oracle_diagnostic"
V_LO, V_HI = 1400.0, 5500.0      # pick_velocity defaults; every audited run used them
SKIP = ("paper_snapshot_", "/expected/", "_to_delete")


def functions(obj, found):
    if isinstance(obj, dict):
        f = obj.get("function")
        if (isinstance(f, list) and f and isinstance(f[0], dict)
                and "v_m_s" in f[0] and "t0_s" in f[0] and "cdp" in obj):
            found.append(obj)
        for v in obj.values():
            functions(v, found)
    elif isinstance(obj, list):
        for v in obj:
            functions(v, found)


def main() -> None:
    rows, seen = [], set()
    for path in sorted((ROOT / "results").rglob("*.json")):
        rel = str(path.relative_to(ROOT))
        if any(s in rel for s in SKIP):
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        found = []
        functions(data, found)
        for loc in found:
            pts = [p for p in loc["function"] if not p.get("held")]
            key = (rel, int(loc["cdp"]),
                   tuple(round(p["v_m_s"]) for p in pts))
            if key in seen:
                continue
            seen.add(key)
            lo = [p["t0_s"] for p in pts if p["v_m_s"] <= V_LO]
            hi = [p["t0_s"] for p in pts if p["v_m_s"] >= V_HI]
            sub_water = ([p["t0_s"] for p in pts if p["v_m_s"] < 1500.0]
                         if "marm2" in rel else None)
            rows.append({"source": rel, "cdp": int(loc["cdp"]),
                         "below_1500_t0_s_marm2_only": sub_water,
                         "valid": loc.get("valid"), "measured_points": len(pts),
                         "floor_pinned_t0_s": lo, "ceiling_pinned_t0_s": hi})
    by_source = {}
    for r in rows:
        s = by_source.setdefault(r["source"], {"locations": 0, "valid_locations": 0,
                                               "points": 0, "floor_pinned": 0,
                                               "ceiling_pinned": 0,
                                               "locations_with_pinned": 0,
                                               "valid_locations_with_pinned": 0,
                                               "below_1500_points_marm2_only": 0})
        s["locations"] += 1
        s["valid_locations"] += bool(r["valid"])
        s["points"] += r["measured_points"]
        s["floor_pinned"] += len(r["floor_pinned_t0_s"])
        s["ceiling_pinned"] += len(r["ceiling_pinned_t0_s"])
        if r["below_1500_t0_s_marm2_only"]:
            s["below_1500_points_marm2_only"] += len(r["below_1500_t0_s_marm2_only"])
        pinned = bool(r["floor_pinned_t0_s"] or r["ceiling_pinned_t0_s"])
        s["locations_with_pinned"] += pinned
        s["valid_locations_with_pinned"] += pinned and bool(r["valid"])
    report = {"scan_edges_m_s": [V_LO, V_HI],
              "note": ("below_1500 uses truth knowledge (Marmousi2 has no Vp under the "
                       "1500 m/s water) and is reported for evaluation only"), "by_source": by_source, "locations": rows}
    (OUT / "pinned_pick_audit.json").write_text(json.dumps(report, indent=1))
    for k, v in by_source.items():
        print(f"{k:70s} {v}")


if __name__ == "__main__":
    main()
