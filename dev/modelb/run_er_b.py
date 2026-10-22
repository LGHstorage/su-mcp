"""Exploding-reflector zero-offset reference of model B, as dev/marm2_oracle/run_er.py does for Marmousi2.
usage: run_er_b.py <er binary> <vp npy> <work dir> <out npz>
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REFINE, DT_FD, NS_OUT, DT_S, SOURCE_DELAY_S = 2, 0.0005, 1301, 0.002, 0.15


def main(er, vp_npy, work, out):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    vp = np.load(vp_npy).astype(np.float64)
    fine = np.repeat(np.repeat(vp, REFINE, 0), REFINE, 1)
    nz, nx = fine.shape
    refl = np.zeros_like(fine)
    refl[:-1] = 0.5 * (np.log(fine[1:]) - np.log(fine[:-1]))
    (work / "vp_half.bin").write_bytes((0.5 * fine).astype("<f4").tobytes())
    (work / "refl.bin").write_bytes(refl.astype("<f4").tobytes())
    dx = 10.0 / REFINE
    decim = int(round(DT_S / DT_FD))
    nt = int(round((NS_OUT - 1) * DT_S / DT_FD + SOURCE_DELAY_S / DT_FD)) + 1
    rec_z = int(round(10.0 / dx))
    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "2"))
    subprocess.run([er, str(work / "vp_half.bin"), str(work / "refl.bin"), str(nx), str(nz), str(dx), str(DT_FD),
                    str(nt), "100", "10.0", str(rec_z), str(REFINE), str(decim), str(work / "er_raw.bin")],
                   check=True, env=env)
    nrec = (nx - 1) // REFINE + 1
    ntout = (nt - 1) // decim + 1
    raw = np.fromfile(work / "er_raw.bin", dtype="<f4").reshape(nrec, ntout)
    shift = int(round(SOURCE_DELAY_S / DT_S))
    section = raw[:, shift:shift + NS_OUT]
    x = 4000.0 + 10.0 * np.arange(nrec)
    np.savez_compressed(out, section=section, x_m=x, dt_s=DT_S,
                        note="model B, exploding reflector, half velocity, source delay removed; "
                             "x in the coordinates of the Marmousi2 line headers")
    print("saved", section.shape)


if __name__ == "__main__":
    main(*sys.argv[1:5])
