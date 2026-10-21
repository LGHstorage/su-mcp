"""v0.30 evaluation B: the production Q0 rule on raw SEG-Y files (evaluation only)."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sumcp.sanity import trace_stats, corrupt_mask


def ibm2ieee(u):
    u = u.astype(np.uint32)
    sign = np.where(u >> 31, -1.0, 1.0)
    exp = ((u >> 24) & 0x7F).astype(np.int32) - 64
    frac = (u & 0x00FFFFFF).astype(np.float64) / float(1 << 24)
    return sign * frac * np.power(16.0, exp)


def stats(path, block=4000):
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    fmt = int.from_bytes(raw[3224:3226].tobytes(), "big")
    ns = int.from_bytes(raw[3220:3222].tobytes(), "big")
    tb = 240 + 4 * ns
    ntr = (raw.size - 3600) // tb
    tr = raw[3600:3600 + ntr * tb].reshape(ntr, tb)
    R, MX, NF, CDP = [], [], [], []
    for a in range(0, ntr, block):
        blk = np.asarray(tr[a:a + block])
        s = blk[:, 240:].copy().view(">u4")
        d = ibm2ieee(s) if fmt == 1 else s.view(">f4").astype(np.float64)
        r, m, n = trace_stats(d)
        R.append(r); MX.append(m); NF.append(n); CDP.append(blk[:, 20:24].copy().view(">i4").ravel())
    return np.concatenate(R), np.concatenate(MX), np.concatenate(NF), np.concatenate(CDP), fmt


for p in sys.argv[1:]:
    r, m, n, c, fmt = stats(p)
    bad, scale, limit = corrupt_mask(r, m, n)
    clean_ratio = float(m[~bad].max() / scale) if scale > 0 else None
    print(Path(p).name, "fmt", fmt, "traces", r.size, "corrupt", int(bad.sum()), "cdp", sorted(set(c[bad].tolist()))[:10],
          "max clean/median-rms %.1f" % clean_ratio, "max corrupt %.3g" % (m[bad].max() if bad.any() else 0), flush=True)
