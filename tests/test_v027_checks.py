"""v0.27 checks: M6 smoothed migration velocity, W4 lateral coverage."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import runner, tools                                   # noqa: E402
from sumcp import migrate as M                                    # noqa: E402
from sumcp import stack as S                                      # noqa: E402

HAVE_SU = runner.find_program("sumigps") is not None


class Smooth(unittest.TestCase):
    def test_one_outlier_is_removed_and_the_trend_kept(self):
        base = [np.full(10, 2000.0 + 50 * i) for i in range(9)]   # lateral trend
        base[4] = base[4] + 600.0                                   # one bad location
        out = M.smooth_locations(base)
        self.assertTrue(np.allclose(out[4], 2250.0))   # 2100, 2150, [2800], 2250, 2300
        self.assertLess(out[0][0], out[8][0])                       # trend survives
        self.assertTrue(all(np.all(o < 2700) for o in out))

    def test_window_is_shifted_inside_the_line(self):
        v = [np.full(3, float(x)) for x in (1, 2, 3, 4, 5, 6, 7)]
        out = [o[0] for o in M.smooth_locations(v)]
        self.assertEqual(out, [3, 3, 3, 4, 5, 5, 5])

    def test_five_or_fewer_share_one_function(self):
        v = [np.full(4, float(x)) for x in (1, 9, 2, 8, 3)]
        out = M.smooth_locations(v)
        self.assertTrue(all(np.array_equal(o, out[0]) for o in out))
        self.assertEqual(out[0][0], 3.0)

    def test_grid_matches_rms_grid(self):
        t = np.arange(0, 1.0, 0.1)
        locs = [{"cdp": 10, "function": [{"t0_s": 0, "v_m_s": 1500.0}, {"t0_s": 1, "v_m_s": 1500.0}]},
                {"cdp": 20, "function": [{"t0_s": 0, "v_m_s": 3000.0}, {"t0_s": 1, "v_m_s": 3000.0}]}]
        a = M.rms_grid(locs, [0, 12, 20, 25], t)
        b = M.grid_from([10, 20], [M.location_rms(l["function"], t) for l in locs], [0, 12, 20, 25])
        self.assertTrue(np.allclose(a, b))

    def test_result_reports_the_migration_velocity(self):
        src = (REPO / "sumcp" / "migrate.py").read_text(encoding="utf-8")
        self.assertIn('{"migration_velocity": ev["migration_velocity"]}', src)

    def test_default_method(self):
        self.assertEqual(M.DEFAULT_METHOD, "phase_shift_smooth")
        self.assertIn("phase_shift", M.METHODS)
        self.assertIn("phase_shift_blend", M.METHODS)
        server = (REPO / "server.py").read_text(encoding="utf-8")
        self.assertIn('method: str = "phase_shift_smooth"', server)


class W4(unittest.TestCase):
    CLEAR = {"level": "CLEAR", "correlation_ceiling": 0.99}

    def test_lateral_fraction(self):
        self.assertAlmostEqual(S.lateral_fraction(np.arange(741, 941), [833, 848]), 16 / 200)
        self.assertAlmostEqual(S.lateral_fraction(np.arange(545, 1141), [637, 1048]), 412 / 596)
        self.assertEqual(S.lateral_fraction(np.arange(10), []), 0.0)

    def test_clustered_locations_warn(self):
        w = S.reliability_warning(self.CLEAR, {"measured_fraction": 0.8, "lateral_fraction": 0.08})
        self.assertEqual(w["level"], "WARN")
        self.assertIn("W4", w["reasons"][0])

    def test_full_line_is_quiet(self):
        w = S.reliability_warning(self.CLEAR, {"measured_fraction": 0.8, "lateral_fraction": 0.69})
        self.assertEqual(w["level"], "OK")


@unittest.skipUnless(HAVE_SU, "SU sumigps not installed")
class SmoothWithFewLocationsIsOneMigration(unittest.TestCase):
    def test_single_migration(self):
        calls = []

        class R:
            def migrate(self, src, vint):
                calls.append(np.asarray(vint).copy())
                return np.zeros((4, 3))
        v = [np.full(3, 2000.0)] * 5
        out = M._migrate(R(), None, "phase_shift_smooth", [{"cdp": c} for c in range(5)],
                         v, None, np.arange(4))
        self.assertEqual(len(calls), 1)
        self.assertEqual(out.shape, (4, 3))


if __name__ == "__main__":
    unittest.main()
