"""Generate the repaired Marmousi2 benchmark v2 (evaluation track)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V1 = ROOT / "test_dataset/Marm2_known_truth/blind_input/marm2_known_truth_v1.sgy"
VP = ROOT / "test_dataset/Marm2_known_truth/truth/vp_crop_mps_f32.bin"
SHOTS = ROOT / "test_dataset/Marm2_known_truth/truth/shots_full.txt"
OUTDIR = ROOT / "test_dataset/Marm2_v2"
OUT = OUTDIR / "marm2_known_truth_v2.sgy"
WORK = Path(os.environ.get("V2_WORK", Path.home() / "v2" / "chunks"))
NB, S, NREC, NT_AFTER_ONSET, NS = 200, 0.005, 96, 5001, 2501
CHUNK = 21
NOTE = ["C13 V2 BENCHMARK REPAIR: TIME ZERO AT RICKER PEAK (V1 WAS 150 MS LATE)",
        "C14 V2: CERJAN SPONGE NB=200 S=0.005 ON BOTH TIME LEVELS; NO EDGE RETURNS"]


def shots() -> list[int]:
    return [int(s) for s in SHOTS.read_text().split()]


def chunk(k: int) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    sel = shots()[k * CHUNK:(k + 1) * CHUNK]
    out = WORK / f"chunk{k}.bin"
    if out.exists() and out.stat().st_size == len(sel) * NREC * NS * 4:
        print("done already", out)
        return
    sf = WORK / f"shots{k}.txt"
    sf.write_text("".join(f"{s}\n" for s in sel))
    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "2"))
    tmp = out.with_suffix(".part")
    subprocess.run([str(HERE / "fd_v2"), str(VP), "801", "351", "10", "0.001",
                    str(NT_AFTER_ONSET), str(NB), "10", str(sf), str(len(sel)), str(tmp),
                    str(NREC), str(S)], check=True, env=env, stderr=subprocess.DEVNULL)
    tmp.rename(out)
    print("wrote", out, len(sel), "shots")


def assemble() -> None:
    if OUT.exists() and "--replace-broken" not in sys.argv:
        raise SystemExit(f"{OUT} exists; not overwriting")
    n = len(shots())
    parts = [np.fromfile(WORK / f"chunk{k}.bin", dtype="<f4")
             for k in range((n + CHUNK - 1) // CHUNK)]
    data = np.concatenate(parts).reshape(n * NREC, NS)
    old = V1.read_bytes()
    tb = 240 + 4 * NS
    a = np.frombuffer(old, dtype="u1", offset=3600).reshape(-1, tb).copy()
    if a.shape[0] != data.shape[0]:
        raise ValueError("trace count mismatch")
    a[:, 240:] = data.astype(">f4").view("u1").reshape(a.shape[0], -1)
    text = bytearray(old[:3200])
    for i, line in enumerate(NOTE):
        text[(12 + i) * 80:(13 + i) * 80] = line[:80].ljust(80).encode("cp500")
    text[0:80] = "C01 MARM2_KNOWN_TRUTH_V2 - MARMOUSI2-DERIVED 2D ACOUSTIC SYNTHETIC (REPAIRED)"[:80].ljust(80).encode("cp500")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if len(text) != 3200:
        raise ValueError("textual header length")
    OUT.write_bytes(bytes(text) + old[3200:3600] + a.tobytes())
    if OUT.stat().st_size != len(old):
        raise ValueError("output length differs from v1")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    info = {"output": str(OUT.relative_to(ROOT)), "output_sha256": sha(OUT),
            "v1_sha256": sha(V1), "vp_sha256": sha(VP),
            "modeler": "dev/marm2_oracle/acoustic_fd2d_v2.c",
            "modeler_sha256": sha(HERE / "acoustic_fd2d_v2.c"),
            "nb_cells": NB, "sponge_S": S, "sponge": "Cerjan, both time levels",
            "time_zero": "wavelet peak", "record_s": 5.0, "dt_s": 0.002,
            "shots": n, "receivers_per_shot": NREC}
    (OUTDIR / "provenance.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "chunk":
        chunk(int(sys.argv[2]))
    else:
        assemble()
