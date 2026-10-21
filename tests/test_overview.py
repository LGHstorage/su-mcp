"""Where the survey stands, and the difference between refused and unasked."""

from __future__ import annotations

import os
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
# Every tool call writes an audit entry now, so the suite gets its own log: test runs in logs/processing.jsonl
# would corrupt the record the adversarial suite reads to decide whether a forbidden program ran.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))


from sumcp import evidence, overview   # noqa: E402


def _manifest(dataset_id, **caps):
    manifest = {"dataset_id": dataset_id, "description": dataset_id,
                "source": {"path": f"raw/{dataset_id}.segy"},
                "capabilities": {}, "artifacts": {}, "updated": "now"}
    for name, spec in caps.items():
        name = name.replace("__", ".")
        status, facts, notes = spec
        evidence.set_capability(manifest, name, status, facts, "test", "run",
                                notes=notes)
    return manifest


PASSED = (evidence.PASS, {}, [])


def _through(*names):
    return {n.replace(".", "__"): PASSED for n in names}


UP_TO_GEOMETRY = _through(
    "dataset.imported", "headers.parsed",
    "geometry.coordinate_scale_resolved",
    "geometry.receiver_positions_trustworthy",
    "geometry.acquisition_classified")


class StandingTest(unittest.TestCase):

    def _survey(self, manifests):
        with mock.patch.object(overview.evidence, "list_datasets",
                               return_value=list(manifests)), \
             mock.patch.object(overview.evidence, "load",
                               side_effect=lambda d: manifests[d]):
            return overview.survey()

    def test_a_refusal_is_not_listed_as_work_outstanding(self):
        refused = _manifest("d001", **UP_TO_GEOMETRY,
                            reflection__processing_feasible=(
                                evidence.FAIL, {},
                                ["no candidate survived all three branches; "
                                 "detection limit 0.4x the record RMS"]))
        got = self._survey({"d001": refused})
        line = got["lines"][0]
        self.assertTrue(line["standing"]["refused"])
        self.assertFalse(line["standing"]["unmeasured"])
        self.assertEqual(got["refused"][0]["dataset_id"], "d001")
        self.assertIn("detection limit", got["refused"][0]["because"])

    def test_an_unasked_question_is_not_listed_as_a_refusal(self):
        untested = _manifest("d006", **UP_TO_GEOMETRY)
        got = self._survey({"d006": untested})
        line = got["lines"][0]
        self.assertTrue(line["standing"]["unmeasured"])
        self.assertFalse(line["standing"]["refused"])
        self.assertEqual(got["refused"], [])
        self.assertEqual(line["standing"]["blocked_on"],
                         "reflection.processing_feasible")

    def test_a_refusal_behind_the_block_is_not_lost(self):
        """The bug survey_overview found in itself on its first real run: d001ch1 was stopped early by an
        unanswered question while a LATER step already held a measured FAIL, and reading only the blocking
        step reported the survey as having refused nothing."""
        manifest = _manifest(
            "d001ch1", **_through("dataset.imported", "headers.parsed",
                                  "geometry.coordinate_scale_resolved"),
            geometry__receiver_positions_trustworthy=(
                evidence.UNKNOWN, {},
                ["either a fixed array or copied headers"]),
            reflection__processing_feasible=(
                evidence.FAIL, {},
                ["detection limit 0.4x the record RMS"]))
        got = self._survey({"d001ch1": manifest})
        standing = got["lines"][0]["standing"]
        self.assertEqual(standing["blocked_on"],
                         "geometry.receiver_positions_trustworthy")
        self.assertTrue(standing["refused"])
        self.assertIn("detection limit", standing["refusals"][0]["because"])
        self.assertIn("Answering the block does not undo that",
                      standing["note"])
        self.assertEqual(got["refused"][0]["at"],
                         "reflection.processing_feasible")

    def test_the_array_fit_is_never_named_with_one_line(self):
        """Called on a single line it cannot answer, so printing it that way names a call that does nothing."""
        manifest = _manifest(
            "d006", **_through("dataset.imported", "headers.parsed",
                               "geometry.coordinate_scale_resolved"))
        got = self._survey({"d006": manifest})
        action = got["lines"][0]["standing"]["next_action"]
        self.assertTrue(action.startswith('fit_array_geometry(["d006"'))
        self.assertIn("shares this array", action)

    def test_the_next_action_is_a_call_not_a_wish(self):
        got = self._survey({"d006": _manifest("d006", **UP_TO_GEOMETRY)})
        self.assertEqual(got["lines"][0]["standing"]["next_action"],
                         "assess_reflection_feasibility(d006)")

    def test_a_finished_line_says_so(self):
        done = _manifest("viking", **_through(*[n for n, _, _ in overview.TRACK]))
        got = self._survey({"viking": done})
        self.assertEqual(got["reached_a_stack"], ["viking"])
        self.assertIsNone(got["lines"][0]["standing"]["blocked_on"])

    def test_lines_are_ordered_by_how_far_they_got(self):
        manifests = {
            "far": _manifest("far", **UP_TO_GEOMETRY),
            "near": _manifest("near", **_through("dataset.imported")),
        }
        got = self._survey(manifests)
        self.assertEqual([r["dataset_id"] for r in got["lines"]],
                         ["far", "near"])

    def test_a_jointly_fitted_array_is_reported_once_for_the_group(self):
        facts = {"verdict": "RESOLVED", "cause": "per-channel recording delay",
                 "spacing_scale": {"value": 0.986},
                 "channel_delay_ms": {"value": 0.31},
                 "lines_fitted": ["d006", "d007"],
                 "lines_used": ["d001", "d006", "d007"]}
        manifests = {
            name: _manifest(name, **UP_TO_GEOMETRY,
                            geometry__array_geometry_resolved=(
                                evidence.PASS, facts, []))
            for name in ("d001", "d006", "d007")}
        got = self._survey(manifests)
        self.assertEqual(len(got["arrays"]), 1)
        self.assertEqual(got["arrays"][0]["lines"], ["d001", "d006", "d007"])
        self.assertEqual(got["arrays"][0]["cause"],
                         "per-channel recording delay")

    def test_open_questions_come_from_the_evidence_not_from_prose(self):
        manifest = _manifest(
            "d001", **UP_TO_GEOMETRY,
            geometry__array_geometry_resolved=(
                evidence.PASS,
                {"what_would_answer_it": "a line whose source track crosses "
                                         "the array"}, []))
        got = self._survey({"d001": manifest})
        notes = [q["note"] for q in got["lines"][0]["open_questions"]]
        self.assertTrue(any("crosses the array" in n for n in notes))

    def test_an_unreadable_manifest_is_reported_not_swallowed(self):
        def boom(dataset_id):
            raise evidence.DatasetError("corrupt")
        with mock.patch.object(overview.evidence, "list_datasets",
                               return_value=["bad"]), \
             mock.patch.object(overview.evidence, "load", side_effect=boom):
            got = overview.survey()
        self.assertEqual(got["unreadable"][0]["dataset_id"], "bad")
        self.assertEqual(got["lines"], [])


if __name__ == "__main__":
    unittest.main()
