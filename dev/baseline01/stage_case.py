"""Baseline study 01, LOG Addendum 2: keep only one case file in the challenge folder."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAL = ROOT / "test_dataset" / "Baseline01_challenge"
HOLD = ROOT / "_b01_hold"
FROZEN = {Path(k).name: v for group in json.loads((ROOT / "results/baseline01/FREEZE.json").read_text())
          ["files"].values() for k, v in group.items() if k.startswith("test_dataset/Baseline01_challenge/")}


def where():
    return {n: ("challenge" if (CHAL / n).exists() else "hold" if (HOLD / n).exists() else "MISSING")
            for n in sorted(FROZEN)}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main(argv):
    if len(FROZEN) != 12:
        sys.exit(f"FREEZE.json lists {len(FROZEN)} challenge files, expected 12")
    if argv[:1] == ["--status"]:
        print(json.dumps(where(), indent=1))
        return
    name = argv[0] if argv[0].endswith(".sgy") else f"{argv[0]}.sgy"
    if not name.startswith("case_"):
        name = "case_" + name
    if name not in FROZEN:
        sys.exit(f"{name} is not a challenge case")
    HOLD.mkdir(exist_ok=True)
    for n, loc in where().items():
        if loc == "MISSING":
            sys.exit(f"{n} is in neither folder; stop and tell the user")
        if n != name and loc == "challenge":
            (CHAL / n).rename(HOLD / n)
        if n == name and loc == "hold":
            (HOLD / n).rename(CHAL / n)
    if sha(CHAL / name) != FROZEN[name]:
        sys.exit(f"{name}: sha256 differs from FREEZE.json; stop and tell the user")
    left = sorted(p.name for p in CHAL.iterdir())
    if left != [name]:
        sys.exit(f"challenge folder holds {left}; expected only {name}")
    print(f"staged {name} (sha256 ok); challenge folder holds only it; {len(list(HOLD.iterdir()))} in _b01_hold/")


if __name__ == "__main__":
    main(sys.argv[1:] or ["--status"])
