"""Geometry that comes from outside the file, and the doubt that follows it."""

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


from sumcp import claims as C          # noqa: E402
from sumcp import external as X        # noqa: E402


class ShotpointMappingTest(unittest.TestCase):
    """The mapping from field record to shotpoint is the first gate, and it is not arithmetic."""

    def test_counting_is_refused(self):
        got = X.shotpoint_mapping(range(1, 156))
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertIn("cannot be counted", got["reason"])
        self.assertIn("observer log", got["what_would_answer_it"])

    def test_the_line_32_case_by_name(self):
        """155 records over a nominal 160 shotpoints: five are missing and nobody knows where, so every
        arithmetic mapping is wrong somewhere."""
        got = X.shotpoint_mapping(range(1, 156))
        self.assertNotIn("mapping", got)

    def test_pairs_from_the_log_resolve_it(self):
        pairs = [(r, 6214 - r) for r in range(1, 156, 10)] + [(155, 6059)]
        got = X.shotpoint_mapping(range(1, 156), pairs)
        self.assertEqual(got["verdict"], X.RESOLVED)
        self.assertEqual(got["mapping"][1], 6213)
        self.assertEqual(got["mapping"][155], 6059)
        self.assertEqual(got["claim"]["origin"], C.ORIGIN_ACQUISITION_LOG)

    def test_a_record_outside_the_listed_pairs_is_left_unmapped(self):
        pairs = [(10, 6204), (20, 6194)]
        got = X.shotpoint_mapping([5, 10, 15, 20, 25], pairs)
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertIn(5, got["records_unmapped"])
        self.assertIn(25, got["records_unmapped"])
        self.assertEqual(got["mapping"][15], 6199)

    def test_an_inconsistent_step_stops_the_filling_in(self):
        """If the log's own pairs do not agree on a step, the gaps between them cannot be filled at that step."""
        got = X.shotpoint_mapping(
            range(1, 31), [(1, 100), (10, 109), (20, 140), (30, 150)])
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertFalse(got["step_consistent"])


class NavigationTest(unittest.TestCase):

    def test_positions_are_interpolated_along_the_track_not_in_xy(self):
        """A turn must not shorten the path: interpolating x and y separately cuts the corner, arc length does
        not."""
        sp = np.array([0, 10, 20], float)
        x = np.array([0.0, 1000.0, 1000.0])
        y = np.array([0.0, 0.0, 1000.0])
        got = X.interpolate_track(sp, x, y, [10])
        self.assertAlmostEqual(got["x"][0], 1000.0, delta=1.0)
        self.assertAlmostEqual(got["y"][0], 0.0, delta=1.0)
        self.assertAlmostEqual(got["track_length_m"], 2000.0, delta=1.0)

    def test_the_claim_says_it_was_interpolated_and_how_far_apart(self):
        sp = np.arange(0, 101, 10).astype(float)
        got = X.interpolate_track(sp, sp * 50.0, sp * 0.0, [5, 15])
        claim = got["position"]
        self.assertEqual(claim["origin"], C.ORIGIN_NAVIGATION)
        # DERIVED, not OBSERVED: nobody recorded a fix at this shotpoint.
        self.assertEqual(claim["class"], C.DERIVED)
        self.assertEqual(claim["fix_interval_shotpoints"], 10.0)
        self.assertIn("along-track", claim["interpolation"])

    def test_shotpoints_outside_the_navigation_are_flagged(self):
        sp = np.array([10.0, 20.0])
        got = X.interpolate_track(sp, [0.0, 500.0], [0.0, 0.0], [5, 15, 25])
        self.assertEqual(got["n_outside"], 2)


class ReceiverPlacementTest(unittest.TestCase):

    def test_receivers_trail_the_source_along_the_track(self):
        got = X.receiver_positions(1000.0, 0.0, [425.0, 3970.0],
                                   tangent=[1.0, 0.0])
        np.testing.assert_allclose(got["gx"], [575.0, -2970.0])
        np.testing.assert_allclose(got["gy"], [0.0, 0.0])

    def test_the_result_is_called_nominal_not_measured(self):
        got = X.receiver_positions(0.0, 0.0, [425.0], tangent=[0.0, 1.0])
        self.assertIn("nominal", got["geometry_type"])
        self.assertEqual(got["not"], "true receiver position")
        self.assertIn("feathering", got["assumption"])

    def test_the_offsets_are_acquisition_log_authority_not_measured(self):
        got = X.receiver_positions(0.0, 0.0, [425.0], tangent=[1.0, 0.0])
        self.assertEqual(got["claim"]["origin"], C.ORIGIN_ACQUISITION_LOG)
        self.assertEqual(got["claim"]["class"], C.ASSUMED)


