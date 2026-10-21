"""Baseline study 02: keep only one case file in the challenge folder (as study 01, LOG Addendum 2)."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAL = ROOT / "test_dataset" / "Baseline02_challenge"
HOLD = ROOT / "_b02_hold"
FROZEN = {Path(v["file"]).name: v["sha256"] for v in json.loads(
    (ROOT / "results/baseline02/hidden/challenge_set.json").read_text())["cases"].values()}


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
    if len(FROZEN) != 18:
        sys.exit(f"challenge_set.json lists {len(FROZEN)} challenge files, expected 18")
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
        sys.exit(f"{name}: sha256 differs from challenge_set.json; stop and tell the user")
    left = sorted(p.name for p in CHAL.iterdir())
    if left != [name]:
        sys.exit(f"challenge folder holds {left}; expected only {name}")
    print(f"staged {name} (sha256 ok); challenge folder holds only it; {len(list(HOLD.iterdir()))} in _b02_hold/")


if __name__ == "__main__":
    main(sys.argv[1:] or ["--status"])
