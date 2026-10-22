"""Shot records of model B (results/modelb/CRITERIA.md).

The modeler and its settings are those of the Marmousi2 v2 line (dev/marm2_oracle/generate_v2.py) with a 2.6 s
record. Trace headers are copied from test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy.
usage: generate_b.py run <fd binary> <work dir>
       generate_b.py assemble <work dir> <template sgy> <out sgy>
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

NX, NZ, NB, S, NREC, NT_AFTER_ONSET, NS = 801, 351, 200, 0.005, 96, 2601, 1301
NOTE = ["C13 MODEL B: ANTICLINE, UNCONFORMITY, NORMAL FAULT (results/modelb/CRITERIA.md)",
        "C14 SAME MODELER, GRID, WAVELET AND GEOMETRY AS THE MARMOUSI2 V2 LINE"]


def run(fd, work, vp, shots):
    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "2"))
    n = len(Path(shots).read_text().split())
    subprocess.run([fd, vp, str(NX), str(NZ), "10", "0.001", str(NT_AFTER_ONSET), str(NB), "10", shots, str(n),
                    str(Path(work) / "shots.bin"), str(NREC), str(S)], check=True, env=env)


def assemble(work, template, out):
    out = Path(out)
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting")
    data = np.fromfile(Path(work) / "shots.bin", dtype="<f4")
    raw = Path(template).read_bytes()
    tb = 240 + 4 * NS
    a = np.frombuffer(raw, dtype="u1", offset=3600).reshape(-1, tb).copy()
    data = data.reshape(a.shape[0], NS)
    a[:, 240:] = data.astype(">f4").view("u1").reshape(a.shape[0], -1)
    text = bytearray(raw[:3200])
    text[0:80] = "C01 MODEL B - SECOND GEOLOGICAL MODEL, 2D ACOUSTIC SYNTHETIC, 2.6 S".ljust(80).encode("cp500")
    for i, line in enumerate(NOTE):
        text[(12 + i) * 80:(13 + i) * 80] = line[:80].ljust(80).encode("cp500")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(text) + raw[3200:3600] + a.tobytes())
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        assemble(sys.argv[2], sys.argv[3], sys.argv[4])
