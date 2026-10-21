"""One leverage formula, checked at both of its callers."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import geometry, leverage as LEV, reflection as R   # noqa: E402

DT = 0.004


class ApertureTest(unittest.TestCase):
    def test_one_offset_has_no_aperture(self):
        ap = LEV.aperture(np.full(60, 2000.0))
        self.assertEqual(ap["offset_min_m"], ap["offset_max_m"])
        self.assertEqual(ap["offset_squared_span_m2"], 0.0)
        self.assertEqual(ap["distinct_offsets"], 1)
        self.assertEqual(ap["traces"], 60)

    def test_the_sign_of_the_offset_header_does_not_matter(self):
        a = LEV.aperture(np.linspace(-3212.0, -262.0, 60))
        b = LEV.aperture(np.linspace(262.0, 3212.0, 60))
        self.assertEqual(a["offset_min_m"], b["offset_min_m"])
        self.assertEqual(a["offset_max_m"], b["offset_max_m"])

    def test_robust_ends_are_reported_beside_the_exact_ones(self):
        x = np.concatenate([np.linspace(300.0, 400.0, 99), [9000.0]])
        ap = LEV.aperture(x)
        self.assertEqual(ap["offset_max_m"], 9000.0)
        self.assertLess(ap["offset_robust_hi_m"], 1000.0)


class SingleHyperbolaTest(unittest.TestCase):
    """What a CMP bin is graded on."""

    def test_sixty_traces_at_one_offset_have_no_leverage(self):
        got = LEV.hyperbola_leverage(np.full(60, 2000.0), 1800.0, 1.0, DT)
        self.assertEqual(got["status"], LEV.NONE)
        self.assertEqual(got["moveout_spread_ms"], 0.0)
        self.assertIn("effectively one moveout", got["reason"])

    def test_a_ten_metre_band_at_two_kilometres_is_not_usable(self):
        got = LEV.hyperbola_leverage(np.linspace(2000.0, 2010.0, 24),
                                     1800.0, 1.0, DT)
        self.assertIn(got["status"], (LEV.NONE, LEV.MARGINAL))
        self.assertLess(got["moveout_spread_ms"], LEV.MARGINAL_BELOW_MS)

    def test_a_viking_cmp_gather_is_usable(self):
        got = LEV.hyperbola_leverage(np.linspace(262.0, 3212.0, 60),
                                     1800.0, 1.0, DT)
        self.assertEqual(got["status"], LEV.USABLE)
        self.assertAlmostEqual(got["moveout_spread_ms"], 1035.0, delta=1.0)

    def test_the_A02_aperture_reproduces_its_recorded_leverage(self):
        """A02 was graded at 0.48 ms in round 1; the refactor must not move it."""
        got = LEV.hyperbola_leverage(np.linspace(100.0, 114.5, 30),
                                     1800.0, 1.0, DT)
        self.assertEqual(got["status"], LEV.NONE)
        self.assertAlmostEqual(got["moveout_spread_ms"], 0.48, delta=0.02)


class VelocityAxisTest(unittest.TestCase):
    """What the feasibility guard is graded on."""

    def test_sixty_traces_at_one_offset_cannot_resolve_a_velocity(self):
        """The defect. Under the old formula this passed because 2000 is big."""
        got = LEV.velocity_axis_leverage(np.full(60, 2000.0), DT, 0.05,
                                         1350.0, 3150.0)
        self.assertFalse(got["resolvable"])
        self.assertEqual(got["moveout_spread_ms"], 0.0)
        self.assertIn("every trace sits at", got["reason"])

    def test_a_ten_metre_band_at_two_kilometres_cannot_either(self):
        got = LEV.velocity_axis_leverage(np.linspace(2000.0, 2010.0, 200), DT,
                                         0.05, 1350.0, 3150.0)
        self.assertFalse(got["resolvable"])

    def test_a_viking_gather_can(self):
        got = LEV.velocity_axis_leverage(np.linspace(262.0, 3212.0, 60), DT,
                                         0.05, 1350.0, 3150.0)
        self.assertTrue(got["resolvable"])
        self.assertGreater(got["moveout_spread_samples"],
                           LEV.MIN_VELOCITY_LEVERAGE_SAMPLES)

    def test_a_zero_offset_section_still_cannot(self):
        """The Marmousi2 case the guard was built for."""
        got = LEV.velocity_axis_leverage(np.zeros(200), DT, 0.05, 1350.0, 3150.0)
        self.assertFalse(got["resolvable"])

    def test_the_A02_aperture_cannot_resolve_a_velocity(self):
        """A consequence of the fix, recorded here so it is not a surprise."""
        got = LEV.velocity_axis_leverage(np.linspace(100.0, 114.5, 30), DT,
                                         0.05, 1350.0, 3150.0)
        self.assertFalse(got["resolvable"])
        self.assertLess(got["moveout_spread_samples"],
                        LEV.MIN_VELOCITY_LEVERAGE_SAMPLES)


class OneFormulaTest(unittest.TestCase):
    """The two callers must not drift apart again."""

    def test_the_cmp_gate_delegates_to_the_shared_function(self):
        for lo, hi, v, t0 in ((262.0, 3212.0, 1800.0, 1.0),
                              (100.0, 114.5, 1800.0, 1.0),
                              (2000.0, 2010.0, 1500.0, 2.0)):
            self.assertAlmostEqual(geometry._moveout_spread_s(lo, hi, v, t0),
                                   LEV.moveout_spread_s(lo, hi, v, t0),
                                   places=12)

    def test_the_feasibility_guard_delegates_to_the_shared_function(self):
        offsets = np.linspace(262.0, 3212.0, 60)
        direct = LEV.velocity_axis_leverage(offsets, DT, 0.05, 1350.0, 3150.0)
        through = R.velocity_leverage(offsets, DT,
                                      np.arange(0.05, 2.0, 0.02),
                                      np.arange(1350.0, 3200.0, 50.0))
        self.assertEqual(direct["moveout_spread_ms"],
                         through["moveout_spread_ms"])
        self.assertEqual(direct["resolvable"], through["resolvable"])

    def test_both_forms_report_the_same_aperture_fields(self):
        offsets = np.linspace(262.0, 3212.0, 60)
        a = LEV.hyperbola_leverage(offsets, 1800.0, 1.0, DT)
        b = LEV.velocity_axis_leverage(offsets, DT, 0.05, 1350.0, 3150.0)
        for key in ("offset_min_m", "offset_max_m", "offset_squared_span_m2",
                    "moveout_spread_ms", "moveout_spread_samples"):
            self.assertIn(key, a)
            self.assertIn(key, b)

    def test_the_thresholds_are_the_existing_ones(self):
        self.assertEqual(LEV.NONE_BELOW_MS, 2.0)
        self.assertEqual(LEV.MARGINAL_BELOW_MS, 20.0)
        self.assertEqual(LEV.MIN_VELOCITY_LEVERAGE_SAMPLES, 2.0)
        self.assertEqual(R.MIN_VELOCITY_LEVERAGE_SAMPLES,
                         LEV.MIN_VELOCITY_LEVERAGE_SAMPLES)


class FoldIsNotLeverageTest(unittest.TestCase):
    def test_fold_sixty_at_one_offset_is_still_NONE(self):
        """The headline: counting traces is not measuring leverage."""
        many = LEV.hyperbola_leverage(np.full(60, 2000.0), 1800.0, 1.0, DT)
        few = LEV.hyperbola_leverage(np.full(4, 2000.0), 1800.0, 1.0, DT)
        self.assertEqual(many["status"], LEV.NONE)
        self.assertEqual(few["status"], LEV.NONE)
        self.assertEqual(many["moveout_spread_ms"], few["moveout_spread_ms"])


if __name__ == "__main__":
    unittest.main()
