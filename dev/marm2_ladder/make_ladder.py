"""Degraded copies of the Marmousi2 v2 benchmark (0-2.6 s), one defect at a time."""
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
OUT = ROOT / "test_dataset/Marm2_ladder"
DT = 0.002
DELAYS_MS = [24, 50, 76, 100, 124, 150]
NOISE_X = [0.5, 1.0, 2.0, 4.0]
STATICS_MS = [10, 20, 40]
NOISE_BAND = (4.0, 16.0)


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


def bandnoise(shape, rng):
    ntr, ns = shape
    n = 2 * ns
    white = rng.standard_normal((ntr, n))
    f = np.fft.rfftfreq(n, DT)
    spec = np.fft.rfft(white, axis=1)
    lo, hi = NOISE_BAND
    taper = np.clip((f - (lo - 1)) / 2, 0, 1) * np.clip(((hi + 2) - f) / 2, 0, 1)
    out = np.fft.irfft(spec * taper[None, :], n=n, axis=1)[:, :ns]
    return out / np.sqrt((out ** 2).mean())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = read_segy(SRC)
    base = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl_rms = float(np.median(np.sqrt((base[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    record = {"source": str(SRC.relative_to(ROOT)), "source_sha256": sha(SRC),
              "reflection_rms": refl_rms, "levels": {}}

    for ms in DELAYS_MS:
        k = int(round(ms / 1000 / DT))
        data = np.zeros_like(base)
        data[:, k:] = base[:, :base.shape[1] - k]
        p = write(f"delay_{ms:03d}ms", data, SRC)
        record["levels"][p.stem] = {"ladder": "delay", "delay_ms": ms,
                                    "samples": k, "sha256": sha(p)}

    rng = np.random.default_rng(1)
    unit = bandnoise(base.shape, rng)          # one realisation, scaled per level
    for x in NOISE_X:
        data = base + x * refl_rms * unit
        p = write(f"noise_{x:.1f}x".replace(".", "p"), data, SRC)
        record["levels"][p.stem] = {"ladder": "noise", "noise_x_reflection_rms": x,
                                    "band_hz": list(NOISE_BAND), "seed": 1,
                                    "sha256": sha(p)}

    sx, gx = d["sx"], d["gx"]
    usx, isx = np.unique(sx, return_inverse=True)
    ugx, igx = np.unique(gx, return_inverse=True)
    rng = np.random.default_rng(2)
    zs = rng.standard_normal(usx.size)
    zg = rng.standard_normal(ugx.size)
    zs, zg = zs / zs.std(), zg / zg.std()
    for ms in STATICS_MS:
        s = ms / 1000 / np.sqrt(2)
        per_trace = s * zs[isx] + s * zg[igx]
        data = shift(base, per_trace)
        p = write(f"statics_{ms:02d}ms", data, SRC)
        record["levels"][p.stem] = {
            "ladder": "statics", "total_rms_ms": ms, "seed": 2,
            "realised_rms_ms": round(float(per_trace.std() * 1000), 2),
            "source_statics_ms": dict(zip(map(int, usx), np.round(s * zs * 1000, 3).tolist())),
            "receiver_statics_ms": dict(zip(map(int, ugx), np.round(s * zg * 1000, 3).tolist())),
            "sha256": sha(p)}

    (OUT / "provenance.json").write_text(json.dumps(record, indent=1))
    for k, v in record["levels"].items():
        print(k, {kk: vv for kk, vv in v.items() if not kk.endswith("statics_ms")})


if __name__ == "__main__":
    main()
