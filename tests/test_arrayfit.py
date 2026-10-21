"""Spacing error or timing delay, and refusing to say when it cannot be known."""

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


from sumcp import arrayfit as AF   # noqa: E402

WATER = 1492.0


def _rows(dd_values, scale, delay_ms, noise_ms=0.05, seed=0, shots=60):
    """Shots whose slopes follow a known (scale, delay)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(shots):
        dd = float(dd_values[i % len(dd_values)])
        slope = scale * dd / WATER + delay_ms * 1e-3
        slope += rng.normal(0.0, noise_ms * 1e-3)
        rows.append({"shot": i, "semblance": 0.6,
                     "slope_s_per_channel": slope,
                     "intercept_s": 0.5, "dd_per_channel_m": dd,
                     "distance_mean_m": 800.0, "channels": 24})
    return rows


class DegeneracyTest(unittest.TestCase):

    def test_a_line_along_the_array_gets_no_answer(self):
        rows = _rows([-3.125, -3.124, -3.123], scale=1.0, delay_ms=0.32)
        got = AF.assess({"inline": rows}, bootstrap=20)
        self.assertEqual(got["verdict"], "INDETERMINATE")
        self.assertIn("column", got["reason"])
        self.assertIn("crosses the array", got["what_would_answer_it"])
        self.assertIsNone(got["fitting_it_anyway"]["value"])

    def test_the_withheld_fit_is_marked_hypothesized(self):
        """It must not be possible to read the refused number as a result."""
        rows = _rows([-3.125, -3.124], scale=1.0, delay_ms=0.32)
        got = AF.assess({"inline": rows}, bootstrap=20)
        self.assertEqual(got["fitting_it_anyway"]["class"], "HYPOTHESIZED")

    def test_too_few_shots_is_also_indeterminate(self):
        rows = _rows(np.linspace(-3.1, -1.5, 8), scale=1.0, delay_ms=0.32,
                     shots=8)
        got = AF.assess({"short": rows}, bootstrap=20)
        self.assertEqual(got["verdict"], "INDETERMINATE")


class RecoveryTest(unittest.TestCase):
    """A line that crosses the array has to give the planted answer back."""

    def setUp(self):
        self.crossing = np.linspace(-3.125, -1.45, 40)

    def test_a_pure_delay_is_recovered(self):
        rows = _rows(self.crossing, scale=1.0, delay_ms=0.32)
        got = AF.assess({"tie": rows}, bootstrap=120)
        self.assertEqual(got["verdict"], "RESOLVED")
        self.assertAlmostEqual(got["spacing_scale"]["value"], 1.0, delta=0.05)
        self.assertAlmostEqual(got["channel_delay_ms"]["value"], 0.32, delta=0.05)
        self.assertFalse(got["spacing_scale"]["nominal_spacing_rejected"])
        self.assertIn("no evidence to reject",
                      got["spacing_scale"]["meaning"])
        self.assertTrue(got["channel_delay_ms"]["differs_from_zero"])
        self.assertEqual(got["cause"], "per-channel recording delay")

    def test_a_pure_spacing_error_is_recovered(self):
        rows = _rows(self.crossing, scale=0.84, delay_ms=0.0)
        got = AF.assess({"tie": rows}, bootstrap=120)
        self.assertEqual(got["verdict"], "RESOLVED")
        self.assertAlmostEqual(got["spacing_scale"]["value"], 0.84, delta=0.05)
        self.assertTrue(got["spacing_scale"]["nominal_spacing_rejected"])
        self.assertFalse(got["channel_delay_ms"]["differs_from_zero"])
        self.assertEqual(got["cause"], "a spacing error")

    def test_a_degenerate_line_is_predicted_not_fitted(self):
        """The line that carries no information is the strongest check available: it never enters the fit, so
        predicting it is a test."""
        lines = {"tie": _rows(self.crossing, scale=1.0, delay_ms=0.32),
                 "inline": _rows([-3.125], scale=1.0, delay_ms=0.32, seed=3)}
        got = AF.assess(lines, bootstrap=60)
        self.assertEqual(got["lines_fitted"], ["tie"])
        predicted = got["predicted_for_degenerate_lines"]
        self.assertEqual(len(predicted), 1)
        self.assertEqual(predicted[0]["line"], "inline")
        self.assertLess(abs(predicted[0]["difference_ms_per_channel"]), 0.05)

    def test_model_comparison_prefers_the_truth(self):
        rows = _rows(self.crossing, scale=1.0, delay_ms=0.32, noise_ms=0.03)
        got = AF.assess({"tie": rows}, bootstrap=20)
        compare = got["model_comparison"]
        self.assertLess(compare["both_free_rms_ms"], compare["delay_only_rms_ms"])
        self.assertLess(compare["both_free_rms_ms"],
                        compare["spacing_only_rms_ms"])


def _tracking_rows(distances, scale=1.0, offset_ms=0.0, noise_ms=0.05,
                   seed=0, semblance=0.6):
    """Shots whose array-centre arrival follows a known fraction of the distance the headers predict."""
    rng = np.random.default_rng(seed)
    rows = []
    for i, d in enumerate(np.asarray(distances, float)):
        t = scale * d / WATER + offset_ms * 1e-3
        t += rng.normal(0.0, noise_ms * 1e-3)
        rows.append({"shot": i, "semblance": semblance,
                     "slope_s_per_channel": -3.125 / WATER,
                     "intercept_s": t, "dd_per_channel_m": -3.125,
                     "distance_mean_m": float(d), "channels": 24})
    return rows


class SourceTrackingTest(unittest.TestCase):
    """Fixed receiver coordinates are either a real array or one record copied into the rest."""

    def test_a_real_array_tracks_the_source(self):
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60)), bootstrap=120)
        self.assertEqual(got["verdict"], AF.TRACKS)
        self.assertAlmostEqual(got["scale"], 1.0, delta=0.03)
        self.assertGreater(got["correlation"], 0.99)

    def test_copied_headers_do_not_track(self):
        """The positions claim 1200 m of source motion; the time ignores it."""
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60), scale=0.0,
                           noise_ms=0.5), bootstrap=120)
        self.assertEqual(got["verdict"], AF.NO_TRACK)

    def test_a_constant_recording_delay_is_absorbed(self):
        """A late clock must not be reported as untrustworthy geometry."""
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60), offset_ms=40.0),
            bootstrap=120)
        self.assertEqual(got["verdict"], AF.TRACKS)
        self.assertAlmostEqual(got["constant_offset_ms"], 40.0, delta=1.0)

    def test_a_stationary_source_is_inconclusive_not_negative(self):
        got = AF.source_tracking(
            _tracking_rows(np.linspace(800.0, 801.0, 60)), bootstrap=60)
        self.assertEqual(got["verdict"], AF.TRACK_INCONCLUSIVE)
        self.assertIn("cannot show", got["reason"])

    def test_too_few_shots_is_inconclusive(self):
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 5)), bootstrap=20)
        self.assertEqual(got["verdict"], AF.TRACK_INCONCLUSIVE)
        self.assertIn("coherence threshold", got["reason"])

    def test_a_wrong_velocity_is_reported_as_velocity_not_geometry(self):
        """Positions right, assumed velocity 20% low: still TRACKS, and the implied velocity says by how much."""
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60), scale=0.85),
            bootstrap=120)
        self.assertEqual(got["verdict"], AF.TRACKS)
        self.assertAlmostEqual(got["implied_velocity_m_s"], WATER / 0.85,
                               delta=40.0)

    def test_a_wrong_velocity_is_noted_not_hidden(self):
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60), scale=0.85),
            bootstrap=120)
        self.assertIn("velocity_note", got)
        self.assertIn("has not been established", got["velocity_note"])

    def test_a_correct_velocity_gets_no_note(self):
        got = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60)), bootstrap=120)
        self.assertNotIn("velocity_note", got)

    def test_assess_reports_tracking_per_line(self):
        lines = {"tie": _rows(np.linspace(-3.125, -1.45, 40), 1.0, 0.32)}
        got = AF.assess(lines, bootstrap=40)
        self.assertIn("source_tracking", got["per_line"]["tie"])


class ClassificationTest(unittest.TestCase):
    """The tracking verdict has to reach the acquisition classification."""

    FIXED = {"every_channel_moves": False, "every_channel_fixed": True,
             "n_shots": 60, "n_channels": 24, "channel_spacing_m": 3.125,
             "array_length_m": 71.9, "trace_sort": {"kind": "shot"}}

    def test_tracking_names_a_fixed_array(self):
        from sumcp import geometry as G
        tracking = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60)), bootstrap=60)
        got = G.classify_acquisition(dict(self.FIXED), tracking=tracking)
        self.assertEqual(got["kind"], G.ACQ_FIXED_ARRAY)
        self.assertIn("array centre", got["reason"])

    def test_no_tracking_names_the_headers_untrustworthy(self):
        from sumcp import geometry as G
        tracking = AF.source_tracking(
            _tracking_rows(np.linspace(200.0, 1400.0, 60), scale=0.0,
                           noise_ms=0.5), bootstrap=60)
        got = G.classify_acquisition(dict(self.FIXED), tracking=tracking)
        self.assertEqual(got["kind"], G.ACQ_RECEIVERS_UNTRUSTWORTHY)

    def test_inconclusive_tracking_stays_undetermined(self):
        from sumcp import geometry as G
        tracking = AF.source_tracking(
            _tracking_rows(np.linspace(800.0, 801.0, 60)), bootstrap=40)
        got = G.classify_acquisition(dict(self.FIXED), tracking=tracking)
        self.assertEqual(got["kind"], G.ACQ_UNDETERMINED)
        self.assertTrue(any("cannot show" in u for u in got["unresolved"]))


class BootstrapTest(unittest.TestCase):

    def test_the_interval_widens_with_noise(self):
        clean = AF.assess({"tie": _rows(np.linspace(-3.125, -1.45, 40),
                                        1.0, 0.32, noise_ms=0.02)},
                          bootstrap=150)
        noisy = AF.assess({"tie": _rows(np.linspace(-3.125, -1.45, 40),
                                        1.0, 0.32, noise_ms=0.30)},
                          bootstrap=150)
        width = lambda r: r["channel_delay_ms"]["ci_95"][1] - r["channel_delay_ms"]["ci_95"][0]
        self.assertGreater(width(noisy), 3 * width(clean))


if __name__ == "__main__":
    unittest.main()
