"""v0.24 migration quality against the migrated ER reference (evaluation only)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from run_oracle import agc, reference_match  # noqa: E402


def read_any_su(path):
    raw = np.fromfile(path, dtype="u1")
    for order in ("<", ">"):
        ns = int(np.frombuffer(raw[114:116].tobytes(), dtype=order + "u2")[0])
        stride = 240 + 4 * ns
        if 0 < ns < 100000 and raw.size % stride == 0:
            tr = raw.reshape(-1, stride)
            cdp = tr[:, 20:24].copy().view(order + "i4").ravel()
            data = tr[:, 240:].copy().view(order + "f4").reshape(-1, ns).astype(float)
            return cdp, data
    raise ValueError(f"cannot read {path}")


def q(path, ref):
    cdp, data = read_any_su(path)
    live = (np.linalg.norm(data[:, 340:710], axis=1) > 0) & (np.linalg.norm(data[:, 690:1210], axis=1) > 0)  # dead (muted) traces carry no correlation
    cdp, data = cdp[live], data[live]
    m = reference_match(data, cdp, ref, 0)
    return {"best_lag": m["0.7-2.4s"]["best_lag_pm20ms"], "zero_lag": m["0.7-2.4s"]["zero_lag"],
            "windows": {k: v for k, v in m.items() if k != "traces"}}


def main():
    img = np.load(sys.argv[2])["section"].astype(float)
    ref = {"agc": agc(img)}
    out = {"reference": sys.argv[2], "unmigrated": q(sys.argv[3], ref)}
    for p in sys.argv[4:]:
        out[Path(p).name] = q(p, ref)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
