"""The refusals."""

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


from sumcp import cmp, evidence, geometry, reflection as R   # noqa: E402

STACK_PREREQUISITES = [
    "geometry.validated",
    "reflection.processing_feasible",
    "geometry.cmp_assigned",
    "velocity.validated",
]


def _manifest(**capabilities):
    manifest = {"dataset_id": "fixture", "capabilities": {}}
    for name, (status, note) in capabilities.items():
        evidence.set_capability(manifest, name, status, {"measured": note},
                                "test", "run", notes=[note])
    return manifest


class StackGateTest(unittest.TestCase):

    def test_a_feasibility_fail_blocks_the_stack_and_says_why(self):
        manifest = _manifest(**{
            "reflection.processing_feasible": (
                evidence.FAIL,
                "no candidate survived all three branches; detection limit "
                "0.4x the record RMS"),
        })
        with self.assertRaises(evidence.PrerequisiteError) as caught:
            evidence.require(manifest, STACK_PREREQUISITES, "Stacking")
        message = str(caught.exception)
        self.assertIn("reflection.processing_feasible", message)
        self.assertIn("FAIL", message)
        self.assertIn("detection limit", message)
        # and it must not stay silent about the ones never even measured
        self.assertIn("velocity.validated", message)

    def test_inconclusive_is_not_a_pass(self):
        """A gather that could not have shown a reflection must not open the gate just because it did not say
        FAIL."""
        manifest = _manifest(**{
            "reflection.processing_feasible": (
                evidence.UNKNOWN, "sensitivity ladder never ran"),
        })
        with self.assertRaises(evidence.PrerequisiteError):
            evidence.require(manifest, ["reflection.processing_feasible"], "Stacking")

    def test_the_gate_opens_when_everything_is_measured(self):
        manifest = _manifest(**{name: (evidence.PASS, "measured")
                                for name in STACK_PREREQUISITES})
        evidence.require(manifest, STACK_PREREQUISITES, "Stacking")   # no raise


class Data001RegressionTest(unittest.TestCase):
    """data001 is not stack-development data any more; it is the case the system has to refuse."""

    def test_direct_wave_only_gather_refuses_and_quantifies(self):
        dt, ns, ntr = 0.001, 2000, 120
        rng = np.random.default_rng(0)
        offsets = np.linspace(180.0, 2300.0, ntr)
        t = np.arange(ns) * dt
        data = np.zeros((ntr, ns))
        for i, x in enumerate(offsets):
            a = (t - x / R.DEFAULT_WATER) * np.pi * 60.0
            data[i] = 3.0 * (1 - 2 * a ** 2) * np.exp(-a ** 2)
        data += 0.05 * rng.standard_normal(data.shape)

        out = R.assess(data, offsets, dt, 0.0, t0_range=(0.1, 1.2))
        self.assertNotEqual(out["REFLECTION_PROCESSING_FEASIBLE"], R.PASS)
        self.assertEqual(out["agreed_candidates"], [])
        self.assertIn(out["detection_threshold_x_rms"]["class"],
                      ("DERIVED", "OBSERVED"))
        self.assertTrue(out["notes"])

    def test_a_fixed_array_has_fold_without_leverage(self):
        """The trap this guards: a bin can hold plenty of traces and still carry no moveout information, because
        the information is in the spread of offset SQUARED, not of offset."""
        # every trace in the bin at nearly the same large offset
        offsets = np.linspace(2000.0, 2100.0, 40)
        barren = float(np.median((offsets ** 2).max() - (offsets ** 2).min()))
        # the same offset span, but near zero offset
        near = np.linspace(100.0, 200.0, 40)
        self.assertGreater(
            float((offsets ** 2).max() - (offsets ** 2).min()),
            float((near ** 2).max() - (near ** 2).min()))
        # equal offset spans, so offset span alone cannot tell them apart
        self.assertAlmostEqual(offsets.max() - offsets.min(),
                               near.max() - near.min(), places=6)
        self.assertGreater(barren, 0.0)

    def test_fold_without_leverage_scores_near_zero(self):
        """Two surveys, both with fold."""
        spread = geometry.assign_cmp(
            _streamer(channel_offsets=np.linspace(100.0, 1500.0, 24)),
            receiver_spacing_m=25.0, sample_interval_s=0.004)
        flat = geometry.assign_cmp(
            _streamer(channel_offsets=np.linspace(2000.0, 2010.0, 24)),
            receiver_spacing_m=25.0, sample_interval_s=0.004)

        # the flat survey has MORE fold and a perfect offset_diversity, so neither of those can be the gate
        self.assertGreater(flat["fold"]["median"], spread["fold"]["median"])
        self.assertGreater(flat["offset_diversity"], spread["offset_diversity"])

        self.assertEqual(spread["nmo_leverage"]["verdict"], "USABLE")
        self.assertIn(flat["nmo_leverage"]["verdict"], ("NONE", "MARGINAL"))
        self.assertGreater(spread["nmo_leverage"]["moveout_spread_ms"],
                           10 * flat["nmo_leverage"]["moveout_spread_ms"])
        self.assertLessEqual(flat["nmo_leverage"]["moveout_spread_samples"], 2.0)

    def test_single_trace_bins_have_no_leverage_whatever_they_contain(self):
        """A line binned so finely that each bin holds one trace has no CMP gather at all, and the few bins that
        do hold two must not be read as if they described the survey."""
        sparse = geometry.assign_cmp(
            _streamer(channel_offsets=np.array([500.0]), shots=60),
            bin_size_m=1.0, sample_interval_s=0.004)
        self.assertEqual(sparse["nmo_leverage"]["verdict"], "NONE")
        self.assertIn("no gather", sparse["nmo_leverage"]["reason"])


