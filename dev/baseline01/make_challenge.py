"""Baseline study 01: generate the 12-case challenge set (results/baseline01/CRITERIA.md, section 4)."""
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
OUT = ROOT / "test_dataset/Baseline01_challenge"
HIDDEN = ROOT / "results/baseline01/hidden"
DT = 0.002
NOISE_BAND = (4.0, 16.0)
SEED_BAND, SEED_STATICS16, SEED_WHITE, SEED_STATICS30, SEED_BADSAMPLE, SEED_IDS, SEED_BAND_D4 = (
    151, 152, 153, 154, 155, 156, 158)
CENTRE = 63
OVERFLOW = np.float32(3.4e38)

CASES = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "K1", "K2", "K3", "K4"]
# pre-written alternates for the controls (CRITERIA.md section 4), generated only if a control fails the oracle
ALTERNATES = {"K3": ("delay", 5), "K4": ("band", 0.3), "K2": ("crop", 90)}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


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


def delay(base, ms):
    k = int(round(ms / 1000 / DT))
    out = np.zeros_like(base)
    out[:, k:] = base[:, :base.shape[1] - k]
    return out, k


def statics(d, rms_s, seed):
    usx, isx = np.unique(d["sx"], return_inverse=True)
    ugx, igx = np.unique(d["gx"], return_inverse=True)
    rng = np.random.default_rng(seed)
    zs, zg = rng.standard_normal(usx.size), rng.standard_normal(ugx.size)
    zs, zg = zs / zs.std(), zg / zg.std()
    s = rms_s / np.sqrt(2)
    per = s * zs[isx] + s * zg[igx]
    return per, {"source_statics_ms": dict(zip(map(int, usx), np.round(s * zs * 1000, 3).tolist())),
                 "receiver_statics_ms": dict(zip(map(int, ugx), np.round(s * zg * 1000, 3).tolist())),
                 "realised_rms_ms": round(float(per.std() * 1000), 2)}


class Writer:
    def __init__(self, ids):
        self.raw = SRC.read_bytes()
        self.ns = int(np.frombuffer(self.raw[3220:3222], ">u2")[0])
        self.tb = 240 + 4 * self.ns
        self.tr = np.frombuffer(self.raw, dtype="u1", offset=3600).reshape(-1, self.tb)
        self.ids = ids

    def path(self, case):
        p = OUT / f"case_{self.ids[case]}.sgy"
        if p.exists():
            raise SystemExit(f"{p} exists; not overwriting")
        return p

    def data(self, case, data, header_fn=None):
        a = self.tr.copy()
        a[:, 240:] = np.asarray(data, dtype=">f4").view("u1").reshape(a.shape[0], -1)
        if header_fn:
            header_fn(a)
        p = self.path(case)
        p.write_bytes(self.raw[:3600] + a.tobytes())
        return p

    def crop(self, case, shots):
        fldr = self.tr[:, 8:12].copy().view(">i4").ravel()
        lo = CENTRE - shots // 2
        hi = lo + shots - 1
        keep = (fldr >= lo) & (fldr <= hi)
        p = self.path(case)
        p.write_bytes(self.raw[:3600] + self.tr[keep].tobytes())
        return p, [int(lo), int(hi)], int(keep.sum())


