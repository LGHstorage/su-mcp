"""Write a time-zero-corrected copy of the Marmousi2 benchmark (0-2.6 s)."""
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
TEMPLATE = ROOT / "test_dataset/Marm2_matched_pair/marm2_original_2p6s.sgy"
OUT = ROOT / "test_dataset/Marm2_time_corrected/marm2_t0fix_2p6s.sgy"
NOTE = "C13 TIME ZERO CORRECTED: 150 MS RICKER ONSET DELAY REMOVED; 0-2.6 S COPY"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; not overwriting")
    before = sha(ORIGINAL)
    shift = int(round(SOURCE_DELAY_S / DT_S))
    old = ORIGINAL.read_bytes()
    tmpl = TEMPLATE.read_bytes()
    ns_old = struct.unpack(">H", old[3220:3222])[0]
    ns_new = struct.unpack(">H", tmpl[3220:3222])[0]
    tb_old, tb_new = 240 + 4 * ns_old, 240 + 4 * ns_new
    ntr = (len(old) - 3600) // tb_old
    if ntr != (len(tmpl) - 3600) // tb_new or shift + ns_new > ns_old:
        raise ValueError("trace count or length mismatch")
    a_old = np.frombuffer(old, dtype="u1", offset=3600).reshape(ntr, tb_old)
    a_new = np.frombuffer(tmpl, dtype="u1", offset=3600).reshape(ntr, tb_new).copy()
    if not np.array_equal(a_old[:, :240][:, :100], a_new[:, :240][:, :100]):
        raise ValueError("template headers do not match the original trace order")
    a_new[:, 240:] = a_old[:, 240 + 4 * shift: 240 + 4 * (shift + ns_new)]
    text = bytearray(tmpl[:3200])
    line = NOTE.ljust(80).encode("cp500")
    text[12 * 80:13 * 80] = line
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(text) + tmpl[3200:3600] + a_new.tobytes())
    if sha(ORIGINAL) != before:
        raise RuntimeError("original changed")
    info = {"original": str(ORIGINAL.relative_to(ROOT)), "original_sha256": before,
            "template": str(TEMPLATE.relative_to(ROOT)),
            "output": str(OUT.relative_to(ROOT)), "output_sha256": sha(OUT),
            "removed_delay_s": SOURCE_DELAY_S, "removed_samples": shift,
            "samples": ns_new, "traces": int(ntr)}
    (OUT.parent / "provenance.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
