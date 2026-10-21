"""Stacking velocity: the picking constraint and the checks on the result."""

from __future__ import annotations

import os
import tempfile
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
# Every tool call writes an audit entry now, so the suite gets its own log: test runs in logs/processing.jsonl
# would corrupt the record the adversarial suite reads to decide whether a forbidden program ran.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))


from sumcp import velocity as V   # noqa: E402

DT, NS = 0.004, 1500


def _cmp_gather(v_of_t=((0.0, 1500.0), (3.0, 2200.0), (5.9, 2800.0)),
                depths=(0.4, 1.1, 2.0, 3.2, 4.5), noise=0.05, seed=0,
                ntr=60, f0=25.0):
    """A CMP gather with hyperbolic reflections on a known velocity trend."""
    rng = np.random.default_rng(seed)
    offsets = np.linspace(262.0, 3212.0, ntr)
    t = np.arange(NS) * DT
    times, vels = zip(*v_of_t)
    data = np.zeros((ntr, NS))
    for t_zero in depths:
        v = float(np.interp(t_zero, times, vels))
        for i, x in enumerate(offsets):
            tc = np.sqrt(t_zero ** 2 + (x / v) ** 2)
            a = (t - tc) * np.pi * f0
            data[i] += (1 - 2 * a ** 2) * np.exp(-a ** 2)
    data += noise * rng.standard_normal(data.shape)
    return data, offsets


class ConstrainedPickTest(unittest.TestCase):

    def test_the_path_never_decreases(self):
        rng = np.random.default_rng(1)
        t0_grid = np.arange(0.1, 4.0, 0.04)
        v_grid = np.arange(1400.0, 5000.0, 50.0)
        panel = rng.random((t0_grid.size, v_grid.size))
        picked = V.pick_constrained(panel, t0_grid, v_grid)
        v = [p["v_m_s"] for p in picked]
        self.assertTrue(all(b >= a for a, b in zip(v, v[1:])))

    def test_the_rate_limit_is_respected(self):
        t0_grid = np.arange(0.0, 2.0, 0.04)
        v_grid = np.arange(1400.0, 5000.0, 50.0)
        panel = np.zeros((t0_grid.size, v_grid.size))
        panel[0, 0] = 1.0            # a peak at the slowest velocity...
        panel[1, -1] = 1.0           # ...and the fastest, one step later
        picked = V.pick_constrained(panel, t0_grid, v_grid, max_rate_m_s2=2500.0)
        jump = picked[1]["v_m_s"] - picked[0]["v_m_s"]
        self.assertLessEqual(jump, 2500.0 * 0.04 + 50.0)

    def test_it_recovers_a_planted_velocity_trend(self):
        data, offsets = _cmp_gather()
        got = V.analyse_gather(data, offsets, DT, 0.0, label="synthetic")
        self.assertTrue(got["valid"], got["problems"])
        at_2s = [p for p in got["function"] if abs(p["t0_s"] - 2.0) < 0.5]
        self.assertTrue(at_2s)
        # the planted trend passes ~1850 m/s at 2 s
        self.assertLess(abs(at_2s[0]["v_m_s"] - 1850.0), 400.0)


class DixTest(unittest.TestCase):
    """The check that uses the picks jointly, and so catches functions that are individually plausible and
    physically impossible."""

    def test_a_falling_rms_velocity_gives_an_imaginary_interval(self):
        function = [{"t0_s": 1.0, "v_m_s": 2500.0, "semblance": 0.5},
                    {"t0_s": 1.5, "v_m_s": 1800.0, "semblance": 0.5}]
        interval = V.dix_interval(function)[0]
        self.assertFalse(interval["physical"])
        self.assertIsNone(interval["v_interval_m_s"])

    def test_a_normal_trend_gives_sensible_intervals(self):
        function = [{"t0_s": 0.5, "v_m_s": 1600.0, "semblance": 0.5},
                    {"t0_s": 1.5, "v_m_s": 1900.0, "semblance": 0.5},
                    {"t0_s": 2.5, "v_m_s": 2200.0, "semblance": 0.5}]
        for interval in V.dix_interval(function):
            self.assertTrue(interval["physical"])
            self.assertTrue(1400 < interval["v_interval_m_s"] < 4000)

    def test_dix_is_only_judged_where_the_velocity_was_measured(self):
        """Below the deepest supported pick the function is held constant, so testing its intervals would be
        testing the assumption."""
        function = [{"t0_s": 1.0, "v_m_s": 1800.0, "semblance": 0.9},
                    {"t0_s": 2.0, "v_m_s": 2000.0, "semblance": 0.9},
                    {"t0_s": 3.0, "v_m_s": 2100.0, "semblance": 0.9},
                    {"t0_s": 3.5, "v_m_s": 6000.0, "semblance": 0.001}]
        report = V.validate(function, 0.1, 6.0)
        self.assertFalse(any("interval velocity" in p for p in report["problems"]),
                         report["problems"])


class HoldBelowSupportTest(unittest.TestCase):

    def test_unsupported_picks_are_held_not_extrapolated_upward(self):
        function = [{"t0_s": 1.0, "v_m_s": 1800.0, "semblance": 0.9},
                    {"t0_s": 2.0, "v_m_s": 2100.0, "semblance": 0.9},
                    {"t0_s": 3.0, "v_m_s": 2600.0, "semblance": 0.01},
                    {"t0_s": 4.0, "v_m_s": 3400.0, "semblance": 0.01}]
        held, depth = V.hold_below_support(function, 0.1)
        self.assertEqual(depth, 2.0)
        self.assertEqual([p["v_m_s"] for p in held],
                         [1800.0, 2100.0, 2100.0, 2100.0])
        self.assertTrue(all(p.get("held") for p in held[2:]))


class NoTrendTest(unittest.TestCase):
    """The answer that matters most: there was nothing here to pick."""

    def test_support_is_read_from_the_dense_path_not_the_control_points(self):
        """Control points sit on a regular time grid so Dix is conditioned; reflections do not."""
        path = [{"t0_s": i * 0.04, "v_m_s": 1800.0,
                 "semblance": 0.9 if i % 25 == 0 else 0.01}
                for i in range(150)]
        self.assertGreaterEqual(V.support(path, 0.1)["points"], 5)
        points = V.thin(path, n_points=10)
        on_grid = sum(p["semblance"] > 0.1 for p in points)
        self.assertLess(on_grid, 5)

    def test_pure_noise_is_not_a_velocity(self):
        rng = np.random.default_rng(7)
        data = rng.standard_normal((60, NS))
        offsets = np.linspace(262.0, 3212.0, 60)
        got = V.analyse_gather(data, offsets, DT, 0.0, label="noise")
        self.assertFalse(got["valid"])
        self.assertFalse(got["path_test"]["significant"])
        self.assertGreater(got["path_test"]["p_value"],
                           got["path_test"]["alpha"])
        self.assertTrue(any("constraint talking" in p for p in got["problems"]),
                        got["problems"])

    def test_control_points_are_evenly_spaced_so_dix_is_conditioned(self):
        """Clustering control points around a velocity step made the Dix check fire on the thinning rather than
        on the data."""
        path = [{"t0_s": i * 0.04, "v_m_s": 1500.0 + 400.0 * (i > 40),
                 "semblance": 0.5} for i in range(150)]
        points = V.thin(path, n_points=10)
        gaps = np.diff([p["t0_s"] for p in points])
        self.assertGreaterEqual(gaps.min(), 0.24)
        self.assertLess(gaps.std() / gaps.mean(), 0.2)


if __name__ == "__main__":
    unittest.main()
