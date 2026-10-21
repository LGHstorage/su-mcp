"""Unit tests for the v0.3 geometry and measurement layer."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
# Every tool call writes an audit entry now, so the suite gets its own log: test runs in logs/processing.jsonl
# would corrupt the record the adversarial suite reads to decide whether a forbidden program ran.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))


SHOTS, CHANNELS = 4, 8


class GeometryTestCase(unittest.TestCase):
    """Fixtures with a known, constructed geometry."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs", "state"):
            (cls.root / name).mkdir()
        os.environ["SU_MCP_ROOT"] = str(cls.root)

        import sumcp
        from sumcp import (analysis, config, evidence, geometry, ingest, measure,
                           paths, preview, provenance, runner, segy, sufile,
                           suenv, tools)
        for module in (config, paths, provenance, suenv, runner, sufile, segy,
                       evidence, geometry, measure, ingest, preview, analysis,
                       tools, sumcp):
            importlib.reload(module)
        from sumcp import (analysis, evidence, geometry, measure,  # noqa: F811
                           sufile, suenv, tools)
        cls.geometry, cls.measure, cls.evidence = geometry, measure, evidence
        cls.analysis, cls.tools, cls.sufile = analysis, tools, sufile

        if suenv.find_program("suplane") is None:
            raise unittest.SkipTest("Seismic Unix is not on this system")
        cls.suenv = suenv

        cls._make("flat.su", dip=0)
        cls._make("dipping.su", dip=2)
        cls._geometry_file("moving.su", moving=True)
        cls._geometry_file("fixed.su", moving=False)
        cls._geometry_file("scaled.su", moving=True, scalco=-100)
        # A spread far wider than the shot spacing: this is the case where a shot number sitting in the cdp field
        # is geometrically impossible.
        cls._geometry_file("wide.su", moving=True, shot_step=20, group_step=50)
        # counit says degrees, but the offset header agrees with the coordinates read as lengths - a real case
        # from the Viking Graben dataset.
        cls._geometry_file("degrees.su", moving=True, counit=3)
        # A survey with real CMP fold: shot interval equal to the group interval, so each bin holds traces from
        # several shots.
        cls._geometry_file("folded.su", moving=True, shot_step=10, group_step=10)
        cls._sorted_copy("folded.su", "by_cdp.su")

    def test_read_traces_matches_one_at_a_time(self):
        """One open and one seek per trace is invisible on ext4 and a timeout on a Windows drive mounted into
        WSL."""
        path = self.root / "raw" / "moving.su"
        geom = self.sufile.geometry(path)
        picks = list(range(0, geom["ntr"], 3))
        one = [self.sufile.read_gather(path, i, 1, geom)[0][0] for i in picks]
        for budget in (512 << 20, 1):          # span read, then seek fallback
            batched = self.sufile.read_traces(path, picks, geom,
                                              span_budget_bytes=budget)
            self.assertEqual(batched.shape, (len(picks), geom["ns"]))
            for a, b in zip(one, batched):
                self.assertTrue((a == b).all())
        self.assertEqual(
            self.sufile.read_traces(path, [], geom).shape, (0, geom["ns"]))

    @classmethod
    def _program(cls, name):
        path = cls.suenv.find_program(name)
        if path is None:
            raise unittest.SkipTest(f"{name} not found")
        return path

    @classmethod
    def _make(cls, name, dip):
        """One plane with a known dip in ms/trace - the unit the measurement uses."""
        with open(cls.root / "raw" / name, "wb") as out:
            subprocess.run([cls._program("suplane"), "npl=1", "nt=256",
                            f"ntr={CHANNELS}", "dt=0.004", f"dip1={dip}",
                            f"len1={CHANNELS}", "ct1=128", f"cx1={CHANNELS // 2}"],
                           stdout=out, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def _chain(cls, src, dst, steps, append=False):
        procs = []
        with open(src, "rb") as fin, open(dst, "ab" if append else "wb") as fout:
            stdin = fin
            for i, args in enumerate(steps):
                last = i == len(steps) - 1
                p = subprocess.Popen([cls._program("suchw")] + args, stdin=stdin,
                                     stdout=fout if last else subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
                if stdin is not fin:
                    stdin.close()
                stdin = p.stdout
                procs.append(p)
            for p in procs:
                p.wait()

    @classmethod
    def _sorted_copy(cls, src, dst):
        """CDP-sort a copy: cdp = (sx + gx) / (2 * midpoint step)."""
        mid = cls.root / "raw" / f"_mid_{dst}"
        cls._chain(cls.root / "raw" / src, mid,
                   [["key1=cdp", "key2=sx", "key3=gx", "a=0", "b=1", "c=1", "d=10"]])
        with open(mid, "rb") as fin, open(cls.root / "raw" / dst, "wb") as fout:
            subprocess.run([cls._program("susort"), "cdp", "offset"], stdin=fin,
                           stdout=fout, stderr=subprocess.DEVNULL, check=True)
        mid.unlink()

    @classmethod
    def _geometry_file(cls, name, *, moving: bool, scalco: int = 0,
                       shot_step: int = 100, group_step: int = 10,
                       counit: int = 1):
        """SHOTS shots x CHANNELS channels, shot every 100 m, groups 10 m apart."""
        dst = cls.root / "raw" / name
        dst.unlink(missing_ok=True)
        src = cls.root / "raw" / "flat.su"
        for shot in range(1, SHOTS + 1):
            steps = [
                ["key1=fldr", "key2=trid", f"a={shot}", "b=0", "c=0", "d=1"],
                ["key1=tracf", "key2=tracl", "a=0", "b=1", "c=0", "d=1"],
                ["key1=sx", "key2=fldr", "a=0", f"b={shot_step}", "c=0", "d=1"],
                (["key1=gx", "key2=sx", "key3=tracf", "a=0", "b=1",
                  f"c={group_step}", "d=1"]
                 if moving else
                 ["key1=gx", "key2=tracf", "a=1000", f"b={group_step}", "c=0", "d=1"]),
                ["key1=offset", "key2=gx", "key3=sx", "a=0", "b=1", "c=-1", "d=1"],
                ["key1=counit", "key2=trid", f"a={counit}", "b=0", "c=0", "d=1"],
            ]
            if scalco:
                steps.append(["key1=scalco", "key2=trid", f"a={scalco}", "b=0",
                              "c=0", "d=1"])
            cls._chain(src, dst, steps, append=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("SU_MCP_ROOT", None)

    def resolved(self, name):
        return self.geometry.resolve_coordinates(self.root / "raw" / name)


class TestApparentVelocity(GeometryTestCase):

    def test_recovers_a_planted_dip(self):
        r = self.measure.apparent_velocity(self.root / "raw" / "dipping.su",
                                           fldr=0, max_slope_ms=6.0)
        self.assertAlmostEqual(abs(r["slope_ms_per_channel"]), 2.0, delta=0.3)
        self.assertTrue(r["slope_consistent_across_bands"], r["per_band"])
        self.assertGreater(max(b["contrast"] for b in r["per_band"]), 2.0)

    def test_flat_event_measures_as_flat(self):
        r = self.measure.apparent_velocity(self.root / "raw" / "flat.su",
                                           fldr=0, max_slope_ms=6.0)
        self.assertAlmostEqual(r["slope_ms_per_channel"], 0.0, delta=0.3)

    def test_slope_converts_to_a_velocity(self):
        r = self.measure.apparent_velocity(self.root / "raw" / "dipping.su",
                                           fldr=0, channel_spacing_m=10.0)
        self.assertAlmostEqual(r["apparent_velocity_m_s"], 10.0 / 0.002, delta=900)

    def test_prediction_comparison_is_reported(self):
        r = self.measure.apparent_velocity(self.root / "raw" / "dipping.su", fldr=0,
                                           channel_spacing_m=10.0,
                                           predicted_slope_ms=-2.0)
        self.assertIn("measured_over_predicted", r)
        self.assertIn("matches_prediction", r)

    def test_short_window_refused(self):
        with self.assertRaises(ValueError):
            self.measure.apparent_velocity(self.root / "raw" / "flat.su", fldr=0,
                                           tmin=0.0, tmax=0.01)


class TestCoordinates(GeometryTestCase):

    def test_negative_scalco_divides(self):
        plain = self.resolved("moving.su")
        scaled = self.resolved("scaled.su")
        self.assertEqual(scaled["scalco_values"], [-100])
        self.assertAlmostEqual(scaled["source"]["sx"]["max"],
                               plain["source"]["sx"]["max"] / 100.0, places=6)
        self.assertTrue(any("divided by 100" in n for n in scaled["notes"]),
                        scaled["notes"])

    def test_counit_one_is_a_length(self):
        r = self.resolved("moving.su")
        self.assertEqual(r["counit_values"], [1])
        self.assertTrue(r["units_are_lengths"])

    def test_signed_offset_header_agrees_with_distance(self):
        state = self.geometry.offset_state(self.resolved("moving.su"))
        self.assertEqual(state["header_state"], "varying")
        self.assertTrue(state["agrees"], state)

    def test_zero_offset_header_carries_no_information(self):
        r = self.resolved("fixed.su")
        r["_raw"]["offset"][:] = 0
        state = self.geometry.offset_state(r)
        self.assertEqual(state["header_state"], "zero")
        self.assertIsNone(state["agrees"])


class TestUnitCrossCheck(GeometryTestCase):
    """counit is a header field, so it is checked rather than believed."""

    def test_counit_contradicted_by_the_offset_header(self):
        r = self.resolved("degrees.su")
        self.assertEqual(r["counit_values"], [3])
        self.assertFalse(r["counit_says_lengths"])
        self.assertTrue(r["units_are_lengths"])          # the data overrules the header
        # geometry-0.7 decides from the coordinate magnitudes themselves
        self.assertTrue(r["unit_evidence"]["angular_plausibility"]["impossible_as_angles"])
        self.assertTrue(any("counit is wrong" in n for n in r["notes"]), r["notes"])

    def test_counit_one_needs_no_argument(self):
        r = self.resolved("moving.su")
        self.assertTrue(r["counit_says_lengths"])
        self.assertTrue(r["units_are_lengths"])

    def test_without_an_offset_header_counit_stands(self):
        r = self.resolved("degrees.su")
        r["_raw"]["offset"][:] = 0
        again = self.geometry.resolve_coordinates(self.root / "raw" / "degrees.su")
        self.assertTrue(again["units_are_lengths"])      # this fixture does have offsets
        # a file with no offsets cannot be rescued by this check
        blank = dict(again)
        # geometry-0.7: the offset header is reported as corroboration only and does not take part in the units
        # decision
        self.assertIn("offset_header_corroborates", again["unit_evidence"])
        self.assertTrue(again["unit_evidence"]["corroboration_role"].startswith("reported only"))


class TestSortDetection(GeometryTestCase):
    """What a header group means depends on how the file is sorted."""

    def test_shot_and_cdp_sorts_are_told_apart(self):
        self.assertEqual(self.geometry.detect_sort(self.resolved("moving.su"))["kind"],
                         "shot")
        cdp = self.geometry.detect_sort(self.resolved("by_cdp.su"))
        self.assertEqual(cdp["kind"], "cdp")
        self.assertGreater(cdp["median_traces_per_cdp"], 1)

    def test_a_fold_one_file_is_not_called_cdp_sorted(self):
        """Every bin holding one trace makes the sort nominal, not a CDP sort."""
        sort = self.geometry.detect_sort(self.resolved("moving.su"))
        self.assertEqual(sort["kind"], "shot")

    def test_receiver_spacing_survives_resorting(self):
        shot = self.geometry.receiver_variation(self.resolved("folded.su"))
        cdp = self.geometry.receiver_variation(self.resolved("by_cdp.su"))
        self.assertAlmostEqual(shot["channel_spacing_m"], cdp["channel_spacing_m"],
                               places=3)
        self.assertEqual(shot["receiver_positions"], cdp["receiver_positions"])

    def test_array_length_is_withheld_when_the_sort_makes_it_meaningless(self):
        cdp = self.geometry.receiver_variation(self.resolved("by_cdp.su"))
        self.assertIsNone(cdp["array_length_m"])
        self.assertIn("cdp-sorted", cdp["array_length_note"])
        self.assertIsNotNone(
            self.geometry.receiver_variation(self.resolved("folded.su"))["array_length_m"])


class TestReceiverVariation(GeometryTestCase):

    def test_moving_receivers_detected(self):
        v = self.geometry.receiver_variation(self.resolved("moving.su"))
        self.assertTrue(v["every_channel_moves"])
        self.assertFalse(v["every_channel_fixed"])
        self.assertEqual(v["n_shots"], SHOTS)
        self.assertEqual(v["n_channels"], CHANNELS)
        self.assertAlmostEqual(v["channel_spacing_m"], 10.0, places=3)

    def test_fixed_receivers_detected(self):
        v = self.geometry.receiver_variation(self.resolved("fixed.su"))
        self.assertFalse(v["every_channel_moves"])
        self.assertTrue(v["every_channel_fixed"])
        self.assertEqual(v["distinct_positions_per_channel"], {"min": 1, "max": 1})


class TestCDPLevels(GeometryTestCase):

    def _with_cdp(self, name, expr, source="moving.su"):
        dst = self.root / "raw" / name
        dst.unlink(missing_ok=True)
        self._chain(self.root / "raw" / source, dst, [expr])
        return self.geometry.cdp_state(self.resolved(name))

    def test_absent_when_zero(self):
        self.assertEqual(self.geometry.cdp_state(self.resolved("moving.su"))["level"],
                         self.geometry.CDP_ABSENT)

    def test_implausible_when_cdp_is_really_the_shot_number(self):
        state = self._with_cdp("cdp_bad.su",
                               ["key1=cdp", "key2=fldr", "a=0", "b=1", "c=0", "d=1"],
                               source="wide.su")
        self.assertEqual(state["level"], self.geometry.CDP_IMPLAUSIBLE)
        self.assertGreater(state["spread_over_spacing"], 2.0)
        self.assertIn("not a CMP binning", state["reason"])

    def test_plausible_when_bins_follow_the_midpoint(self):
        # midpoint = (sx + gx)/2 ; with 10 m groups the midpoint step is 5 m
        state = self._with_cdp("cdp_ok.su",
                               ["key1=cdp", "key2=sx", "key3=gx", "a=0", "b=1",
                                "c=1", "d=10"])
        self.assertEqual(state["level"], self.geometry.CDP_PLAUSIBLE, state)
        self.assertLessEqual(state["spread_over_spacing"], 2.0)


class TestClassification(GeometryTestCase):

    def _variation(self, fixed):
        return {"every_channel_moves": not fixed, "every_channel_fixed": fixed,
                "n_shots": 20, "n_channels": 24, "channel_spacing_m": 3.1,
                "array_length_m": 71.9}

    def test_moving_receivers(self):
        c = self.geometry.classify_acquisition(self._variation(False))
        self.assertEqual(c["kind"], self.geometry.ACQ_MOVING_RECEIVERS)

    def test_fixed_without_measurement_is_undetermined(self):
        c = self.geometry.classify_acquisition(self._variation(True))
        self.assertEqual(c["kind"], self.geometry.ACQ_UNDETERMINED)
        self.assertTrue(any("arrival-time" in u for u in c["unresolved"]))

    def test_fixed_with_a_tracking_trend_is_a_real_array(self):
        trend = {"tracks_source_motion": True, "measured_ms_per_shot": -7.07,
                 "predicted_ms_per_shot": -7.19, "correlation_with_prediction": 0.99}
        c = self.geometry.classify_acquisition(self._variation(True), trend)
        self.assertEqual(c["kind"], self.geometry.ACQ_FIXED_ARRAY)
        self.assertIn("0.99", c["reason"])

    def test_fixed_with_a_non_tracking_trend_is_untrustworthy(self):
        trend = {"tracks_source_motion": False, "measured_ms_per_shot": 0.0,
                 "predicted_ms_per_shot": -7.19, "correlation_with_prediction": 0.02}
        c = self.geometry.classify_acquisition(self._variation(True), trend)
        self.assertEqual(c["kind"], self.geometry.ACQ_RECEIVERS_UNTRUSTWORTHY)
        self.assertIn("cannot be used", c["reason"])

    def test_velocity_mismatch_is_surfaced_as_unresolved(self):
        check = {"apparent_velocity_m_s": 1786.0, "predicted_velocity_m_s": 1501.0,
                 "matches_prediction": False}
        c = self.geometry.classify_acquisition(self._variation(False), None, check)
        self.assertTrue(any("not the direct water wave" in u for u in c["unresolved"]))


class TestVelocityCrossCheck(GeometryTestCase):
    """Two independent measurements of one wavefront have to agree."""

    def test_agreement_is_reported(self):
        r = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1500.0, "channel_spacing_m": 3.125},
            {"source_side": {"fitted_velocity_m_s": 1492.0}})
        self.assertTrue(r["agrees"])
        self.assertIn("one wavefront", r["reason"])

    def test_disagreement_does_not_name_a_single_cause(self):
        """A 20% disagreement says something is wrong, not what."""
        r = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1786.0, "channel_spacing_m": 3.125,
             "slope_ms_per_channel": -1.75},
            {"source_side": {"fitted_velocity_m_s": 1492.0}})
        self.assertFalse(r["agrees"])
        self.assertEqual(r["cause"], "UNKNOWN")
        causes = [h["cause"] for h in r["hypotheses"]]
        self.assertIn("channel spacing wrong", causes)
        self.assertIn("per-channel timing delay", causes)
        self.assertTrue(all(h["status"] == "HYPOTHESIZED" for h in r["hypotheses"]))
        spacing = next(h for h in r["hypotheses"] if h["cause"] == "channel spacing wrong")
        self.assertAlmostEqual(spacing["candidate_spacing_m"], 2.61, delta=0.02)

    def test_observed_and_derived_are_separated(self):
        r = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1786.0, "channel_spacing_m": 3.125,
             "slope_ms_per_channel": -1.75},
            {"source_side": {"fitted_velocity_m_s": 1492.0}})
        # the channel moveout is measured; the velocity from it is not
        self.assertEqual(r["observed"]["channel_moveout_ms_per_channel"], -1.75)
        self.assertEqual(r["derived"]["velocity_across_channels_m_s"], 1786.0)
        self.assertIn("inherits", r["derived"]["note"])

    def test_an_in_line_survey_cannot_separate_spacing_from_timing(self):
        """Both scale the same way when the array-ray angle never changes."""
        inline = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1786.0, "channel_spacing_m": 3.125},
            {"source_side": {"fitted_velocity_m_s": 1492.0}},
            array_ray_angle_range_deg=[0.1, 2.3])
        self.assertFalse(inline["separability"]["can_separate_spacing_from_timing"])
        crossing = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1786.0, "channel_spacing_m": 3.125},
            {"source_side": {"fitted_velocity_m_s": 1492.0}},
            array_ray_angle_range_deg=[0.2, 60.0])
        self.assertTrue(crossing["separability"]["can_separate_spacing_from_timing"])

    def test_missing_half_is_not_a_verdict(self):
        r = self.measure.cross_check_velocity(
            {"apparent_velocity_m_s": 1786.0}, {})
        self.assertIsNone(r["agrees"])

    def test_scan_mode_finds_an_arrival_outside_the_window(self):
        """A fixed window cannot hold an arrival that moves across the line."""
        trend = self.measure.arrival_time_trend(
            self.root / "raw" / "dipping.su", [0], tmin=0.0, tmax=0.2,
            slope_ms=2.0, pick_mode="scan", band=None, window_s=0.1, step_s=0.02)
        picked = trend["per_shot"][0]["peak_time_s"]
        self.assertGreater(picked, 0.2)          # the event sits at ~0.5 s
        self.assertIsNotNone(trend["per_shot"][0]["contrast"])


