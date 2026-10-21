"""Build the exploding-reflector zero-offset reference section (evaluation only)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, VP_NPY, SOURCE_DELAY_S, DT_S  # noqa: E402

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("ORACLE_WORK", Path.home() / "oracle_work")) / "er"
OUT = ROOT / "results/marm2_oracle_diagnostic"
REFINE = 2                      # 10 m model cells -> 5 m FD cells (nearest)
DT_FD = 0.0005
NS_OUT = 1301


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    vp = np.load(VP_NPY).astype(np.float64)
    fine = np.repeat(np.repeat(vp, REFINE, 0), REFINE, 1)
    nz, nx = fine.shape
    refl = np.zeros_like(fine)
    refl[:-1] = 0.5 * (np.log(fine[1:]) - np.log(fine[:-1]))
    (WORK / "vp_half.bin").write_bytes((0.5 * fine).astype("<f4").tobytes())
    (WORK / "refl.bin").write_bytes(refl.astype("<f4").tobytes())
    dx = 10.0 / REFINE
    decim = int(round(DT_S / DT_FD))
    nt = int(round((NS_OUT - 1) * DT_S / DT_FD + SOURCE_DELAY_S / DT_FD)) + 1
    rec_z = int(round(10.0 / dx))
    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "2"))
    subprocess.run([str(HERE / "er"), str(WORK / "vp_half.bin"), str(WORK / "refl.bin"),
                    str(nx), str(nz), str(dx), str(DT_FD), str(nt), "100", "10.0",
                    str(rec_z), str(REFINE), str(decim), str(WORK / "er_raw.bin")],
                   check=True, env=env)
    nrec = (nx - 1) // REFINE + 1
    ntout = (nt - 1) // decim + 1
    raw = np.fromfile(WORK / "er_raw.bin", dtype="<f4").reshape(nrec, ntout)
    shift = int(round(SOURCE_DELAY_S / DT_S))
    section = raw[:, shift:shift + NS_OUT]
    x = 4000.0 + 10.0 * np.arange(nrec)
    np.savez_compressed(OUT / "er_zero_offset_reference.npz", section=section,
                        x_m=x, dt_s=DT_S, note="exploding reflector, half velocity, "
                        "source delay removed; time axis = zero-offset two-way time")
    print("saved", section.shape)


if __name__ == "__main__":
    main()