def main(alternates=()):
    OUT.mkdir(parents=True, exist_ok=True)
    HIDDEN.mkdir(parents=True, exist_ok=True)
    rng_ids = np.random.default_rng(SEED_IDS)
    names = sorted({f"{v:04x}" for v in rng_ids.choice(65536, size=64, replace=False)})
    names = list(rng_ids.permutation(names))[:len(CASES) + len(ALTERNATES)]
    ids = dict(zip(CASES + [f"{k}alt" for k in ALTERNATES], names))
    d = read_segy(SRC)
    base = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl_rms = float(np.median(np.sqrt((base[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    w = Writer(ids)
    rec = {"criteria": "results/baseline01/CRITERIA.md", "source": str(SRC.relative_to(ROOT)),
           "source_sha256": sha(SRC), "reflection_rms": refl_rms, "case_ids": ids, "cases": {}}
    band = band_noise(base.shape, np.random.default_rng(SEED_BAND))
    white = np.random.default_rng(SEED_WHITE).standard_normal(base.shape)
    white /= np.sqrt((white ** 2).mean())

    def put(case, p, **info):
        rec["cases"][case] = {"file": str(p.relative_to(ROOT)), "sha256": sha(p), **info}

    if not alternates:
        data, k = delay(base, 70)
        put("D1", w.data("D1", data), mechanism="time datum", delay_ms=70, samples=k)
        put("D2", w.data("D2", base + 1.8 * refl_rms * band), mechanism="signal to noise (band)",
            noise_x_reflection_rms=1.8, band_hz=list(NOISE_BAND), seed=SEED_BAND)
        put("D3", w.data("D3", base + 2.5 * refl_rms * white), mechanism="signal to noise (white)",
            noise_x_reflection_rms=2.5, seed=SEED_WHITE)
        per16, info16 = statics(d, 0.016, SEED_STATICS16)
        band4 = band_noise(base.shape, np.random.default_rng(SEED_BAND_D4))
        put("D4", w.data("D4", shift(base, per16) + 1.0 * refl_rms * band4), mechanism="statics",
            total_rms_ms=16, noise_x_reflection_rms=1.0, seed_statics=SEED_STATICS16, seed_band=SEED_BAND_D4,
            per_trace_statics_s=np.round(per16, 6).tolist(), **info16)
        per30, info30 = statics(d, 0.030, SEED_STATICS30)
        put("D5", w.data("D5", shift(base, per30)), mechanism="statics (severe)", total_rms_ms=30,
            seed_statics=SEED_STATICS30, per_trace_statics_s=np.round(per30, 6).tolist(), **info30)

        def double_offset(a):
            off = a[:, 36:40].copy().view(">i4").ravel() * 2
            a[:, 36:40] = off.astype(">i4").view("u1").reshape(-1, 4)
        put("D6", w.data("D6", base, double_offset), mechanism="geometry headers",
            change="offset header (bytes 37-40) doubled; coordinates unchanged")
        p, fr, n = w.crop("D7", 32)
        put("D7", p, mechanism="aperture / line length", shots=32, fldr_range=fr, traces=n)
        rng = np.random.default_rng(SEED_BADSAMPLE)
        mid = np.flatnonzero((d["cdp"] >= 800) & (d["cdp"] <= 900))
        itr = int(rng.choice(mid))
        isamp = int(rng.integers(int(1.2 / DT), int(2.0 / DT)))
        bad = base.copy()
        bad[itr, isamp] = OVERFLOW
        put("D8", w.data("D8", bad), mechanism="sample integrity", trace_index=itr, sample=isamp,
            value=float(OVERFLOW), cdp=int(d["cdp"][itr]))
        put("K1", w.data("K1", base), mechanism="benign, unperturbed")
        p, fr, n = w.crop("K2", 64)
        put("K2", p, mechanism="benign, short line", shots=64, fldr_range=fr, traces=n)
        data, k = delay(base, 10)
        put("K3", w.data("K3", data), mechanism="benign, small delay", delay_ms=10, samples=k)
        put("K4", w.data("K4", base + 0.5 * refl_rms * band), mechanism="benign, weak noise",
            noise_x_reflection_rms=0.5, band_hz=list(NOISE_BAND), seed=SEED_BAND)
        out = HIDDEN / "generation.json"
    else:
        for k_ in alternates:
            kind, val = ALTERNATES[k_]
            case = f"{k_}alt"
            if kind == "delay":
                data, k = delay(base, val)
                put(case, w.data(case, data), mechanism="benign, small delay (alternate)", delay_ms=val, samples=k)
            elif kind == "band":
                put(case, w.data(case, base + val * refl_rms * band), mechanism="benign, weak noise (alternate)",
                    noise_x_reflection_rms=val, band_hz=list(NOISE_BAND), seed=SEED_BAND)
            else:
                p, fr, n = w.crop(case, val)
                put(case, p, mechanism="benign, short line (alternate)", shots=val, fldr_range=fr, traces=n)
        out = HIDDEN / "generation_alternates.json"
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.write_text(json.dumps(rec, indent=1))
    print(json.dumps({c: {k: v for k, v in r.items() if k in ("file", "mechanism")} for c, r in rec["cases"].items()},
                     indent=0))


if __name__ == "__main__":
    main(tuple(sys.argv[1:]))
