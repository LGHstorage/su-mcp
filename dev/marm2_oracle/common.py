"""Shared I/O for the Marmousi2 oracle diagnostic (evaluation only)."""
from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SU_BIN = ROOT / "dev/ablation/su_bin"
VP_NPY = ROOT / "test_dataset/Marm2_known_truth/truth/marmousi2_vp_crop_10m_mps.npy"
X0_M, DX_M, DZ_M = 4000.0, 10.0, 10.0
SOURCE_DELAY_S = 0.15          # t0 = 1.5 / f0 in the modeler, f0 = 10 Hz
DT_S = 0.002


def read_segy(path: Path) -> dict:
    """Big-endian IEEE SEG-Y as written by the benchmark generator."""
    raw = path.read_bytes()
    ns = struct.unpack(">H", raw[3220:3222])[0]
    dt_us = struct.unpack(">H", raw[3216:3218])[0]
    tb = 240 + 4 * ns
    ntr = (len(raw) - 3600) // tb
    arr = np.frombuffer(raw, dtype="u1", offset=3600, count=ntr * tb).reshape(ntr, tb)
    hdr = arr[:, :240].copy()

    def col(off, fmt=">i4"):
        return np.frombuffer(hdr[:, off:off + np.dtype(fmt).itemsize].tobytes(),
                             dtype=fmt).astype(np.int64)
    scalco = col(70, ">i2")
    if np.any((scalco != 1) & (scalco != 0)):
        raise ValueError("unexpected coordinate scalar")
    sx, gx = col(72), col(80)
    data = np.frombuffer(arr[:, 240:].tobytes(), dtype=">f4").reshape(ntr, ns)
    mid = (sx + gx) / 2.0
    return {"sx": sx, "gx": gx, "offset": gx - sx, "cdp": np.rint(mid / 10).astype(np.int64),
            "data": data.astype(np.float32), "ns": ns, "dt_s": dt_us * 1e-6,
            "raw_headers": hdr, "textual": raw[:3600]}


def write_su_native(path: Path, cdp, offset, sx, gx, data, dt_s=DT_S) -> None:
    """SU in host byte order, the order the non-XDR su_bin build reads."""
    ntr, ns = data.shape
    rec = np.zeros(ntr, dtype=np.dtype([("h", "u1", 240), ("d", "<f4", ns)]))
    h = rec["h"]

    def put(off, values, fmt):
        b = np.asarray(values).astype(fmt).view("u1").reshape(ntr, -1)
        h[:, off:off + b.shape[1]] = b
    put(0, np.arange(1, ntr + 1), "<i4")          # tracl
    put(20, cdp, "<i4")                           # cdp
    put(28, np.ones(ntr), "<i2")                  # trid
    put(36, offset, "<i4")                        # offset
    put(70, np.ones(ntr), "<i2")                  # scalco
    put(72, sx, "<i4")
    put(80, gx, "<i4")
    put(114, np.full(ntr, ns), "<u2")             # ns
    put(116, np.full(ntr, int(round(dt_s * 1e6))), "<u2")  # dt
    rec["d"] = data
    rec.tofile(path)


def read_su(path: Path) -> dict:
    raw = path.read_bytes()
    ns_le = struct.unpack("<H", raw[114:116])[0]
    ns_be = struct.unpack(">H", raw[114:116])[0]
    order = "<" if 0 < ns_le < 32768 and (len(raw) % (240 + 4 * ns_le) == 0) else ">"
    ns = ns_le if order == "<" else ns_be
    tb = 240 + 4 * ns
    ntr = len(raw) // tb
    arr = np.frombuffer(raw, dtype="u1").reshape(ntr, tb)
    cdp = np.frombuffer(arr[:, 20:24].tobytes(), dtype=order + "i4").astype(int)
    data = np.frombuffer(arr[:, 240:].tobytes(), dtype=order + "f4").reshape(ntr, ns)
    return {"cdp": cdp, "data": data.astype(np.float64), "ns": ns}


def cmp_sort(d: dict) -> np.ndarray:
    return np.lexsort((np.abs(d["offset"]), d["cdp"]))


def nmo_stack(work: Path, tag: str, d: dict, order: np.ndarray, cdps, tnmo, vnmo,
              smute: float) -> dict:
    """Actual SU sunmo + sustack on a CMP-sorted copy. Returns stack dict."""
    work.mkdir(parents=True, exist_ok=True)
    src = work / "cmp_sorted.su"
    if not src.exists():
        write_su_native(src, d["cdp"][order], d["offset"][order], d["sx"][order],
                        d["gx"][order], d["data"][order])
    nmo = work / f"{tag}_nmo.su"
    out = work / f"{tag}_stack.su"
    args = [str(SU_BIN / "sunmo"), "cdp=" + ",".join(str(int(c)) for c in cdps)]
    for t, v in zip(tnmo, vnmo):
        args += ["tnmo=" + ",".join(f"{x:.3f}" for x in t),
                 "vnmo=" + ",".join(f"{x:.1f}" for x in v)]
    args.append(f"smute={smute}")
    with src.open("rb") as fi, nmo.open("wb") as fo:
        subprocess.run(args, stdin=fi, stdout=fo, check=True)
    with nmo.open("rb") as fi, out.open("wb") as fo:
        subprocess.run([str(SU_BIN / "sustack"), "key=cdp"], stdin=fi, stdout=fo, check=True)
    nmo.unlink()
    return read_su(out)


def truth_vrms(x_m: float, times: np.ndarray, vp: np.ndarray | None = None) -> np.ndarray:
    """Vertical-column RMS velocity against zero-offset two-way time (proxy)."""
    vp = np.load(VP_NPY) if vp is None else vp
    col = vp[:, int(round((x_m - X0_M) / DX_M))].astype(float)
    dt = 2 * DZ_M / col
    twt = np.cumsum(dt)
    vrms = np.sqrt(np.cumsum(col * col * dt) / twt)
    return np.interp(times, twt, vrms, left=col[0], right=vrms[-1])


def picked_functions(processing_json: Path) -> tuple[list, list, list]:
    record = json.loads(processing_json.read_text())
    result = next(c["result"] for c in record["calls"] if c["tool"] == "pick_velocity")
    valid = [loc for loc in result["locations"] if loc.get("valid", True)]
    cdps = [int(l["cdp"]) for l in valid]
    tnmo = [[p["t0_s"] for p in l["function"]] for l in valid]
    vnmo = [[p["v_m_s"] for p in l["function"]] for l in valid]
    return cdps, tnmo, vnmo