class DirectArrivalTest(unittest.TestCase):
    """The test an assignment cannot pass by accident."""

    def _gather(self, offsets, velocity=1500.0, t0=0.05, seed=0, noise=0.2):
        rng = np.random.default_rng(seed)
        ns, dt = 1200, 0.004
        data = rng.normal(0, noise, (len(offsets), ns))
        for i, x in enumerate(np.abs(offsets)):
            k = int((t0 + x / velocity) / dt)
            if 0 < k < ns - 6:
                data[i, k:k + 6] += 1.0
        return data, dt

    def test_correct_offsets_land_inside_the_seawater_bracket(self):
        offsets = np.linspace(425.0, 3970.0, 48)
        data, dt = self._gather(offsets)
        got = X.direct_arrival_consistency(data, offsets, dt)
        self.assertEqual(got["verdict"], X.RESOLVED)
        self.assertTrue(got["supports_assignment"])
        self.assertTrue(got["inside_seawater_bracket"])

    def test_offsets_scaled_wrong_are_caught(self):
        """The classic silent error: a group interval guessed at half the real one."""
        true_offsets = np.linspace(425.0, 3970.0, 48)
        data, dt = self._gather(true_offsets)
        got = X.direct_arrival_consistency(data, true_offsets * 0.5, dt)
        self.assertFalse(got["supports_assignment"])
        self.assertFalse(got["inside_seawater_bracket"])
        self.assertIn("factor", got["reason"])

    def test_offsets_scaled_wrong_the_other_way_too(self):
        true_offsets = np.linspace(425.0, 3970.0, 48)
        data, dt = self._gather(true_offsets)
        got = X.direct_arrival_consistency(data, true_offsets * 2.0, dt)
        self.assertFalse(got["supports_assignment"])
        self.assertAlmostEqual(got["velocity_m_s"], 3000.0, delta=60.0)

    def test_reversed_channel_order_is_not_this_checks_job(self):
        """Reversing the order leaves nothing linear to fit, so this check says it could not tell rather than
        inventing a contradiction."""
        true_offsets = np.linspace(425.0, 3970.0, 48)
        data, dt = self._gather(true_offsets)
        got = X.direct_arrival_consistency(data, true_offsets[::-1], dt)
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertNotIn("supports_assignment", got)

    def test_pure_noise_stays_well_under_the_threshold(self):
        """The threshold is calibrated against this, not chosen to fit."""
        offsets = np.linspace(425.0, 3970.0, 48)
        worst = max(
            X.direct_arrival_consistency(
                np.random.default_rng(s).normal(0, 1, (48, 1200)),
                offsets, 0.004)["contrast"]
            for s in range(6))
        self.assertLess(worst, X.MIN_DIRECT_CONTRAST)

    def test_a_gather_with_no_linear_arrival_says_it_could_not_tell(self):
        rng = np.random.default_rng(1)
        offsets = np.linspace(425.0, 3970.0, 48)
        got = X.direct_arrival_consistency(rng.normal(0, 1, (48, 1200)),
                                           offsets, 0.004)
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertNotIn("supports_assignment", got)


class FoldPatternTest(unittest.TestCase):

    def test_a_rolled_along_line_rises_holds_and_falls(self):
        """48 channels, source moving one bin pair per shot: the midpoint of channel i sits at source -
        offset_i/2, so the bin index is 2*shot - channel."""
        cdp = [2 * shot - ch for shot in range(60) for ch in range(48)]
        got = X.fold_pattern(np.asarray(cdp) - min(cdp))
        self.assertEqual(got["verdict"], X.RESOLVED)
        self.assertTrue(got["supports_assignment"])

    def test_scattered_bins_are_caught(self):
        rng = np.random.default_rng(3)
        cdp = rng.integers(0, 40, 2000)
        got = X.fold_pattern(cdp)
        self.assertFalse(got["supports_assignment"])
        self.assertIn("alternates", got["reason"])

    def test_counting_direction_changes_would_have_failed_the_clean_line(self):
        """Why the metric is total variation and not direction changes: a real roll-along climbs in steps and
        reverses at more than half its bins."""
        cdp = np.asarray([2 * s - c for s in range(60) for c in range(48)])
        _, counts = np.unique(cdp, return_counts=True)
        reversals = int(np.sum(np.diff(np.sign(np.diff(counts.astype(float)))) != 0))
        self.assertGreater(reversals / (counts.size - 2), 0.5)
        self.assertTrue(X.fold_pattern(cdp)["supports_assignment"])

    def test_too_few_bins_is_inconclusive(self):
        got = X.fold_pattern(np.array([1, 1, 2, 2, 3]))
        self.assertEqual(got["verdict"], X.INDETERMINATE)


class CombinedVerdictTest(unittest.TestCase):
    """One check may not decide alone, and silence is not consent."""

    def test_one_contradiction_rejects_however_many_support(self):
        got = X.validate_assignment({
            "direct_arrival": {"supports_assignment": True, "reason": "a"},
            "fold_pattern": {"supports_assignment": False, "reason": "b"},
        })
        self.assertEqual(got["verdict"], "REJECTED")
        self.assertEqual(got["contradicted_by"], ["fold_pattern"])

    def test_silence_alone_is_not_acceptance(self):
        got = X.validate_assignment({
            "direct_arrival": {"verdict": X.INDETERMINATE, "reason": "a"},
            "fold_pattern": {"verdict": X.INDETERMINATE, "reason": "b"},
        })
        self.assertEqual(got["verdict"], X.INDETERMINATE)
        self.assertIn("not the same as", got["reason"])

    def test_support_with_silence_is_accepted_and_says_who_was_silent(self):
        got = X.validate_assignment({
            "direct_arrival": {"supports_assignment": True, "reason": "a"},
            "fold_pattern": {"verdict": X.INDETERMINATE, "reason": "b"},
        })
        self.assertEqual(got["verdict"], "ACCEPTED")
        self.assertIn("fold_pattern", got["reason"])


if __name__ == "__main__":
    unittest.main()
