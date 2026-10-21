"""Unit tests for the v0.2 dataset layer: SEG-Y diagnosis, import, evidence."""

from __future__ import annotations

import importlib
import os
import struct
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



def swap_segy(src: Path, dst: Path) -> None:
    """Rewrite a SEG-Y file in the opposite byte order (see sumcp.segy)."""
    from sumcp import segy as _segy
    _segy.rewrite_byte_order(src, dst)


class DatasetTestCase(unittest.TestCase):
    """Temporary project holding one small SU file and its SEG-Y conversions."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs", "state"):
            (cls.root / name).mkdir()
        os.environ["SU_MCP_ROOT"] = str(cls.root)

        import sumcp
        from sumcp import (config, evidence, ingest, paths, provenance, runner,
                           segy, sufile, suenv, tools)
        for module in (config, paths, provenance, suenv, runner, sufile, segy,
                       evidence, ingest, tools, sumcp):
            importlib.reload(module)
        from sumcp import (config, evidence, ingest, paths, segy,  # noqa: F811
                           sufile, suenv, tools)
        cls.config, cls.paths, cls.segy = config, paths, segy
        cls.evidence, cls.ingest, cls.tools, cls.sufile = evidence, ingest, tools, sufile

        if suenv.find_program("suplane") is None:
            raise unittest.SkipTest("Seismic Unix is not on this system")

        def program(name):
            path = suenv.find_program(name)
            if path is None:
                raise unittest.SkipTest(f"{name} not found")
            return path

        su = cls.root / "raw" / "test.su"
        with open(su, "wb") as out:
            subprocess.run([program("suplane"), "nt=200", "ntr=32", "dt=0.004"],
                           stdout=out, stderr=subprocess.DEVNULL, check=True)
        # give it coordinates so the header-availability report has something to say
        moved = cls.root / "raw" / "geom.su"
        with open(su, "rb") as fin, open(moved, "wb") as fout:
            p1 = subprocess.Popen([program("suchw"), "key1=sx", "key2=tracl",
                                   "a=0", "b=50", "c=0", "d=1"],
                                  stdin=fin, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
            subprocess.run([program("suchw"), "key1=gx", "key2=tracl",
                            "a=1000", "b=25", "c=0", "d=1"],
                           stdin=p1.stdout, stdout=fout, stderr=subprocess.DEVNULL,
                           check=True)
            p1.wait()
        moved.replace(su)

        hdr, bhdr = cls.root / "work" / "h", cls.root / "work" / "b"
        with open(su, "rb") as fin:
            subprocess.run([program("segyhdrs"), f"hfile={hdr}", f"bfile={bhdr}"],
                           stdin=fin, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        be = cls.root / "raw" / "test_be.sgy"
        with open(su, "rb") as fin:
            subprocess.run([program("segywrite"), f"tape={be}",
                            f"hfile={hdr}", f"bfile={bhdr}"],
                           stdin=fin, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        # The little-endian fixture is made by swapping the big-endian one in Python rather than with segywrite's
        # endian= flag: what that flag produces depends on how the local SU was built (XDR or not), and a fixture
        # must not depend on that.
        if cls.segy.diagnose(be)["byte_order"] != "big":
            swap_segy(be, cls.root / "raw" / "tmp.sgy")
            (cls.root / "raw" / "tmp.sgy").replace(be)
        swap_segy(be, cls.root / "raw" / "test_le.sgy")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("SU_MCP_ROOT", None)

    def fresh(self, dataset_id):
        self.evidence.manifest_path(dataset_id).unlink(missing_ok=True)
        return dataset_id


class TestSEGYDiagnosis(DatasetTestCase):

    def test_big_endian_detected_with_evidence(self):
        d = self.segy.diagnose(self.root / "raw" / "test_be.sgy")
        self.assertEqual(d["byte_order"], "big")
        self.assertEqual(d["ns"], 200)
        self.assertEqual(d["dt_us"], 4000)
        self.assertEqual(d["traces_estimated"], 32)
        self.assertEqual(d["sample_format_code"], 1)
        self.assertGreater(d["byte_order_evidence"]["big"]["score"],
                           d["byte_order_evidence"]["little"]["score"])

    def test_little_endian_detected(self):
        d = self.segy.diagnose(self.root / "raw" / "test_le.sgy")
        self.assertEqual(d["byte_order"], "little")
        self.assertEqual(d["ns"], 200)
        self.assertEqual(d["traces_estimated"], 32)

    def test_textual_header_is_decoded(self):
        d = self.segy.diagnose(self.root / "raw" / "test_be.sgy")
        self.assertIn(d["textual_header_encoding"], ("ebcdic", "ascii"))
        self.assertTrue(d["textual_header"].strip())

    def test_trace_header_disagreement_is_reported(self):
        """Corrupt ns in the binary header only; the first trace must give it away."""
        src = (self.root / "raw" / "test_be.sgy").read_bytes()
        broken = bytearray(src)
        struct.pack_into(">H", broken, 3200 + 20, 199)      # binary header ns
        path = self.root / "raw" / "ns_mismatch.sgy"
        path.write_bytes(bytes(broken))
        d = self.segy.diagnose(path)
        self.assertTrue(any("first trace header says ns=200" in w for w in d["warnings"]),
                        d["warnings"])

    def test_the_two_fixtures_hold_the_same_survey(self):
        be = self.segy.diagnose(self.root / "raw" / "test_be.sgy")
        le = self.segy.diagnose(self.root / "raw" / "test_le.sgy")
        self.assertEqual(be["byte_order"], "big")
        self.assertEqual(le["byte_order"], "little")
        for key in ("ns", "dt_us", "sample_format_code", "traces_estimated"):
            self.assertEqual(be[key], le[key], key)

    def test_non_segy_is_refused(self):
        junk = self.root / "raw" / "junk.sgy"
        junk.write_bytes(b"\x00" * 8000)
        with self.assertRaises(self.segy.SEGYError):
            self.segy.diagnose(junk)


class TestEvidenceModel(DatasetTestCase):

    def test_capability_vocabulary_is_closed(self):
        m = self.evidence.create(self.fresh("vocab"), self.root / "raw" / "test.su",
                                 "su", "run1")
        with self.assertRaises(self.evidence.DatasetError):
            self.evidence.set_capability(m, "geometry.definitely_fine",
                                         self.evidence.PASS, {}, "v", "run1")

    def test_require_names_what_is_missing_and_why(self):
        m = self.evidence.create(self.fresh("req"), self.root / "raw" / "test.su",
                                 "su", "run1")
        self.evidence.set_capability(m, "geometry.cmp_assigned", self.evidence.FAIL,
                                     {"cdp_state": "zero"}, "geom-0.3", "run1",
                                     notes=["cdp is all zero"])
        with self.assertRaises(self.evidence.PrerequisiteError) as ctx:
            self.evidence.require(m, ["geometry.cmp_assigned", "velocity.model_available"],
                                  "Stacking")
        message = str(ctx.exception)
        self.assertIn("geometry.cmp_assigned: FAIL", message)
        self.assertIn("cdp is all zero", message)
        self.assertIn("velocity.model_available: never evaluated", message)

    def test_require_passes_when_satisfied(self):
        m = self.evidence.create(self.fresh("req2"), self.root / "raw" / "test.su",
                                 "su", "run1")
        self.evidence.set_capability(m, "dataset.imported", self.evidence.PASS,
                                     {}, "v", "run1")
        self.evidence.require(m, ["dataset.imported"], "Anything")

    def test_manifest_round_trips(self):
        did = self.fresh("rt")
        m = self.evidence.create(did, self.root / "raw" / "test.su", "su", "run1", "d")
        self.evidence.add_artifact(m, "su", self.root / "raw" / "test.su",
                                   "imported", "run1", parents=["raw/test.su"])
        self.evidence.save(m)
        again = self.evidence.load(did)
        self.assertEqual(again["artifacts"]["su"]["parents"], ["raw/test.su"])
        self.assertEqual(len(again["artifacts"]["su"]["sha256"]), 64)
        self.assertIn(did, self.evidence.list_datasets())

    def test_bad_dataset_ids_refused(self):
        for bad in ("../escape", "UPPER", "with space", "", "x" * 80, "state/x"):
            with self.assertRaises(self.evidence.DatasetError):
                self.evidence.manifest_path(bad)

    def test_state_dir_is_not_writable_through_su_run(self):
        with self.assertRaises(self.paths.PathPolicyError):
            self.paths.safe_output_path("state/datasets/line01.json")


class TestImport(DatasetTestCase):

    def test_segy_import_verifies_against_the_source(self):
        did = self.fresh("imp")
        m = self.ingest.import_segy(did, "raw/test_be.sgy", "big-endian fixture")
        statuses = {k: v["status"] for k, v in m["capabilities"].items()}
        for name in ("dataset.registered", "dataset.imported", "headers.parsed",
                     "headers.sampling_consistent", "headers.trace_count_consistent"):
            self.assertEqual(statuses[name], self.evidence.PASS, (name, statuses))
        check = m["capabilities"]["headers.sampling_consistent"]["evidence"]
        self.assertEqual(check["ns"]["segy"], check["ns"]["su"])
        self.assertEqual(check["checked_against"], "SEG-Y binary header")

    def test_little_endian_import_produces_the_same_data(self):
        import numpy as np
        be = self.ingest.import_segy(self.fresh("impbe2"), "raw/test_be.sgy")
        le = self.ingest.import_segy(self.fresh("imple2"), "raw/test_le.sgy")
        a, _ = self.sufile.read_gather(self.root / be["artifacts"]["su"]["path"], 0, 32)
        b, _ = self.sufile.read_gather(self.root / le["artifacts"]["su"]["path"], 0, 32)
        self.assertTrue(np.allclose(a, b))

    def test_import_is_faithful_to_the_original_su_file(self):
        import numpy as np
        m = self.ingest.import_segy(self.fresh("fidelity"), "raw/test_be.sgy")
        original, _ = self.sufile.read_gather(self.root / "raw" / "test.su", 0, 32)
        imported, _ = self.sufile.read_gather(
            self.root / m["artifacts"]["su"]["path"], 0, 32)
        scale = np.abs(original).max() or 1.0
        # format 1 is IBM float, so equality is to that format's precision
        self.assertLess(np.abs(imported - original).max() / scale, 1e-6)

    def test_duplicate_dataset_id_refused(self):
        did = self.fresh("dup")
        self.ingest.import_segy(did, "raw/test_be.sgy")
        with self.assertRaises(self.evidence.DatasetError):
            self.ingest.import_segy(did, "raw/test_be.sgy")

    def test_artifacts_and_lineage_recorded(self):
        m = self.ingest.import_segy(self.fresh("lineage"), "raw/test_be.sgy")
        self.assertIn("su", m["artifacts"])
        self.assertIn("textual_header", m["artifacts"])
        self.assertIn("import_report", m["artifacts"])
        self.assertEqual(m["artifacts"]["su"]["parents"], ["raw/test_be.sgy"])

    def test_register_su_without_conversion(self):
        did = self.fresh("plain")
        m = self.ingest.register_su(did, "raw/test.su", "already SU")
        self.assertEqual(m["source"]["kind"], "su")
        self.assertEqual(self.evidence.capability_status(m, "dataset.imported"),
                         self.evidence.PASS)
        self.assertEqual(self.evidence.capability_status(m, "geometry.validated"),
                         self.evidence.UNKNOWN)

    def test_header_availability_distinguishes_zero_from_varying(self):
        m = self.ingest.register_su(self.fresh("avail"), "raw/test.su")
        avail = m["capabilities"]["headers.parsed"]["evidence"]["availability"]
        self.assertEqual(avail["sx"]["state"], "varying")
        self.assertEqual(avail["cdp"]["state"], "zero")
        self.assertEqual(avail["sy"]["state"], "zero")

    def test_missing_cdp_is_called_out_not_silently_accepted(self):
        m = self.ingest.register_su(self.fresh("nocdp"), "raw/test.su")
        outlook = m["capabilities"]["headers.parsed"]["evidence"]["outlook"]
        self.assertEqual(outlook["cdp_state"], "zero")
        self.assertTrue(any("CMP bins must be computed" in n for n in outlook["notes"]))

    def test_populated_cdp_is_not_treated_as_correct(self):
        """A dataset with a cdp header must still not claim geometry is valid."""
        suchw = None
        from sumcp import suenv
        suchw = suenv.find_program("suchw")
        if suchw is None:
            self.skipTest("suchw not found")
        src = self.root / "raw" / "test.su"
        withcdp = self.root / "raw" / "withcdp.su"
        with open(src, "rb") as fin, open(withcdp, "wb") as fout:
            subprocess.run([suchw, "key1=cdp", "key2=tracl", "a=0", "b=1", "c=0", "d=1"],
                           stdin=fin, stdout=fout, stderr=subprocess.DEVNULL, check=True)
        m = self.ingest.register_su(self.fresh("hascdp"), "raw/withcdp.su")
        outlook = m["capabilities"]["headers.parsed"]["evidence"]["outlook"]
        self.assertEqual(outlook["cdp_state"], "varying")
        self.assertTrue(any("not evidence that it is correct" in n
                            for n in outlook["notes"]), outlook["notes"])
        self.assertEqual(self.evidence.capability_status(m, "geometry.cmp_assigned"),
                         self.evidence.UNKNOWN)


class TestDatasetTools(DatasetTestCase):

    def test_tools_report_failures_rather_than_raising(self):
        self.assertFalse(self.tools.dataset_manifest("nope")["ok"])
        self.assertFalse(self.tools.segy_inspect("raw/test.su")["ok"])
        self.assertFalse(self.tools.dataset_import_segy("bad id", "raw/test_be.sgy")["ok"])
        self.assertFalse(self.tools.dataset_register_su("x", "/etc/passwd")["ok"])

    def test_manifest_sections(self):
        did = self.fresh("sections")
        self.tools.dataset_register_su(did, "raw/test.su")
        self.assertIn("capabilities_pass", self.tools.dataset_manifest(did))
        caps = self.tools.dataset_manifest(did, "capabilities")
        self.assertIn("vocabulary", caps)
        self.assertIn("headers.parsed", caps["capabilities"])
        self.assertIn("artifacts", self.tools.dataset_manifest(did, "artifacts"))
        self.assertIn("history", self.tools.dataset_manifest(did, "history"))
        self.assertFalse(self.tools.dataset_manifest(did, "nonsense")["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