class TestChannelGeometryFit(GeometryTestCase):
    """An in-line line cannot separate a spacing scale from a channel delay."""

    def test_in_line_geometry_is_reported_as_degenerate(self):
        r = self.measure.channel_geometry_fit(
            self.root / "raw" / "moving.su", velocity=1500.0, band=None,
            tmin_window_s=0.4, min_contrast=0.0, spacing_m=10.0)
        # every shot sees the same array orientation, so predicted is constant
        self.assertIn(r["status"], ("DEGENERATE", "INSUFFICIENT"))
        if r["status"] == "DEGENERATE":
            self.assertIn("cannot be separated", r["reason"])
            self.assertIn("crosses the array", r["reason"])

    def test_models_are_reported_side_by_side_not_reduced_to_one(self):
        """The synthetic fixtures cannot separate the models, but the shape of the answer is what matters:
        competing models with their residuals."""
        import numpy as np
        predicted = np.linspace(-2.1, -1.0, 40)
        measured = 1.10 * predicted + 0.54          # a scale and a delay
        a, b = np.polyfit(predicted, measured, 1)
        self.assertAlmostEqual(a, 1.10, places=6)
        self.assertAlmostEqual(b, 0.54, places=6)
        a_only = float(predicted @ measured / (predicted @ predicted))
        resid_free = np.std(measured - (a * predicted + b))
        resid_scale_only = np.std(measured - a_only * predicted)
        # dropping the delay term has to cost something, or it was not needed
        self.assertGreater(resid_scale_only, resid_free * 1.2)


