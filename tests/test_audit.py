"""The audit trail."""

from __future__ import annotations

import os
import json
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


from sumcp import config, evidence, provenance, tools   # noqa: E402

FORBIDDEN = ("sunmo", "sustack", "suvelan")


class LogCapture:
    """Point the processing log at a temporary file for the duration."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved = (config.LOG_DIR, config.PROCESSING_LOG)
        config.LOG_DIR = Path(self._dir.name)
        config.PROCESSING_LOG = Path(self._dir.name) / "processing.jsonl"
        return self

    def __exit__(self, *exc):
        config.LOG_DIR, config.PROCESSING_LOG = self._saved
        self._dir.cleanup()
        return False

    def entries(self, kind="tool_call"):
        if not config.PROCESSING_LOG.exists():
            return []
        rows = [json.loads(line) for line in
                config.PROCESSING_LOG.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        return [r for r in rows if kind is None or r.get("kind") == kind]


def manifest_with(**capabilities):
    m = {"dataset_id": "unit-test", "capabilities": {}}
    for name, status in capabilities.items():
        m["capabilities"][name.replace("__", ".")] = {
            "status": status, "evidence": {}, "notes": ["because the test says so"]}
    return m


class EntryShapeTest(unittest.TestCase):
    """One entry per call, with the fields an audit needs."""

    def test_success_lists_commands_and_artifacts(self):
        with LogCapture() as log:
            @provenance.audited("pretend_tool")
            def pretend(dataset_id: str):
                provenance.note_execution("susort", ["susort", "cdp"], 0, 0.1)
                provenance.note_execution("sunmo", ["sunmo", "tnmo=0"], 0, 0.2)
                provenance.note_artifact("work/x/x_nmo.su", "nmo-corrected")
                return {"ok": True}

            pretend(dataset_id="d")
            entry, = log.entries()

        self.assertEqual(entry["tool"], "pretend_tool")
        self.assertEqual(entry["dataset"], "d")
        self.assertEqual(entry["status"], "SUCCESS")
        self.assertEqual(entry["underlying_commands_executed"], ["sunmo", "susort"])
        self.assertEqual(entry["artifacts_created"], ["work/x/x_nmo.su"])
        self.assertIsNone(entry["refusal_reason"])
        self.assertEqual(entry["audit_version"], provenance.AUDIT_VERSION)

    def test_a_program_that_failed_is_still_recorded_as_having_run(self):
        """Exit status is not the question; whether it executed is."""
        with LogCapture() as log:
            @provenance.audited("pretend_tool")
            def pretend():
                provenance.note_execution("sustack", ["sustack"], 1, 0.05)
                return {"ok": False, "error": "sustack exited 1",
                        "error_type": "SURunError"}

            pretend()
            entry, = log.entries()

        self.assertEqual(entry["status"], "ERROR")
        self.assertIn("sustack", entry["underlying_commands_executed"])
        self.assertEqual(entry["commands_detail"][0]["returncode"], 1)


class RefusalTest(unittest.TestCase):
    """A refusal is a log event, and it names what refused."""

    def test_refusal_names_the_deciding_capability(self):
        manifest = manifest_with(geometry__cmp_assigned="PASS",
                                 geometry__fold_valid="FAIL")
        with LogCapture() as log:
            @provenance.audited("sort_cmp")
            def pretend(dataset_id: str):
                try:
                    evidence.require(manifest,
                                     ["geometry.cmp_assigned", "geometry.fold_valid"],
                                     "Sorting into CMP gathers")
                except evidence.PrerequisiteError as exc:
                    return {"ok": False, "error": str(exc),
                            "error_type": "PrerequisiteError"}
                return {"ok": True}

            pretend(dataset_id="adv-a02")
            entry, = log.entries()

        self.assertEqual(entry["status"], "REFUSED")
        self.assertEqual(entry["gate"], "geometry.fold_valid")
        self.assertEqual(entry["gate_status"], "FAIL")
        self.assertEqual(entry["underlying_commands_executed"], [])
        self.assertEqual(entry["artifacts_created"], [])
        self.assertIn("fold_valid", entry["refusal_reason"])

    def test_every_consulted_capability_is_listed_not_only_the_failing_one(self):
        manifest = manifest_with(geometry__cmp_assigned="PASS",
                                 geometry__fold_valid="FAIL")
        with LogCapture() as log:
            @provenance.audited("sort_cmp")
            def pretend():
                try:
                    evidence.require(manifest,
                                     ["geometry.cmp_assigned", "geometry.fold_valid"])
                except evidence.PrerequisiteError:
                    return {"ok": False, "error": "no", "error_type": "PrerequisiteError"}
                return {"ok": True}

            pretend()
            entry, = log.entries()

        checked = {g["capability"]: g["status"] for g in entry["gate_evaluation"]
                   if g["kind"] == "required"}
        self.assertEqual(checked, {"geometry.cmp_assigned": "PASS",
                                   "geometry.fold_valid": "FAIL"})

    def test_prerequisite_error_carries_structured_failures(self):
        manifest = manifest_with(geometry__fold_valid="FAIL")
        with self.assertRaises(evidence.PrerequisiteError) as caught:
            evidence.require(manifest, ["geometry.fold_valid", "nmo.applied"])
        failed = {f["capability"]: f["status"] for f in caught.exception.failed}
        self.assertEqual(failed, {"geometry.fold_valid": "FAIL",
                                  "nmo.applied": "UNKNOWN"})

    def test_a_capability_written_as_FAIL_is_the_deciding_gate(self):
        """build_cmp succeeds as a call while grading the survey unstackable."""
        with LogCapture() as log:
            @provenance.audited("build_cmp")
            def pretend():
                provenance.note_gate("geometry.cmp_assigned", "PASS", "set")
                provenance.note_gate("geometry.fold_valid", "FAIL", "set",
                                     detail=["no NMO leverage"])
                return {"ok": True}

            pretend()
            entry, = log.entries()

        self.assertEqual(entry["status"], "SUCCESS")
        self.assertEqual(entry["gate"], "geometry.fold_valid")
        self.assertEqual(entry["gate_status"], "FAIL")


class CoverageTest(unittest.TestCase):
    """Adding a tool must not be able to forget to log itself."""

    def test_every_public_tool_is_audited_or_deliberately_exempt(self):
        for name in tools.__all__:
            fn = getattr(tools, name)
            audited = getattr(fn, "__wrapped_tool__", None) == name
            exempt = name in tools._AUDIT_EXEMPT
            self.assertTrue(audited or exempt,
                            f"{name} is neither audited nor in _AUDIT_EXEMPT")

    def test_the_exempt_set_holds_only_lookups(self):
        """Nothing that runs a program or writes a file may be exempt."""
        for name in tools._AUDIT_EXEMPT:
            self.assertIn(name, tools.__all__)
        for name in ("build_cmp", "sort_cmp", "pick_velocity", "apply_nmo",
                     "stack_cmp", "dataset_import_segy", "su_run", "su_pipeline",
                     "export_product"):
            self.assertNotIn(name, tools._AUDIT_EXEMPT)


class ForbiddenCommandTest(unittest.TestCase):
    """The claim the suite exists to support, read out of the log."""

    def test_a_refused_call_records_no_forbidden_command(self):
        manifest = manifest_with(velocity__validated="FAIL")
        with LogCapture() as log:
            @provenance.audited("apply_nmo")
            def pretend():
                try:
                    evidence.require(manifest, ["velocity.validated"], "NMO")
                except evidence.PrerequisiteError as exc:
                    return {"ok": False, "error": str(exc),
                            "error_type": "PrerequisiteError"}
                provenance.note_execution("sunmo", ["sunmo"], 0, 1.0)
                return {"ok": True}

            pretend()
            entry, = log.entries()

        self.assertEqual(entry["status"], "REFUSED")
        for command in FORBIDDEN:
            self.assertNotIn(command, entry["underlying_commands_executed"])


if __name__ == "__main__":
    unittest.main()
