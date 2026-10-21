"""Migrated exploding-reflector reference for v0.24 (evaluation only)."""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import DT_S, truth_vrms  # noqa: E402
from run_oracle import load_reference  # noqa: E402

OUT = Path(sys.argv[2])
STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 10
CDP0 = 400                      # first cdp of the ER section (row = cdp - 400)
DX = 10.0


def write_su(path, data, dt):
    ntr, ns = data.shape
    hdr = np.zeros((ntr, 60), dtype="<i4")
    h16 = hdr.view("<i2")
    hdr[:, 0] = np.arange(1, ntr + 1)
    hdr[:, 5] = np.arange(CDP0, CDP0 + ntr)
    h16[:, 57] = ns
    h16[:, 58] = int(round(dt * 1e6))
    path.write_bytes(np.concatenate([hdr.view("u1"), data.astype("<f4").view("u1")], axis=1).tobytes())


def read_su(path, ns):
    raw = np.fromfile(path, dtype="u1").reshape(-1, 240 + 4 * ns)
    return raw[:, 240:].copy().view("<f4").reshape(-1, ns).astype(float)


def vint_from_vrms(vrms, dt):
    t = np.arange(vrms.size) * dt
    v2 = np.empty(vrms.size)
    v2[0] = vrms[0] ** 2
    v2[1:] = np.diff(t * vrms ** 2) / dt
    return np.sqrt(np.maximum(v2, 1.0))


def main():
    er = load_reference()["raw"]
    ntr, ns = er.shape
    t = np.arange(ns) * DT_S
    vp = np.load(ROOT / "test_dataset/Marm2_known_truth/truth/marmousi2_vp_crop_10m_mps.npy")
    locs = list(range(CDP0, CDP0 + ntr, STEP))
    if locs[-1] != CDP0 + ntr - 1:
        locs.append(CDP0 + ntr - 1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "er.su"
        write_su(src, er, DT_S)
        migs = []
        for c in locs:
            vint = vint_from_vrms(truth_vrms(c * DX, t, vp), DT_S)
            vf = tmp / "v.bin"
            vint.astype("=f4").tofile(vf)
            out = tmp / "m.su"
            with open(src, "rb") as fi, open(out, "wb") as fo:
                subprocess.run(["sumigps", f"dx={DX}", f"nxpad={ntr // 2}", "ltaper=10",
                                f"vfile={vf}"], stdin=fi, stdout=fo, check=True)
            migs.append(read_su(out, ns))
            print("migrated with truth at cdp", c, flush=True)
    xs = np.array(locs, float)
    cdps = np.arange(CDP0, CDP0 + ntr, dtype=float)
    img = np.zeros_like(er)
    for i, c in enumerate(cdps):
        k = min(max(int(np.searchsorted(xs, c)) - 1, 0), len(xs) - 2)
        w = np.clip((c - xs[k]) / (xs[k + 1] - xs[k]), 0, 1)
        img[i] = (1 - w) * migs[k][i] + w * migs[k + 1][i]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, section=img.astype(np.float32), cdp0=CDP0, step=STEP,
                        note="ER reference (half-derivative) migrated by sumigps with true "
                             "vertical-column Vrms every STEP cdp, blended linearly")


if __name__ == "__main__":
    main()
