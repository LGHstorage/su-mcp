"""Eleventh held-out ladder, for v0.26 (see results/v0260/CRITERIA.md): DMO."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import read_segy  # noqa: E402

SRC = ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"
OUT = ROOT / "test_dataset/Marm2_ladder_heldout11"
DT = 0.002
NOISE_BAND = (4.0, 16.0)
SEED_BAND, SEED_STATICS, SEED_WHITE = 111, 112, 113
CROP, CENTRE = 102, 63


def write(name, data, template):
    raw = template.read_bytes()
    ns = data.shape[1]
    tb = 240 + 4 * ns
    a = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, tb).copy()
    a[:, 240:] = data.astype(">f4").view("u1").reshape(a.shape[0], -1)
    path = OUT / f"{name}.sgy"
    if path.exists():
        raise SystemExit(f"{path} exists; not overwriting")
    path.write_bytes(raw[:3600] + a.tobytes())
    return path


def shift(data, seconds):
    ntr, ns = data.shape
    n = 2 * ns
    f = np.fft.rfftfreq(n, DT)
    spec = np.fft.rfft(data, n=n, axis=1)
    spec *= np.exp(-2j * np.pi * f[None, :] * np.asarray(seconds)[:, None])
    return np.fft.irfft(spec, n=n, axis=1)[:, :ns]


def band_noise(shape, rng):
    ntr, ns = shape
    f = np.fft.rfftfreq(ns, DT)
    spec = np.fft.rfft(rng.standard_normal((ntr, ns)), axis=1)
    spec[:, (f < NOISE_BAND[0]) | (f > NOISE_BAND[1])] = 0.0
    out = np.fft.irfft(spec, n=ns, axis=1)
    return out / np.sqrt((out ** 2).mean())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = read_segy(SRC)
    base = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl_rms = float(np.median(np.sqrt((base[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    rec = {"source": str(SRC.relative_to(ROOT)), "source_sha256": sha(SRC), "reflection_rms": refl_rms,
           "criteria": "results/v0260/CRITERIA.md", "levels": {}}

    band = band_noise(base.shape, np.random.default_rng(SEED_BAND))
    white = np.random.default_rng(SEED_WHITE).standard_normal(base.shape)
    white /= np.sqrt((white ** 2).mean())

    sx, gx = d["sx"], d["gx"]
    usx, isx = np.unique(sx, return_inverse=True)
    ugx, igx = np.unique(gx, return_inverse=True)
    rng = np.random.default_rng(SEED_STATICS)
    zs, zg = rng.standard_normal(usx.size), rng.standard_normal(ugx.size)
    zs, zg = zs / zs.std(), zg / zg.std()
    s = 0.012 / np.sqrt(2)
    per = s * zs[isx] + s * zg[igx]
    p = write("statics12_bandnoise_0p60x", shift(base, per) + 0.6 * refl_rms * band, SRC)
    rec["levels"][p.stem] = {"ladder": "combined", "total_rms_ms": 12, "noise": "band",
                             "noise_x_reflection_rms": 0.6, "seed_band": SEED_BAND,
                             "seed_statics": SEED_STATICS, "realised_rms_ms": round(float(per.std() * 1000), 2),
                             "source_statics_ms": dict(zip(map(int, usx), np.round(s * zs * 1000, 3).tolist())),
                             "receiver_statics_ms": dict(zip(map(int, ugx), np.round(s * zg * 1000, 3).tolist())),
                             "sha256": sha(p)}

    p = write("whitenoise_0p8x", base + 0.8 * refl_rms * white, SRC)
    rec["levels"][p.stem] = {"ladder": "white_noise", "noise_x_reflection_rms": 0.8, "seed": SEED_WHITE,
                             "sha256": sha(p)}

    p = write("bandnoise_1p20x", base + 1.2 * refl_rms * band, SRC)
    rec["levels"][p.stem] = {"ladder": "band_noise", "noise_x_reflection_rms": 1.2, "seed": SEED_BAND,
                             "band_hz": list(NOISE_BAND), "sha256": sha(p)}

    k = int(round(0.070 / DT))
    data = np.zeros_like(base)
    data[:, k:] = base[:, :base.shape[1] - k]
    p = write("delay_070ms", data, SRC)
    rec["levels"][p.stem] = {"ladder": "delay", "delay_ms": 70, "samples": k, "sha256": sha(p)}

    raw = SRC.read_bytes()
    ns = int(np.frombuffer(raw[3220:3222], ">u2")[0])
    tr = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, 240 + 4 * ns)
    fldr = tr[:, 8:12].copy().view(">i4").ravel()
    lo = CENTRE - CROP // 2
    hi = lo + CROP - 1
    keep = (fldr >= lo) & (fldr <= hi)
    p = OUT / f"crop_{CROP:03d}shots.sgy"
    if p.exists():
        raise SystemExit(f"{p} exists")
    p.write_bytes(raw[:3600] + tr[keep].tobytes())
    rec["levels"][p.stem] = {"ladder": "crop", "shots": CROP, "fldr_range": [lo, hi],
                             "traces": int(keep.sum()), "sha256": sha(p)}
    (OUT / "provenance.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k_: {kk: vv for kk, vv in v.items() if not kk.endswith("_ms") or kk == "total_rms_ms"
                           if kk != "sha256"} for k_, v in rec["levels"].items()}))


if __name__ == "__main__":
    main()
