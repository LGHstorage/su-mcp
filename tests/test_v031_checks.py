"""v0.31 checks: M7 time smoothing, M8 stability windows, Z5 depth step, B1 bookkeeping."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import depth as Z                                      # noqa: E402
from sumcp import evidence                                        # noqa: E402
from sumcp import migrate as M                                    # noqa: E402


def _loc(cdp, pairs):
    return {"cdp": cdp, "function": [{"t0_s": a, "v_m_s": b} for a, b in pairs]}


class M7(unittest.TestCase):
    def test_spacing_and_smoothing(self):
        f = _loc(1, [(0, 1500), (0.5, 2000), (1.0, 2000), (1.5, 3500)])["function"]
        self.assertAlmostEqual(M.knot_spacing(f), 0.5)
        t = np.arange(0, 2.0, 0.004)
        v = M.location_rms(f, t)
        s = M.time_smooth(v, 0.5, 0.004)
        self.assertEqual(s.shape, v.shape)
        self.assertLess(np.abs(np.diff(M.dix(s, 0.004))).max(), np.abs(np.diff(M.dix(v, 0.004))).max())
        self.assertTrue(np.allclose(M.time_smooth(np.full(100, 2000.0), 0.5, 0.004), 2000.0))

    def test_m7_velocities_keeps_a_constant_model(self):
        t = np.arange(0, 2.0, 0.004)
        locs = [_loc(c, [(0, 2000), (1, 2000), (2, 2000)]) for c in (10, 20, 30)]
        for v in M.m7_velocities(locs, t, 0.004):
            self.assertTrue(np.allclose(v, 2000.0))


class M8(unittest.TestCase):
    def test_windows(self):
        t = np.arange(0, 3.0, 0.004)
        rng = np.random.default_rng(1)
        mig = rng.standard_normal((50, t.size))
        good = mig + 0.05 * rng.standard_normal(mig.shape)
        bad = mig.copy()
        bad[:, t >= 2.0] = rng.standard_normal((50, int((t >= 2.0).sum())))
        w = M.stability_windows(mig, [good, bad], t, 0.5)
        self.assertEqual([x["from_s"] for x in w], [0.5, 1.5, 2.5])
        self.assertGreater(w[0]["stability"], 0.9)
        self.assertLess(w[2]["stability"], 0.2)


class Z5(unittest.TestCase):
    def test_depth_step(self):
        self.assertEqual(Z.depth_step(1450.0, 5.8), 5.0)        # Marmousi2 keeps 5 m
        self.assertEqual(Z.depth_step(1480.0, 52.8), 3.0)       # Viking: floor(3.5)
        self.assertEqual(Z.depth_step(1480.0, 400.0), 1.0)      # never below 1 m
        self.assertEqual(Z.depth_step(None, 10.0), 5.0)


class B1(unittest.TestCase):
    def test_rejected_run_keeps_a_released_product(self):
        m = {"capabilities": {}, "history": []}
        evidence.record_product_run(m, "migration.completed", True, {"method": "phase_shift_smooth"},
                                    "x", "r1", artifact="results/a.su")
        evidence.record_product_run(m, "migration.completed", False, {"method": "phase_shift"},
                                    "x", "r2", artifact="work/b.su")
        cap = m["capabilities"]["migration.completed"]
        self.assertEqual(cap["status"], "PASS")
        self.assertEqual(cap["artifact"], "results/a.su")
        self.assertEqual([a["released"] for a in cap["attempts"]], [True, False])

    def test_first_rejection_is_a_fail(self):
        m = {"capabilities": {}, "history": []}
        evidence.record_product_run(m, "depth.completed", False, {"method": "depth_pspi"}, "x", "r1")
        self.assertEqual(m["capabilities"]["depth.completed"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
