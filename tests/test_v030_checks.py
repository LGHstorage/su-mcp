"""v0.30 checks: Q0 corrupt samples, kill_corrupt (K0), N0 non-finite measurements."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import conditioning as K                               # noqa: E402
from sumcp import iterate as I                                    # noqa: E402
from sumcp import migrate as M                                    # noqa: E402
from sumcp import sanity as Q                                     # noqa: E402
from sumcp import stack as S                                      # noqa: E402
from sumcp import sufile                                          # noqa: E402

FLT_MAX = np.finfo(np.float32).max


def _file(path, ntr=400, ns=250, bad=(), order=">"):
    rng = np.random.default_rng(30)
    data = (1e7 * rng.standard_normal((ntr, ns))).astype(np.float32)
    for i, v in bad:
        data[i, ns // 2] = v
    hdr = np.zeros((ntr, 60), dtype=order + "i4")
    h16 = hdr.view(order + "i2")
    hdr[:, 0] = np.arange(1, ntr + 1)
    hdr[:, 5] = np.repeat(np.arange(1, ntr // 20 + 1), 20)[:ntr]
    h16[:, 57] = ns
    h16[:, 58] = 4000
    path.write_bytes(np.concatenate([hdr.view("u1"), data.astype(order + "f4").view("u1")], axis=1).tobytes())
    return data


class Q0(unittest.TestCase):
    def test_flags_the_clamped_overflow_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.su"
            _file(p, bad=[(137, FLT_MAX)])
            r = Q.scan(p)
        self.assertEqual(r["corrupt_count"], 1)
        self.assertEqual(r["corrupt_traces"], [137])
        self.assertEqual(r["corrupt_cdps"], [7])

    def test_nan_and_inf_are_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.su"
            _file(p, bad=[(3, np.nan), (5, np.inf)], order="<")
            self.assertEqual(Q.scan(p)["corrupt_traces"], [3, 5])

    def test_a_clean_file_and_a_strong_but_real_event_are_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.su"
            _file(p, bad=[(10, 1e7 * 1e4)])          # 80 dB above the RMS: loud, not corrupt
            r = Q.scan(p)
        self.assertEqual(r["corrupt_count"], 0)


class Kill(unittest.TestCase):
    def test_only_the_corrupt_trace_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dst = tmp / "a.su", tmp / "b.su"
            _file(src, bad=[(137, FLT_MAX)])
            geom = sufile.geometry(src)
            ok, qc, chain, _ = I._kill_pass(src, dst, geom)
            a = np.fromfile(src, np.uint8).reshape(geom["ntr"], -1)
            b = np.fromfile(dst, np.uint8).reshape(geom["ntr"], -1)
        self.assertTrue(ok, qc)
        self.assertEqual(qc["killed_traces"], 1)
        keep = np.ones(geom["ntr"], bool); keep[137] = False
        self.assertTrue(np.array_equal(a[keep], b[keep]))
        self.assertTrue(np.array_equal(a[137, :240], b[137, :240]))      # header kept
        self.assertFalse(b[137, 240:].any())

    def test_more_than_one_percent_is_not_a_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dst = tmp / "a.su", tmp / "b.su"
            _file(src, bad=[(i, FLT_MAX) for i in range(0, 400, 50)])    # 8 of 400 = 2%
            ok, qc, _, _ = I._kill_pass(src, dst, sufile.geometry(src))
        self.assertFalse(ok)
        self.assertIn("1%", qc["reason"])

    def test_registry(self):
        self.assertIn("kill_corrupt", K.REGISTRY)
        self.assertIn("kill_corrupt", K.SOLO_OPERATIONS)
        with self.assertRaises(ValueError):
            K.REGISTRY["kill_corrupt"]["build"]({"x": 1}, {})


class N0(unittest.TestCase):
    CLEAR = {"level": "CLEAR", "correlation_ceiling": 0.99}

    def test_unmeasurable_sn_is_a_warning(self):
        w = S.reliability_warning({"status": "UNMEASURABLE"}, {"measured_fraction": 0.9})
        self.assertEqual(w["level"], "WARN")
        self.assertIn("N0", w["reasons"][0])

    def test_corrupt_stack_is_a_warning(self):
        w = S.reliability_warning(self.CLEAR, {"measured_fraction": 0.9},
                                  sample_check={"corrupt_count": 1, "corrupt_cdps": [713]})
        self.assertEqual(w["level"], "WARN")
        self.assertIn("kill_corrupt", w["reasons"][0])

    def test_m2_never_nan(self):
        a = np.ones((4, 10)); b = np.ones((4, 10)); b[1, 3] = np.inf
        self.assertEqual(M._median_trace_corr(a, b, 0), 1.0)

    def test_migration_refuses_a_corrupt_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.su"
            _file(p, bad=[(20, FLT_MAX)])
            with self.assertRaises(ValueError):
                M._refuse_corrupt(p, sufile.geometry(p))
            q = Path(tmp) / "t.su"
            _file(q)
            M._refuse_corrupt(q, sufile.geometry(q))           # clean: no exception


if __name__ == "__main__":
    unittest.main()
