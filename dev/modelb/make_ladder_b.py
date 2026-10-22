"""Degraded copies of the model-B line (results/modelb/CRITERIA.md), with the functions of the Marmousi2 ladders."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import read_segy  # noqa: E402

SRC = ROOT / "test_dataset/ModelB/modelb_clean_2p6s.sgy"
OUT = ROOT / "test_dataset/ModelB/ladder"
DT = 0.002
NOISE_BAND = (4.0, 16.0)
SEED_BAND, SEED_STATICS, SEED_WHITE = 151, 152, 153


def write(name, data):
    raw = SRC.read_bytes()
    ns = data.shape[1]
    a = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, 240 + 4 * ns).copy()
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


def statics(d, rms_s, seed):
    usx, isx = np.unique(d["sx"], return_inverse=True)
    ugx, igx = np.unique(d["gx"], return_inverse=True)
    rng = np.random.default_rng(seed)
    zs, zg = rng.standard_normal(usx.size), rng.standard_normal(ugx.size)
    zs, zg = zs / zs.std(), zg / zg.std()
    s = rms_s / np.sqrt(2)
    return s * zs[isx] + s * zg[igx]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = read_segy(SRC)
    base = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl = float(np.median(np.sqrt((base[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    rec = {"source": str(SRC.relative_to(ROOT)), "source_sha256": sha(SRC), "reflection_rms": refl,
           "criteria": "results/modelb/CRITERIA.md", "seeds": [SEED_BAND, SEED_STATICS, SEED_WHITE], "levels": {}}
    band = band_noise(base.shape, np.random.default_rng(SEED_BAND))
    white = np.random.default_rng(SEED_WHITE).standard_normal(base.shape)
    white /= np.sqrt((white ** 2).mean())
    k = int(round(0.060 / DT))
    delayed = np.zeros_like(base)
    delayed[:, k:] = base[:, :base.shape[1] - k]
    st16 = statics(d, 0.016, SEED_STATICS)
    st12 = statics(d, 0.012, SEED_STATICS)
    levels = {"delay_060ms": (delayed, {"delay_ms": 60}),
              "bandnoise_1p00x": (base + 1.0 * refl * band, {"band_x": 1.0}),
              "bandnoise_1p60x": (base + 1.6 * refl * band, {"band_x": 1.6}),
              "bandnoise_2p00x": (base + 2.0 * refl * band, {"band_x": 2.0}),
              "whitenoise_1p0x": (base + 1.0 * refl * white, {"white_x": 1.0}),
              "statics_16ms": (shift(base, st16), {"statics_rms_ms": 16, "realised_ms": round(float(st16.std() * 1e3), 2)}),
              "statics12_bandnoise_1p00x": (shift(base, st12) + 1.0 * refl * band,
                                            {"statics_rms_ms": 12, "band_x": 1.0,
                                             "realised_ms": round(float(st12.std() * 1e3), 2)})}
    for name, (data, info) in levels.items():
        p = write(name, data)
        rec["levels"][name] = dict(info, sha256=sha(p))
    (OUT / "provenance.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "sha256"} for k, v in rec["levels"].items()}))


if __name__ == "__main__":
    main()
