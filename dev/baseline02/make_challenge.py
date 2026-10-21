"""Baseline study 02: generate the 12 cases of results/baseline02/CRITERIA.md section 4 (and benign alternates)."""
from __future__ import annotations

import codecs
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import read_segy  # noqa: E402
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("b01_make_challenge", ROOT / "dev/baseline01/make_challenge.py")
_b01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b01)                      # the frozen study 01 generator: same perturbation code
band_noise, delay, shift, statics = _b01.band_noise, _b01.delay, _b01.shift, _b01.statics

SRC = ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"
OUT = ROOT / "test_dataset/Baseline02_challenge"
HIDDEN = ROOT / "results/baseline02/hidden"
DT = 0.002
SEED_IDS = 161
SEED_IDS_ADDED = 191
# case: (kind, mechanism, steps); a step is (operation, value, seed)
CASES = {
    "P1": ("defect", "time datum", [("delay", 55, None), ("white", 0.2, 162)]),
    "P2": ("defect", "signal to noise (band)", [("band", 1.5, 163)]),
    "P3": ("defect", "signal to noise (white)", [("white", 3.5, 164)]),
    "P4": ("defect", "statics", [("statics", 24, 165)]),
    "P5": ("defect", "statics + noise", [("statics", 12, 166), ("band", 1.2, 167)]),
    "P6": ("defect", "aperture / line length", [("white", 0.2, 168), ("crop", (36, 45), None)]),
    "Q1": ("benign", "weak white noise", [("white", 0.3, 169)]),
    "Q2": ("benign", "weak band noise", [("band", 0.4, 170)]),
    "Q3": ("benign", "small delay", [("delay", 8, None), ("white", 0.2, 171)]),
    "Q4": ("benign", "short line", [("white", 0.2, 172), ("crop", (90, 60), None)]),
    "Q5": ("benign", "small statics", [("statics", 4, 173)]),
    "Q6": ("benign", "white noise", [("white", 0.6, 174)]),
    # six cases added before the freeze (18 cases for power; CRITERIA section 4)
    "P7": ("defect", "time datum", [("delay", 80, None), ("white", 0.2, 182)]),
    "P8": ("defect", "signal to noise (band)", [("band", 2.2, 183)]),
    "P9": ("defect", "geometry headers", [("white", 0.2, 184), ("offset2", None, None)]),
    "Q7": ("benign", "weak band noise", [("band", 0.25, 185)]),
    "Q8": ("benign", "white noise", [("white", 0.45, 186)]),
    "Q9": ("benign", "short line", [("white", 0.2, 187), ("crop", (100, 66), None)]),
    "Q7alt": ("benign", "weak band noise (alternate)", [("band", 0.125, 188)]),
    "Q8alt": ("benign", "white noise (alternate)", [("white", 0.22, 189)]),
    "Q9alt": ("benign", "short line (alternate)", [("white", 0.1, 190), ("crop", (112, 66), None)]),
    # alternates: half the perturbation, used only if the benign case is not usable under the oracle
    "Q1alt": ("benign", "weak white noise (alternate)", [("white", 0.15, 175)]),
    "Q2alt": ("benign", "weak band noise (alternate)", [("band", 0.2, 176)]),
    "Q3alt": ("benign", "small delay (alternate)", [("delay", 4, None), ("white", 0.1, 177)]),
    "Q4alt": ("benign", "short line (alternate)", [("white", 0.1, 178), ("crop", (108, 60), None)]),
    "Q5alt": ("benign", "small statics (alternate)", [("statics", 2, 179)]),
    "Q6alt": ("benign", "white noise (alternate)", [("white", 0.3, 180)]),
}
LINES = ["C 1 2D SEISMIC LINE, SEG-Y", "C 2 DATA SAMPLE FORMAT: IEEE FLOAT (BINARY HEADER)",
         "C 3 SAMPLE INTERVAL AND LENGTH: SEE BINARY HEADER"] + [f"C{i:2d}" for i in range(4, 40)] + [
             "C40 END TEXTUAL HEADER"]