def _streamer(channel_offsets, shots: int = 40, shot_interval: float = 25.0):
    """A straight line of shots, each recording at the given offsets."""
    sx, sy, gx, gy = [], [], [], []
    for shot in range(shots):
        s = shot * shot_interval
        for offset in channel_offsets:
            sx.append(s)
            sy.append(0.0)
            gx.append(s + float(offset))
            gy.append(0.0)
    return {"_scaled": {k: np.asarray(v, dtype=float) for k, v in
                        (("sx", sx), ("sy", sy), ("gx", gx), ("gy", gy))}}


class CmpGateTest(unittest.TestCase):
    """Entering the stack pipeline is a decision made from what was measured earlier, not from how the bins turn
    out."""

    def test_feasibility_is_a_prerequisite_for_binning(self):
        self.assertIn("reflection.processing_feasible",
                      cmp.STACK_TRACK_PREREQUISITES)
        manifest = _manifest(**{
            name: (evidence.PASS, "measured")
            for name in cmp.STACK_TRACK_PREREQUISITES
            if name != "reflection.processing_feasible"})
        evidence.set_capability(
            manifest, "reflection.processing_feasible", evidence.FAIL,
            {"detection_threshold_x_rms": 0.4}, "test", "run",
            notes=["nothing survived all three branches"])
        with self.assertRaises(evidence.PrerequisiteError) as caught:
            evidence.require(manifest, cmp.STACK_TRACK_PREREQUISITES, "CMP binning")
        self.assertIn("nothing survived", str(caught.exception))


class HeaderCdpComparisonTest(unittest.TestCase):
    """A cdp already in the file is a claim."""

    def test_a_shifted_numbering_still_agrees(self):
        computed = np.repeat(np.arange(1, 6), 4)
        header = computed + 999
        got = cmp._compare_with_header(header, computed)
        self.assertTrue(got["agrees"])

    def test_a_header_bin_split_by_the_coordinates_is_reported(self):
        computed = np.repeat(np.arange(1, 7), 2)
        header = np.repeat(np.arange(1, 4), 4)          # coarser than the truth
        got = cmp._compare_with_header(header, computed)
        self.assertFalse(got["agrees"])
        self.assertEqual(got["header_bins_split_by_coordinates"], 3)

    def test_an_absent_header_is_not_a_disagreement(self):
        computed = np.repeat(np.arange(1, 6), 4)
        got = cmp._compare_with_header(np.zeros_like(computed), computed)
        self.assertIsNone(got["agrees"])
        self.assertEqual(got["header_cdp"], "absent")


class BareSortKeyTest(unittest.TestCase):
    """susort takes bare key names."""

    def test_bare_keys_render_and_are_still_validated(self):
        from sumcp import runner
        self.assertEqual(runner.validate_params({"cdp": None, "offset": None}),
                         ["cdp", "offset"])
        for bad in ("../etc/passwd", "a b", "tape"):
            with self.subTest(bad=bad), self.assertRaises(runner.ParameterError):
                runner.validate_params({bad: None})


if __name__ == "__main__":
    unittest.main()


