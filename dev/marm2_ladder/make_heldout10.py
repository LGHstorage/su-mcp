"""Tenth held-out ladder, for v0.25 (see results/v0250/CRITERIA.md): short lines."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"
OUT = ROOT / "test_dataset/Marm2_ladder_heldout10"
DT = 0.002
CROPS = [27, 52, 77, 102]
CENTRE = 63
NOISE_X, SEED_BAND, BAND = 0.8, 101, (4.0, 16.0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = SRC.read_bytes()
    head = raw[:3600]
    ns = int(np.frombuffer(raw[3220:3222], ">u2")[0])
    tb = 240 + 4 * ns
    tr = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, tb)
    fldr = tr[:, 8:12].copy().view(">i4").ravel()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    rec = {"source": str(SRC.relative_to(ROOT)), "criteria": "results/v0250/CRITERIA.md", "levels": {}}
    for n in CROPS:
        lo = CENTRE - n // 2
        hi = lo + n - 1
        keep = (fldr >= lo) & (fldr <= hi)
        p = OUT / f"crop_{n:03d}shots.sgy"
        if p.exists():
            raise SystemExit(f"{p} exists")
        p.write_bytes(head + tr[keep].tobytes())
        rec["levels"][p.stem] = {"ladder": "crop", "shots": n, "fldr_range": [lo, hi],
                                 "cmp_span_m_approx": (n - 1) * 40 + 950, "traces": int(keep.sum()),
                                 "sha256": sha(p)}
    data = tr[:, 240:].copy().view(">f4").reshape(-1, ns).astype(np.float64)
    t = np.arange(ns) * DT
    refl_rms = float(np.median(np.sqrt((data[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    rng = np.random.default_rng(SEED_BAND)
    f = np.fft.rfftfreq(ns, DT)
    spec = np.fft.rfft(rng.standard_normal(data.shape), axis=1)
    spec[:, (f < BAND[0]) | (f > BAND[1])] = 0.0
    unit = np.fft.irfft(spec, n=ns, axis=1)
    unit /= np.sqrt((unit ** 2).mean())
    noisy = data + NOISE_X * refl_rms * unit
    out = tr.copy()
    out[:, 240:] = noisy.astype(">f4").view("u1").reshape(out.shape[0], -1)
    p = OUT / "bandnoise_0p80x.sgy"
    if p.exists():
        raise SystemExit(f"{p} exists")
    p.write_bytes(head + out.tobytes())
    rec["levels"][p.stem] = {"ladder": "band_noise", "noise_x_reflection_rms": NOISE_X, "seed": SEED_BAND,
                             "band_hz": list(BAND), "sha256": sha(p)}
    (OUT / "provenance.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "sha256"} for k, v in rec["levels"].items()}))


if __name__ == "__main__":
    main()