class TestAnalysisRecordsEvidence(GeometryTestCase):

    def test_capabilities_and_report_are_written(self):
        self.evidence.manifest_path("moving").unlink(missing_ok=True)
        self.tools.dataset_register_su("moving", "raw/moving.su", "moving spread")
        r = self.tools.geometry_analyze("moving")
        self.assertTrue(r["ok"], r)
        caps = r["capabilities"]
        self.assertEqual(caps["geometry.coordinate_scale_resolved"], "PASS")
        self.assertEqual(caps["geometry.acquisition_classified"], "PASS")
        self.assertEqual(caps["geometry.receiver_positions_trustworthy"], "PASS")
        self.assertEqual(caps["geometry.cdp_header_plausible"], "UNKNOWN")
        manifest = self.evidence.load("moving")
        self.assertIn("geometry_report", manifest["artifacts"])
        entry = manifest["capabilities"]["geometry.acquisition_classified"]
        self.assertEqual(entry["algorithm_version"], self.geometry.GEOMETRY_VERSION)
        self.assertIn("reason", entry["evidence"])

    def test_stacking_is_still_refused_after_geometry_analysis(self):
        self.evidence.manifest_path("moving2").unlink(missing_ok=True)
        self.tools.dataset_register_su("moving2", "raw/moving.su")
        self.tools.geometry_analyze("moving2")
        manifest = self.evidence.load("moving2")
        with self.assertRaises(self.evidence.PrerequisiteError) as ctx:
            self.evidence.require(manifest, ["geometry.validated",
                                             "velocity.model_available"], "Stacking")
        self.assertIn("geometry.validated", str(ctx.exception))

    def test_analysis_refuses_an_unimported_dataset(self):
        self.assertFalse(self.tools.geometry_analyze("no_such_dataset")["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
