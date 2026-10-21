"""v0.22 checks: D1 density, K1 valid count, K2 gap, E2 support by area, W3."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import stack as S                                     # noqa: E402
from sumcp import velocity as V                                  # noqa: E402


def _reports(cdps, valid):
    return [{"cdp": c, "valid": v} for c, v in zip(cdps, valid)]


class Density(unittest.TestCase):
    def test_marmousi_and_viking_spans(self):
        self.assertEqual(S.density_count(411 * 10.0, 5), 9)     # Marmousi2 v2
        self.assertEqual(S.density_count(168 * 12.5, 5), 5)     # Viking: unchanged
        self.assertEqual(S.density_count(40000.0, 5), 15)       # capped
        self.assertEqual(S.density_count(None, 5), 5)           # unknown bin size
        self.assertEqual(S.density_count(1000.0, 7), 7)         # caller asks for more

    def test_selection_spreads_over_the_same_eligible_range(self):
        cdp = np.arange(545, 1141)
        fold = np.full(cdp.size, 24)
        fold[:30] = fold[-30:] = 12
        five, sel5 = S.choose_analysis_locations(cdp, fold, 5)
        nine, sel9 = S.choose_analysis_locations(cdp, fold, 9)
        self.assertEqual((five[0], five[-1]), (nine[0], nine[-1]))
        self.assertEqual(len(nine), 9)
        self.assertEqual(sel5["eligible_range"], sel9["eligible_range"])


class ValidCount(unittest.TestCase):
    def test_table(self):
        self.assertEqual([S.required_valid(n) for n in (1, 2, 3, 4, 5)], [1, 2, 3, 3, 3])
        self.assertEqual([S.required_valid(n) for n in range(6, 11)], [4] * 5)
        self.assertEqual([S.required_valid(n) for n in range(11, 16)], [5] * 5)

    def test_family_wise_rate_never_exceeds_the_sparse_one(self):
        ref = S._binom_tail(5, 3)
        for n in range(6, 16):
            self.assertLessEqual(S._binom_tail(n, S.required_valid(n)), ref + 1e-12)


class Gap(unittest.TestCase):
    CDPS = [637, 688, 740, 791, 843, 894, 945, 997, 1048]

    def test_end_location_failure_is_interpolated_when_dense(self):
        g = S.grade_velocity_locations(_reports(self.CDPS, [1] * 8 + [0]))
        self.assertTrue(g["ok"], g["problems"])

    def test_one_interior_failure_is_interpolated(self):
        # gap 740 -> 843 = 103 cdp; the limit is a quarter span rounded up to a bin
        g = S.grade_velocity_locations(_reports(self.CDPS, [1, 1, 1, 0, 1, 1, 1, 1, 1]))
        self.assertTrue(g["ok"], g["problems"])
        self.assertEqual(g["gap_limit_cdp"], 103)

    def test_two_adjacent_interior_failures_are_too_long_a_gap(self):
        g = S.grade_velocity_locations(_reports(self.CDPS, [1, 1, 1, 0, 0, 1, 1, 1, 1]))
        self.assertFalse(g["ok"])

    def test_long_gap_fails_even_with_enough_valid_and_full_coverage(self):
        g = S.grade_velocity_locations(_reports(self.CDPS, [1, 1, 0, 0, 0, 1, 1, 1, 1]))
        self.assertFalse(g["ok"])
        self.assertTrue(any("K2" in p for p in g["problems"]), g["problems"])

    def test_too_few_valid(self):
        g = S.grade_velocity_locations(_reports(self.CDPS, [1, 0, 0, 1, 0, 0, 1, 0, 0]))
        self.assertFalse(g["ok"])
        self.assertEqual(g["required_valid"], 4)

    def test_sparse_rule_is_unchanged(self):
        cdps = [637, 740, 843, 945, 1048]
        g = S.grade_velocity_locations(_reports(cdps, [1, 0, 0, 1, 1]))
        self.assertTrue(g["ok"])          # three of five, full coverage, no K2
        self.assertNotIn("max_gap_cdp", g)


class AreaSupport(unittest.TestCase):
    def test_interpolates_between_locations_and_holds_beyond(self):
        frac = S.area_support_fraction([0, 5, 10, 15, 20], [5, 15], [1.4, 2.6], 1.4, 2.6)
        # depths 1.4, 1.4, 2.0, 2.6, 2.6 -> fractions 0, 0, .5, 1, 1
        self.assertAlmostEqual(frac, 0.5)

    def test_single_location(self):
        self.assertAlmostEqual(S.area_support_fraction([1, 2], [1], [2.0], 1.4, 2.6), 0.5)


class W3(unittest.TestCase):
    CLEAR = {"level": "CLEAR", "correlation_ceiling": 0.99}

    def test_low_area_fraction_warns_whatever_the_ceiling(self):
        w = S.reliability_warning(self.CLEAR, {"level": "PARTIAL", "measured_fraction": 0.2})
        self.assertEqual(w["level"], "WARN")
        self.assertIn("E2", w["reasons"][0])

    def test_partial_above_a_quarter_with_high_ceiling_is_quiet(self):
        w = S.reliability_warning(self.CLEAR, {"level": "PARTIAL", "measured_fraction": 0.3})
        self.assertEqual(w["level"], "OK")
        self.assertEqual(w["rule"], "v0.30 N0+Q0+N2+W3+W4 / W2")


class NoiseOnlyLine(unittest.TestCase):
    """Nine noise-only CMP gathers must not validate a velocity model."""

    def test_dense_noise_line_does_not_validate(self):
        rng = np.random.default_rng(22)
        offsets = np.linspace(262.0, 3212.0, 48)
        reports = []
        for i, c in enumerate(range(637, 1049, 51)):
            data = rng.standard_normal((48, 700))
            rep = V.analyse_gather(data, offsets, 0.004, 0.0, label=f"noise {c}")
            reports.append({"cdp": c, "valid": rep["valid"]})
        g = S.grade_velocity_locations(reports)
        self.assertEqual(len(reports), 9)
        self.assertFalse(g["ok"])


if __name__ == "__main__":
    unittest.main()
