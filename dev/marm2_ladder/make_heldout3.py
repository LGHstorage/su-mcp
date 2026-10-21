"""Third held-out degradation ladder for v0.18 (see results/v0180/CRITERIA.md)."""
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
OUT = ROOT / "test_dataset/Marm2_ladder_heldout3"
DT = 0.002
DELAYS_MS = [45]
BAND_NOISE_X = [0.5, 1.25, 1.75, 2.25]
WHITE_NOISE_X = [1.0]
STATICS_MS = [8]
NOISE_BAND = (4.0, 16.0)
SEED_BAND, SEED_STATICS, SEED_WHITE = 31, 32, 33


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
    """Exact fractional delay per trace (positive = later), zero-padded FFT."""
    ntr, ns = data.shape
    n = 2 * ns
    f = np.fft.rfftfreq(n, DT)
    spec = np.fft.rfft(data, n=n, axis=1)
    spec *= np.exp(-2j * np.pi * f[None, :] * np.asarray(seconds)[:, None])
    return np.fft.irfft(spec, n=n, axis=1)[:, :ns]


def band_noise(shape, rng):
    """Unit-RMS noise with no energy outside NOISE_BAND (circular, no crop)."""
    ntr, ns = shape
    f = np.fft.rfftfreq(ns, DT)
    spec = np.fft.rfft(rng.standard_normal((ntr, ns)), axis=1)
    lo, hi = NOISE_BAND
    spec[:, (f < lo) | (f > hi)] = 0.0
    out = np.fft.irfft(spec, n=ns, axis=1)
    return out / np.sqrt((out ** 2).mean())


def band_fraction(x, lo, hi):
    p = np.abs(np.fft.rfft(x, axis=1)) ** 2
    f = np.fft.rfftfreq(x.shape[1], DT)
    return float(p[:, (f >= lo) & (f <= hi)].sum() / p[:, f > 0].sum())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = read_segy(SRC)
    base = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl_rms = float(np.median(np.sqrt((base[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    record = {"source": str(SRC.relative_to(ROOT)), "source_sha256": sha(SRC),
              "reflection_rms": refl_rms, "criteria": "results/v0180/CRITERIA.md",
              "levels": {}}

    for ms in DELAYS_MS:
        k = int(round(ms / 1000 / DT))
        data = np.zeros_like(base)
        data[:, k:] = base[:, :base.shape[1] - k]
        p = write(f"delay_{ms:03d}ms", data, SRC)
        record["levels"][p.stem] = {"ladder": "delay", "delay_ms": ms, "samples": k,
                                    "sha256": sha(p)}

    unit = band_noise(base.shape, np.random.default_rng(SEED_BAND))
    leak = band_fraction(unit, 20.0, 250.0)
    for x in BAND_NOISE_X:
        p = write(f"bandnoise_{x:.2f}x".replace(".", "p"), base + x * refl_rms * unit, SRC)
        record["levels"][p.stem] = {"ladder": "band_noise", "noise_x_reflection_rms": x,
                                    "band_hz": list(NOISE_BAND), "seed": SEED_BAND,
                                    "noise_energy_fraction_above_20hz": leak,
                                    "sha256": sha(p)}

    white = np.random.default_rng(SEED_WHITE).standard_normal(base.shape)
    white /= np.sqrt((white ** 2).mean())
    for x in WHITE_NOISE_X:
        p = write(f"whitenoise_{x:.1f}x".replace(".", "p"), base + x * refl_rms * white, SRC)
        record["levels"][p.stem] = {"ladder": "white_noise", "noise_x_reflection_rms": x,
                                    "seed": SEED_WHITE, "sha256": sha(p)}

    sx, gx = d["sx"], d["gx"]
    usx, isx = np.unique(sx, return_inverse=True)
    ugx, igx = np.unique(gx, return_inverse=True)
    rng = np.random.default_rng(SEED_STATICS)
    zs = rng.standard_normal(usx.size)
    zg = rng.standard_normal(ugx.size)
    zs, zg = zs / zs.std(), zg / zg.std()
    for ms in STATICS_MS:
        s = ms / 1000 / np.sqrt(2)
        per_trace = s * zs[isx] + s * zg[igx]
        p = write(f"statics_{ms:02d}ms", shift(base, per_trace), SRC)
        record["levels"][p.stem] = {
            "ladder": "statics", "total_rms_ms": ms, "seed": SEED_STATICS,
            "realised_rms_ms": round(float(per_trace.std() * 1000), 2),
            "source_statics_ms": dict(zip(map(int, usx), np.round(s * zs * 1000, 3).tolist())),
            "receiver_statics_ms": dict(zip(map(int, ugx), np.round(s * zg * 1000, 3).tolist())),
            "sha256": sha(p)}

    (OUT / "provenance.json").write_text(json.dumps(record, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items()
                          if kk not in ("source_statics_ms", "receiver_statics_ms", "sha256")}
                      for k, v in record["levels"].items()}, indent=0))


if __name__ == "__main__":
    main()