TEXT = codecs.encode("".join(l.ljust(80)[:80] for l in LINES), "cp500")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def case_ids():
    f = HIDDEN / "case_ids.json"
    ids = json.loads(f.read_text()) if f.exists() else {}
    missing = [c for c in CASES if c not in ids]
    if missing:
        rng = np.random.default_rng(SEED_IDS if not ids else SEED_IDS_ADDED)
        used = {p.stem[5:] for p in (ROOT / "test_dataset").rglob("case_*.sgy")} | {
            p.stem[5:] for p in (ROOT / "_b01_hold").glob("case_*.sgy")} | set(ids.values())
        names = [n for n in (f"{v:04x}" for v in rng.choice(65536, size=64, replace=False)) if n not in used]
        ids.update(zip(missing, names))
        HIDDEN.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(ids, indent=1))
    return ids


def make(case):
    ids = case_ids()
    kind, mech, steps = CASES[case]
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"case_{ids[case]}.sgy"
    rec_path = HIDDEN / f"generation_{case}.json"
    if out.exists() or rec_path.exists():
        raise SystemExit(f"{case}: already generated; not overwriting")
    raw = SRC.read_bytes()
    ns = int(np.frombuffer(raw[3220:3222], ">u2")[0])
    tr = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, 240 + 4 * ns).copy()
    d = read_segy(SRC)
    data = d["data"].astype(np.float64)
    t = np.arange(d["ns"]) * DT
    refl_rms = float(np.median(np.sqrt((data[:, (t >= 1.5) & (t <= 2.5)] ** 2).mean(axis=1))))
    info = {"kind": kind, "mechanism": mech, "steps": [], "reflection_rms": refl_rms}
    keep = np.ones(data.shape[0], bool)
    for op, val, seed in steps:
        if op == "delay":
            data, k = delay(data, val)
            info.update(delay_ms=val, samples=k)
        elif op == "white":
            n = np.random.default_rng(seed).standard_normal(data.shape)
            data = data + val * refl_rms * n / np.sqrt((n ** 2).mean())
        elif op == "band":
            data = data + val * refl_rms * band_noise(data.shape, np.random.default_rng(seed))
        elif op == "statics":
            per, sinfo = statics(d, val / 1000.0, seed)
            data = shift(data, per)
            info.update(per_trace_statics_s=np.round(per, 6).tolist(), **sinfo)
        elif op == "offset2":
            off = tr[:, 36:40].copy().view(">i4").ravel() * 2
            tr[:, 36:40] = off.astype(">i4").view("u1").reshape(-1, 4)
            info.update(change="offset header (bytes 37-40) doubled; coordinates unchanged")
        elif op == "crop":
            shots, centre = val
            fldr = tr[:, 8:12].copy().view(">i4").ravel()
            lo = centre - shots // 2
            keep = (fldr >= lo) & (fldr <= lo + shots - 1)
            info.update(shots=shots, fldr_range=[int(lo), int(lo + shots - 1)], traces=int(keep.sum()))
        info["steps"].append({"operation": op, "value": val, "seed": seed})
    tr[:, 240:] = np.asarray(data, dtype=">f4").view("u1").reshape(tr.shape[0], -1)
    if "per_trace_statics_s" in info:
        info["per_trace_statics_s"] = [v for v, k in zip(info["per_trace_statics_s"], keep) if k]
    out.write_bytes(TEXT + raw[3200:3600] + tr[keep].tobytes())
    rec = {"criteria": "results/baseline02/CRITERIA.md", "case": case, "case_id": f"case_{ids[case]}",
           "file": str(out.relative_to(ROOT)), "sha256": sha(out), "source": str(SRC.relative_to(ROOT)),
           "source_sha256": hashlib.sha256(raw).hexdigest(), **info}
    rec_path.write_text(json.dumps(rec))
    print(case, out.name, out.stat().st_size, rec["sha256"][:16])


if __name__ == "__main__":
    for c in sys.argv[1:]:
        make(c)