class CapabilityWriteTest(unittest.TestCase):
    """Every status written to a manifest must be one of the three names."""

    def _rows(self, dd_values, distances, seed=0):
        rng = np.random.default_rng(seed)
        rows = []
        for i in range(60):
            dd = float(dd_values[i % len(dd_values)])
            d = float(distances[i % len(distances)])
            rows.append({
                "shot": i, "semblance": 0.6,
                "slope_s_per_channel": dd / 1492.0 + 0.32e-3
                + rng.normal(0, 5e-8),
                "intercept_s": d / 1492.0 + rng.normal(0, 5e-5),
                "dd_per_channel_m": dd, "distance_mean_m": d, "channels": 24,
            })
        return rows

    def test_fit_array_geometry_writes_only_valid_statuses(self):
        from unittest import mock

        from sumcp import tools

        manifests = {}
        for name in ("tie", "inline"):
            manifest = _manifest(**{
                "dataset.imported": (evidence.PASS, "imported"),
                "geometry.coordinate_scale_resolved": (evidence.PASS, "m"),
            })
            manifest["dataset_id"] = name
            manifests[name] = manifest

        lines = {
            "tie": self._rows(np.linspace(-3.125, -1.45, 40),
                              np.linspace(200.0, 1400.0, 60)),
            # fixed receivers, source barely moving: tracking must come back INCONCLUSIVE, which is the None
            # branch that broke
            "inline": self._rows([-3.125], np.linspace(800.0, 800.5, 60),
                                 seed=3),
        }
        variation = {"every_channel_moves": False, "every_channel_fixed": True,
                     "n_shots": 60, "n_channels": 24, "channel_spacing_m": 3.125,
                     "array_length_m": 71.9, "trace_sort": {"kind": "shot"}}

        saved = []
        with mock.patch.object(tools.evidence, "load",
                               side_effect=lambda d: manifests[d]), \
             mock.patch.object(tools.evidence, "save",
                               side_effect=saved.append), \
             mock.patch.object(tools.evidence, "get_artifact",
                               return_value={"path": "work/x/x.su"}), \
             mock.patch.object(tools, "safe_input_path",
                               side_effect=lambda p: Path(p)), \
             mock.patch.object(tools.sufile, "geometry", return_value={}), \
             mock.patch.object(tools.geometry, "resolve_coordinates",
                               return_value={}), \
             mock.patch.object(tools.geometry, "receiver_variation",
                               return_value=variation), \
             mock.patch.object(tools.arrayfit, "measure_slopes",
                               side_effect=lambda path, **kw: lines.pop(
                                   next(iter(lines)))):
            got = tools.fit_array_geometry(["tie", "inline"], bootstrap=40)

        self.assertTrue(got["ok"], got.get("error"))
        self.assertEqual(len(saved), 2)
        written = 0
        for manifest in manifests.values():
            for name, entry in manifest["capabilities"].items():
                self.assertIn(entry["status"], (evidence.PASS, evidence.FAIL,
                                                evidence.UNKNOWN),
                              f"{name} was written as {entry['status']!r}")
                written += 1
        self.assertGreater(written, 4)
        # the degenerate line's tracking has no answer, and UNKNOWN is the honest way to say that
        self.assertEqual(
            manifests["inline"]["capabilities"][
                "geometry.receiver_positions_trustworthy"]["status"],
            evidence.UNKNOWN)
        self.assertEqual(
            manifests["tie"]["capabilities"][
                "geometry.receiver_positions_trustworthy"]["status"],
            evidence.PASS)


class EvidenceClassTest(unittest.TestCase):
    """A number's class has to survive the arithmetic done to it."""

    def test_a_velocity_from_an_assumed_spacing_is_assumed(self):
        from sumcp import claims as C
        spacing = C.assumed(3.125, "caller-supplied channel spacing")
        velocity = C.derived(1492.0, "spacing over slope",
                             inputs=[spacing,
                                     C.derived(2.09, "semblance maximum")])
        self.assertEqual(velocity["class"], C.ASSUMED)
        self.assertFalse(C.is_established(velocity))

    def test_a_velocity_from_a_measured_spacing_is_derived(self):
        from sumcp import claims as C
        spacing = C.derived(3.125, "median step between receiver positions",
                            inputs=[C.observed("gx/gy", "trace headers")])
        velocity = C.derived(1492.0, "spacing over slope",
                             inputs=[spacing,
                                     C.derived(2.09, "semblance maximum")])
        self.assertEqual(velocity["class"], C.DERIVED)
        self.assertTrue(C.is_established(velocity))

    def test_nmo_leverage_inherits_the_reference_velocity(self):
        """The leverage verdict is graded against a velocity nobody measured, so the spread it is graded on
        cannot be reported as established."""
        report = geometry._leverage_report(
            offset_sq_range=1e5, moveout_s=0.05, velocity=1800.0, t_zero=1.0,
            sample_interval_s=0.004, fold_median=20, multi_trace_fraction=0.9)
        self.assertEqual(report["reference"]["class"], "ASSUMED")
        self.assertEqual(report["claims"]["moveout_spread_ms"]["class"],
                         "ASSUMED")


