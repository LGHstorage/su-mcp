"""Baseline study 01: replace the 3200-byte textual header of every case file with a neutral one (pre-freeze log
item 9)."""
import codecs, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "test_dataset/Baseline01_challenge"
OUT = ROOT / "results/baseline01/hidden/header_neutralization.json"
assert not OUT.exists(), "already neutralised"
lines = ["C 1 2D SEISMIC LINE, SEG-Y", "C 2 DATA SAMPLE FORMAT: IEEE FLOAT (BINARY HEADER)",
         "C 3 SAMPLE INTERVAL AND LENGTH: SEE BINARY HEADER"] + [f"C{i:2d}" for i in range(4, 40)] + ["C40 END TEXTUAL HEADER"]
text = "".join(l.ljust(80)[:80] for l in lines)
assert len(text) == 3200
block = codecs.encode(text, "cp500")
rec = {}
for f in sorted(D.glob("case_*.sgy")):
    old = hashlib.sha256(f.read_bytes()).hexdigest()
    with open(f, "r+b") as fh:
        fh.seek(0)
        fh.write(block)
    new = hashlib.sha256(f.read_bytes()).hexdigest()
    rec[f.name] = {"sha256_before": old, "sha256_after": new}
OUT.write_text(json.dumps({"textual_header": text, "files": rec}, indent=1))
print(len(rec), "files")
