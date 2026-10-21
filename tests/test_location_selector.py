"""The representative velocity-analysis location selector (SYSTEM_LIMITATION-001)."""
import unittest

import numpy as np

from sumcp import reflection as R
from sumcp.stack import choose_analysis_locations, grade_velocity_locations


class LocationSelectorTest(unittest.TestCase):

    def test_full_fold_line_is_unchanged_from_the_fixed_margin_rule(self):
        # 200 bins, uniform fold well above the minimum: the fold test removes nothing, so the selection must be
        # exactly what the 5 % margin gave.
        cdp = np.arange(1000, 1200)
        fold = np.full(cdp.size, 58)
        got, sel = choose_analysis_locations(cdp, fold, 5)
        margin = max(1, int(round(0.05 * cdp.size)))
        inner = cdp[margin:cdp.size - margin]
        want = [int(inner[i]) for i in
                np.linspace(0, inner.size - 1, 5).round().astype(int)]
        self.assertEqual(got, want)
        self.assertEqual(sel["basis"], "inner_and_min_fold")
        self.assertEqual(sel["bins_eligible"], inner.size)

    def test_off_end_taper_is_excluded_even_though_the_margin_keeps_it(self):
        # 596 bins with a 95-bin fold ramp at each end, as an off-end spread makes.
        cdp = np.arange(545, 1141)
        taper, full = 95, 24
        up = np.clip(np.round(full * np.arange(1, cdp.size + 1) / taper),
                     1, full).astype(int)
        fold = np.minimum(up, up[::-1])
        got, sel = choose_analysis_locations(cdp, fold, 5)
        self.assertEqual(sel["edge_margin_bins"], 30)
        self.assertGreater(sel["bins_inside_margin"], sel["bins_eligible"])
        for c in got:
            self.assertGreaterEqual(int(fold[cdp == c][0]),
                                    R.MIN_SEMBLANCE_TRACES)
        self.assertTrue(all(f >= R.MIN_SEMBLANCE_TRACES
                            for f in sel["fold_at_selected"]))

    def test_the_minimum_is_the_estimators_own(self):
        cdp = np.arange(0, 100)
        fold = np.full(cdp.size, R.MIN_SEMBLANCE_TRACES - 1)
        fold[40:60] = R.MIN_SEMBLANCE_TRACES
        got, sel = choose_analysis_locations(cdp, fold, 3)
        self.assertEqual(sel["min_fold_required"], R.MIN_SEMBLANCE_TRACES)
        self.assertEqual(sel["min_fold_source"],
                         "reflection.velocity_semblance min_traces")
        self.assertTrue(all(40 <= c < 60 for c in got), got)

    def test_gaps_in_the_eligible_set_are_handled(self):
        cdp = np.arange(0, 120)
        fold = np.full(cdp.size, 30)
        fold[50:60] = 2                       # a dead patch in the middle
        got, sel = choose_analysis_locations(cdp, fold, 5)
        self.assertTrue(all(not (50 <= c < 60) for c in got), got)
        self.assertEqual(sel["bins_eligible"], 120 - 12 - 10)

    def test_no_bin_reaches_the_minimum_falls_back_and_says_so(self):
        cdp = np.arange(0, 40)
        fold = np.full(cdp.size, 3)
        got, sel = choose_analysis_locations(cdp, fold, 3)
        self.assertEqual(sel["basis"], "inner_only_no_bin_reaches_min_fold")
        self.assertEqual(sel["bins_meeting_min_fold"], 0)
        self.assertEqual(len(got), 3)

    def test_only_edge_bins_reach_the_minimum_falls_back_and_says_so(self):
        cdp = np.arange(0, 40)
        fold = np.full(cdp.size, 3)
        fold[0] = fold[-1] = 40
        got, sel = choose_analysis_locations(cdp, fold, 2)
        self.assertEqual(sel["basis"], "min_fold_only_no_inner_bin_qualified")
        self.assertEqual(got, [0, 39])

    def test_fewer_eligible_bins_than_requested_locations(self):
        cdp = np.arange(0, 30)
        fold = np.full(cdp.size, 1)
        fold[14:16] = 25
        got, sel = choose_analysis_locations(cdp, fold, 5)
        self.assertEqual(got, [14, 15])
        self.assertEqual(sel["bins_eligible"], 2)


class LocationGradeTest(unittest.TestCase):

    @staticmethod
    def report(cdp, valid):
        return {"cdp": cdp, "valid": valid,
                "problems": [] if valid else ["unsupported"]}

    def test_internal_failures_are_omitted_when_valid_controls_span_the_line(self):
        reports = [self.report(100, True), self.report(300, False),
                   self.report(500, True), self.report(700, False),
                   self.report(900, True)]
        got = grade_velocity_locations(reports)
        self.assertTrue(got["ok"], got["problems"])
        self.assertEqual([r["cdp"] for r in got["valid"]], [100, 500, 900])
        self.assertEqual(got["coverage_fraction"], 1.0)

    def test_missing_edge_coverage_fails_even_with_three_valid_locations(self):
        reports = [self.report(100, False), self.report(300, True),
                   self.report(500, True), self.report(700, True),
                   self.report(900, False)]
        got = grade_velocity_locations(reports)
        self.assertFalse(got["ok"])
        self.assertLess(got["coverage_fraction"], 0.8)

    def test_fewer_than_three_valid_locations_fails(self):
        reports = [self.report(100, True), self.report(300, False),
                   self.report(500, True), self.report(700, False),
                   self.report(900, False)]
        got = grade_velocity_locations(reports)
        self.assertFalse(got["ok"])
        self.assertEqual(got["required_valid"], 3)


if __name__ == "__main__":
    unittest.main()