class AcquisitionStatusTest(unittest.TestCase):
    """A likely classification must not be discarded as if nothing were known, and must not open the gate either."""

    FIXED = {"every_channel_moves": False, "every_channel_fixed": True,
             "receiver_coordinate_state": "STATIC",
             "n_shots": 60, "n_channels": 24, "channel_spacing_m": 3.125,
             "array_length_m": 71.9, "trace_sort": {"kind": "shot"}}

    def _tracking(self, verdict, correlation, scale=1.0):
        return {"verdict": verdict, "correlation": correlation, "scale": scale,
                "shots_used": 60, "residual_rms_ms": 0.1,
                "implied_velocity_m_s": 1492.0 / scale, "reason": "fixture"}

    def test_time_that_follows_the_positions_at_the_wrong_rate_is_probable(self):
        got = geometry.classify_acquisition(
            dict(self.FIXED),
            tracking=self._tracking("DOES_NOT_TRACK", 0.995, scale=0.5))
        self.assertEqual(got["candidate"], geometry.ACQ_FIXED_ARRAY)
        self.assertEqual(got["status"], geometry.ACQ_PROBABLE)
        # probable is not established: the gate stays shut
        self.assertEqual(got["kind"], geometry.ACQ_UNDETERMINED)

    def test_time_that_ignores_the_positions_is_established_as_untrustworthy(self):
        got = geometry.classify_acquisition(
            dict(self.FIXED),
            tracking=self._tracking("DOES_NOT_TRACK", 0.1, scale=0.02))
        self.assertEqual(got["candidate"],
                         geometry.ACQ_RECEIVERS_UNTRUSTWORTHY)
        self.assertEqual(got["status"], geometry.ACQ_ESTABLISHED)
        self.assertEqual(got["kind"], geometry.ACQ_RECEIVERS_UNTRUSTWORTHY)

    def test_no_measurement_names_both_alternatives(self):
        got = geometry.classify_acquisition(dict(self.FIXED))
        self.assertEqual(got["status"], geometry.ACQ_STATUS_UNKNOWN)
        self.assertIn(geometry.ACQ_FIXED_ARRAY, got["alternatives"])
        self.assertIn(geometry.ACQ_RECEIVERS_UNTRUSTWORTHY, got["alternatives"])


