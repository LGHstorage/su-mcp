"""v0.28 evaluation (results/v0280/CRITERIA.md): depth imaging."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
from evaluate_v027 import quality, reliability, judge  # noqa: E402
sys.path.insert(0, str(E.ROOT / "dev/marm2_oracle"))
from run_oracle import agc  # noqa: E402

RES = E.RES
IDS = ["v028-v2", "v028-h13-sb", "v028-h13-wn", "v028-h13-bn", "v028-h13-dl", "v028-h13-c090"]
OTHER = ["v028-v2n"]
DREF = RES / "migration_reference/er_depth_true_pspi.npz"
DT, DZREF = 0.002, 10.0
WIN = {"0.5-1.2km": (500, 1200), "1.2-2.4km": (1200, 2400), "0.5-2.4km": (500, 2400)}


def smooth5(arr):
    n = arr.shape[0]
    out = []
    for i in range(n):
        lo, hi = (0, n) if n <= 5 else (max(0, min(i - 2, n - 5)), max(0, min(i - 2, n - 5)) + 5)
        out.append(np.median(arr[lo:hi], axis=0))
    return np.stack(out)


def dix(vr, dt):
    t = np.arange(vr.size) * dt
    tv2 = t * vr ** 2
    v2 = np.empty(vr.size); v2[0] = vr[0] ** 2; v2[1:] = np.diff(tv2) / dt
    return np.sqrt(np.maximum(v2, 1.0))


def c5(model_path, vp):
    m = json.loads(Path(model_path).read_text())
    rep = {r["cdp"]: r for r in m["reports"]}
    locs = sorted(m["locations"], key=lambda l: l["cdp"])
    t = np.arange(0, 2.6 + 1e-9, DT)
    vr = np.stack([np.interp(t, [p["t0_s"] for p in l["function"]], [p["v_m_s"] for p in l["function"]]) for l in locs])
    vs = smooth5(vr)
    rel = []
    for l, v in zip(locs, vs):
        r = rep.get(l["cdp"], {})
        if not r.get("valid"):
            continue
        vi = dix(v, DT)
        z = np.concatenate([[0], np.cumsum(vi[:-1] * DT / 2)])
        col = vp[:, int(l["cdp"]) - 400].astype(float)
        tz = np.concatenate([[0], np.cumsum(2 * DZREF / col[:-1])])
        ztrue = np.interp(t, tz, np.arange(col.size) * DZREF)
        for tt in np.arange(0.7, float(r.get("supported_to_s") or 0) + 1e-9, 0.1):
            i = int(round(tt / DT))
            rel.append((z[i] - ztrue[i]) / ztrue[i])
    rel = np.array(rel)
    return {"pairs": int(rel.size), "within5": int((np.abs(rel) <= 0.05).sum()),
            "C5": round(float(np.mean(np.abs(rel) <= 0.05)), 3), "median_pct": round(float(np.median(rel)) * 100, 2)}


def read_depth(path):
    raw = np.fromfile(path, dtype="u1")
    for o in "<>":
        ns = int(np.frombuffer(raw[114:116].tobytes(), o + "u2")[0])
        if 0 < ns < 100000 and raw.size % (240 + 4 * ns) == 0:
            tr = raw.reshape(-1, 240 + 4 * ns)
            dz = float(np.frombuffer(raw[180:184].tobytes(), o + "f4")[0])
            return (tr[:, 20:24].copy().view(o + "i4").ravel(),
                    tr[:, 240:].copy().view(o + "f4").reshape(-1, ns).astype(float), dz)


def depth_match(path, ref_agc):
    c, d, dz = read_depth(path)
    step = int(round(DZREF / dz))
    d = d[:, ::step]
    nz = min(d.shape[1], ref_agc.shape[1])
    g = agc(d[:, :nz])
    out = {}
    for name, (lo, hi) in WIN.items():
        i0, i1 = int(lo / DZREF), int(hi / DZREF)
        best = []
        for row, cc in zip(g, c):
            if not 640 <= cc <= 1100:
                continue
            r = ref_agc[int(cc) - 400, i0:i1]
            vals = [float(row[i0 + l:i1 + l] @ r / (np.linalg.norm(row[i0 + l:i1 + l]) * np.linalg.norm(r)))
                    for l in range(-4, 5) if i1 + l <= row.size and np.linalg.norm(row[i0 + l:i1 + l]) > 0]
            if vals:
                best.append(max(vals))
        out[name] = round(float(np.median(best)), 3) if best else None
    return out


def main():
    ref = E.load_reference()
    vp = np.load(E.VP_NPY)
    dref = agc(np.load(DREF)["section"].astype(float))
    out = {"rows": {}}
    for ds in IDS + OTHER:
        row = {}
        for tag in ("stack0", "stack1"):
            p = RES / "v0280/stacks" / f"{ds}_{tag}.su"
            if p.exists():
                row[tag] = quality(p, ref)["best_lag"]
        row["final"] = quality(RES / f"{ds}_stack.su", ref)["best_lag"]
        row["C5"] = c5(RES / f"{ds}_velF.json", vp)
        for meth in ("depth_convert", "depth_pspi"):
            p = RES / f"{ds}_mig_{meth}.su"
            if p.exists():
                row[meth] = depth_match(p, dref)
        st, lvl, reasons, _ = reliability(ds)
        row["reliability"] = [lvl, reasons]
        row["class"] = judge(row["final"] >= E.GOOD, lvl, st == "PASS")
        out["rows"][ds] = row
        print(ds, json.dumps(row), flush=True)
    rows = [out["rows"][d]["C5"] for d in IDS[1:]]
    out["pooled_C5_ladder"] = round(sum(r["within5"] for r in rows) / sum(r["pairs"] for r in rows), 3)
    print("pooled ladder C5", out["pooled_C5_ladder"])
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
