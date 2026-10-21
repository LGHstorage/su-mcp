"""Full-length time-zero-corrected copy (0-4.85 s) of the 5.0 s benchmark."""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, SOURCE_DELAY_S, DT_S  # noqa: E402

ORIGINAL = ROOT / "test_dataset/Marm2_known_truth/blind_input/marm2_known_truth_v1.sgy"
OUT = ROOT / "test_dataset/Marm2_time_corrected/marm2_t0fix_full.sgy"
NOTE = "C13 TIME ZERO CORRECTED: 150 MS RICKER ONSET DELAY REMOVED; 0-4.85 S"


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; not overwriting")
    before = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    shift = int(round(SOURCE_DELAY_S / DT_S))
    old = ORIGINAL.read_bytes()
    ns = struct.unpack(">H", old[3220:3222])[0]
    ns_new = ns - shift
    tb, tb_new = 240 + 4 * ns, 240 + 4 * ns_new
    ntr = (len(old) - 3600) // tb
    a = np.frombuffer(old, dtype="u1", offset=3600).reshape(ntr, tb)
    new = np.empty((ntr, tb_new), dtype="u1")
    new[:, :240] = a[:, :240]
    new[:, 114:116] = np.frombuffer(struct.pack(">H", ns_new), dtype="u1")
    new[:, 240:] = a[:, 240 + 4 * shift:]
    text = bytearray(old[:3200])
    text[12 * 80:13 * 80] = NOTE.ljust(80).encode("cp500")
    binh = bytearray(old[3200:3600])
    binh[20:22] = struct.pack(">H", ns_new)
    OUT.write_bytes(bytes(text) + bytes(binh) + new.tobytes())
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == before
    prov = OUT.parent / "provenance_full.json"
    prov.write_text(json.dumps({"original_sha256": before, "output": str(OUT.relative_to(ROOT)),
                                "output_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
                                "removed_samples": shift, "samples": ns_new}, indent=2))
    print(prov.read_text())


if __name__ == "__main__":
    main()