class FeasibilityStatusTest(unittest.TestCase):
    """Three verdicts, three statuses."""

    def _record(self, verdict):
        from unittest import mock

        import numpy as np

        from sumcp import tools

        manifest = _manifest(**{"dataset.imported": (evidence.PASS, "ok")})
        manifest["dataset_id"] = "fixture"
        result = {
            "REFLECTION_PROCESSING_FEASIBLE": verdict,
            "feasibility_reason": f"fixture reason for {verdict}",
            "agreed_candidates": [], "detection_threshold_x_rms": {},
            "direct_wave_stack_peak": {}, "branches": {}, "notes": ["a caveat"],
        }
        with mock.patch.object(tools, "safe_input_path",
                               side_effect=lambda p: Path(p)), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(tools.sufile, "geometry",
                               return_value={"dt_s": 0.001, "t_start_s": 0.0}), \
             mock.patch.object(tools.geometry, "resolve_coordinates",
                               return_value={
                                   "_scaled": {k: np.arange(40.0)
                                               for k in ("gx", "gy", "sx", "sy")},
                                   "_raw": {"fldr": np.ones(40)}}), \
             mock.patch.object(tools.sufile, "read_traces",
                               return_value=np.zeros((40, 100))), \
             mock.patch.object(tools.reflection, "assess", return_value=result), \
             mock.patch.object(tools.evidence, "load", return_value=manifest), \
             mock.patch.object(tools.evidence, "save"):
            tools.assess_reflection_feasibility("work/x.su", fldr=1,
                                                dataset_id="fixture")
        return manifest["capabilities"]["reflection.processing_feasible"]

    def _record_gather(self, verdict, fldr, manifest=None):
        from unittest import mock

        import numpy as np

        from sumcp import tools

        if manifest is None:
            manifest = _manifest(**{"dataset.imported": (evidence.PASS, "ok")})
            manifest["dataset_id"] = "fixture"
        result = {
            "REFLECTION_PROCESSING_FEASIBLE": verdict,
            "feasibility_reason": f"fixture reason for {verdict}",
            "agreed_candidates": [], "detection_threshold_x_rms": {},
            "direct_wave_stack_peak": {}, "branches": {}, "notes": [],
        }
        with mock.patch.object(tools, "safe_input_path",
                               side_effect=lambda p: Path(p)), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(tools.sufile, "geometry",
                               return_value={"dt_s": 0.001, "t_start_s": 0.0}), \
             mock.patch.object(tools.geometry, "resolve_coordinates",
                               return_value={
                                   "_scaled": {k: np.arange(40.0)
                                               for k in ("gx", "gy", "sx", "sy")},
                                   "_raw": {"fldr": np.full(40, fldr)}}), \
             mock.patch.object(tools.sufile, "read_traces",
                               return_value=np.zeros((40, 100))), \
             mock.patch.object(tools.reflection, "assess", return_value=result), \
             mock.patch.object(tools.evidence, "load", return_value=manifest), \
             mock.patch.object(tools.evidence, "save"):
            out = tools.assess_reflection_feasibility(
                "work/x.su", fldr=fldr, dataset_id="fixture")
        return manifest, out

    def test_the_gather_is_part_of_the_evidence(self):
        """Feasibility is a property of a gather."""
        manifest, _ = self._record_gather("FAIL", 7)
        entry = manifest["capabilities"]["reflection.processing_feasible"]
        self.assertEqual(entry["evidence"]["gather"], {"fldr": 7})

    def test_replacing_another_gathers_answer_says_so(self):
        manifest, _ = self._record_gather("FAIL", 7)
        manifest, out = self._record_gather("INCONCLUSIVE", 9, manifest)
        entry = manifest["capabilities"]["reflection.processing_feasible"]
        self.assertEqual(entry["evidence"]["gather"], {"fldr": 9})
        self.assertIn("Supersedes", entry["notes"][0])
        self.assertIn("'fldr': 7", entry["notes"][0])
        self.assertIn("FAIL", entry["notes"][0])
        self.assertIn("superseded", out)

    def test_remeasuring_the_same_gather_is_not_a_supersession(self):
        manifest, _ = self._record_gather("FAIL", 7)
        manifest, out = self._record_gather("FAIL", 7, manifest)
        self.assertNotIn("superseded", out)

    def test_inconclusive_is_unknown_not_fail(self):
        entry = self._record("INCONCLUSIVE")
        self.assertEqual(entry["status"], evidence.UNKNOWN)
        self.assertEqual(entry["evidence"]["verdict"], "INCONCLUSIVE")

    def test_fail_is_still_fail(self):
        self.assertEqual(self._record("FAIL")["status"], evidence.FAIL)

    def test_pass_is_still_pass(self):
        self.assertEqual(self._record("PASS")["status"], evidence.PASS)

    def test_the_recorded_reason_is_the_outcome_not_the_first_caveat(self):
        from sumcp import overview
        entry = self._record("FAIL")
        self.assertIn("fixture reason", overview._evidence_line(entry))
        self.assertNotIn("a caveat", overview._evidence_line(entry))


class ReceiverCoordinateStateTest(unittest.TestCase):
    """Absent coordinates are a third state, not a kind of static."""

    ABSENT = {"every_channel_moves": False, "every_channel_fixed": True,
              "receiver_coordinate_state": geometry.RX_ABSENT,
              "n_shots": 155, "n_channels": 48, "channel_spacing_m": None,
              "array_length_m": 0.0, "trace_sort": {"kind": "shot"}}

    def test_absent_coordinates_offer_no_alternatives(self):
        got = geometry.classify_acquisition(dict(self.ABSENT))
        self.assertEqual(got["kind"], geometry.ACQ_UNDETERMINED)
        self.assertEqual(got["status"], geometry.ACQ_STATUS_UNKNOWN)
        self.assertEqual(got["alternatives"], [])
        self.assertIn("no receiver geometry at all", got["reason"])

    def test_absent_coordinates_ask_for_external_geometry(self):
        got = geometry.classify_acquisition(dict(self.ABSENT))
        self.assertTrue(any("observer log" in u for u in got["unresolved"]))

    def test_a_tracking_measurement_cannot_rescue_absent_coordinates(self):
        """There is nothing for the arrival time to be consistent WITH."""
        got = geometry.classify_acquisition(
            dict(self.ABSENT),
            tracking={"verdict": "TRACKS", "correlation": 0.99, "scale": 1.0,
                      "shots_used": 155, "residual_rms_ms": 0.1})
        self.assertEqual(got["kind"], geometry.ACQ_UNDETERMINED)

    def test_static_still_offers_the_two_it_cannot_separate(self):
        static = dict(self.ABSENT, receiver_coordinate_state=geometry.RX_STATIC)
        got = geometry.classify_acquisition(static)
        self.assertIn(geometry.ACQ_FIXED_ARRAY, got["alternatives"])
        self.assertIn(geometry.ACQ_RECEIVERS_UNTRUSTWORTHY, got["alternatives"])


class EvidenceOriginTest(unittest.TestCase):
    """The class grades the evidence; the origin names the authority."""

    def test_the_same_class_can_have_different_authority(self):
        from sumcp import claims as C
        logged = C.assumed(50.0, "group interval from the observer log",
                           origin=C.ORIGIN_ACQUISITION_LOG)
        guessed = C.assumed(50.0, "typical for the era",
                            origin=C.ORIGIN_DEFAULT)
        self.assertEqual(logged["class"], guessed["class"])
        self.assertNotEqual(logged["origin"], guessed["origin"])

    def test_a_derived_value_inherits_a_single_origin(self):
        from sumcp import claims as C
        nav = C.observed("lon/lat at SP 6210", "USGS navigation file",
                         origin=C.ORIGIN_NAVIGATION)
        interpolated = C.derived("lon/lat at SP 6207",
                                 "along-track interpolation", inputs=[nav])
        self.assertEqual(interpolated["origin"], C.ORIGIN_NAVIGATION)

    def test_mixed_origins_are_not_claimed_as_one(self):
        from sumcp import claims as C
        nav = C.observed("source xy", "navigation", origin=C.ORIGIN_NAVIGATION)
        log = C.assumed(50.0, "group interval", origin=C.ORIGIN_ACQUISITION_LOG)
        mixed = C.derived("receiver xy", "source plus offset along the track",
                          inputs=[nav, log])
        self.assertEqual(mixed["origin"], C.ORIGIN_UNSTATED)

    def test_an_unknown_origin_is_refused(self):
        from sumcp import claims as C
        with self.assertRaises(ValueError):
            C.assumed(50.0, "somewhere", origin="THE_INTERNET")


class ClassificationStatusTest(unittest.TestCase):
    """FAIL means measured and found wanting."""

    def test_undetermined_is_unknown(self):
        self.assertIsNone(geometry.classification_status(
            {"kind": geometry.ACQ_UNDETERMINED}))

    def test_only_a_measured_negative_is_fail(self):
        self.assertIs(geometry.classification_status(
            {"kind": geometry.ACQ_RECEIVERS_UNTRUSTWORTHY}), False)

    def test_a_named_geometry_is_pass(self):
        self.assertIs(geometry.classification_status(
            {"kind": geometry.ACQ_FIXED_ARRAY}), True)
        self.assertIs(geometry.classification_status(
            {"kind": geometry.ACQ_MOVING_RECEIVERS}), True)

    def test_a_probable_classification_is_unknown_not_fail(self):
        """It is downgraded to undetermined for the gate, which must land on UNKNOWN, writing it FAIL would say
        the geometry was refuted."""
        got = geometry.classify_acquisition(
            {"every_channel_moves": False, "every_channel_fixed": True,
             "receiver_coordinate_state": "STATIC",
             "n_shots": 60, "n_channels": 24, "channel_spacing_m": 3.125,
             "array_length_m": 71.9, "trace_sort": {"kind": "shot"}},
            tracking={"verdict": "DOES_NOT_TRACK", "correlation": 0.99,
                      "scale": 0.5, "shots_used": 60, "residual_rms_ms": 0.1,
                      "implied_velocity_m_s": 2984.0, "reason": "fixture"})
        self.assertEqual(got["status"], geometry.ACQ_PROBABLE)
        self.assertIsNone(geometry.classification_status(got))
