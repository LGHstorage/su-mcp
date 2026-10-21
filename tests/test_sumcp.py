"""Unit tests for the SU-MCP package."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# This module already runs against a throwaway SU_MCP_ROOT, so its log is disposable either way; the line is here
# so the isolation is uniform across the suite and visible in one grep.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))


def _reload_package(root: Path):
    """Point the package at a throwaway project root and reload it."""
    os.environ["SU_MCP_ROOT"] = str(root)
    import sumcp
    from sumcp import config, paths, provenance, runner, sufile, suenv, tools
    for module in (config, paths, provenance, runner, sufile, suenv, tools, sumcp):
        importlib.reload(module)
    from sumcp import tools as reloaded_tools
    return reloaded_tools


class SUProjectTestCase(unittest.TestCase):
    """Base case: a temporary project with one small synthetic SU file."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("suplane") is None and not os.environ.get("CWPROOT"):
            raise unittest.SkipTest("Seismic Unix is not on this system")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs"):
            (cls.root / name).mkdir()

        import sys
        sys.path.insert(0, str(REPO))
        cls.tools = _reload_package(cls.root)
        from sumcp import config, paths, provenance, runner, sufile
        cls.config, cls.paths = config, paths
        cls.provenance, cls.runner, cls.sufile = provenance, runner, sufile

        suplane = cls._program("suplane")
        with open(cls.root / "raw" / "test.su", "wb") as out:
            subprocess.run([suplane, "nt=200", "ntr=32", "dt=0.004"],
                           stdout=out, stderr=subprocess.DEVNULL, check=True)

    @staticmethod
    def _program(name):
        from sumcp import suenv
        path = suenv.find_program(name)
        if path is None:
            raise unittest.SkipTest(f"{name} not found")
        return path

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("SU_MCP_ROOT", None)


class TestPathPolicy(SUProjectTestCase):

    def test_readable_paths_resolve(self):
        p = self.paths.safe_input_path("raw/test.su")
        self.assertTrue(p.exists())
        self.assertTrue(str(p).startswith(str(self.root)))

    def test_absolute_outside_root_rejected(self):
        for bad in ("/etc/passwd", "/tmp/x.su"):
            with self.assertRaises(self.paths.PathPolicyError):
                self.paths.safe_input_path(bad)

    def test_traversal_rejected(self):
        for bad in ("../../etc/passwd", "work/../../etc/shadow", "raw/../../x"):
            with self.assertRaises(self.paths.PathPolicyError):
                self.paths.safe_output_path(bad)

    def test_raw_is_not_writable(self):
        with self.assertRaises(self.paths.PathPolicyError):
            self.paths.safe_output_path("raw/overwrite.su")

    def test_symlink_escape_rejected(self):
        link = self.root / "work" / "escape"
        if not link.exists():
            link.symlink_to("/etc")
        with self.assertRaises(self.paths.PathPolicyError):
            self.paths.safe_output_path("work/escape/passwd")

    def test_existing_output_needs_overwrite(self):
        target = self.root / "work" / "exists.su"
        target.write_bytes(b"x")
        with self.assertRaises(self.paths.PathPolicyError):
            self.paths.safe_output_path("work/exists.su")
        self.assertTrue(self.paths.safe_output_path("work/exists.su", overwrite=True))


class TestParameterPolicy(SUProjectTestCase):

    def test_lists_become_comma_separated(self):
        self.assertEqual(self.runner.validate_params({"f": [10, 20, 120, 150]}),
                         ["f=10,20,120,150"])

    def test_floats_avoid_exponent_form(self):
        self.assertEqual(self.runner.validate_params({"wagc": 0.00005}), ["wagc=0.00005"])

    def test_shell_metacharacters_rejected(self):
        for bad in ({"f": "1;rm -rf /"}, {"f": "$(id)"}, {"f": "a|b"}, {"f": "a b"},
                    {"f": "`id`"}, {"f": "x>y"}):
            with self.assertRaises(self.runner.ParameterError):
                self.runner.validate_params(bad)

    def test_path_valued_parameters_rejected(self):
        for bad in ({"f": "../../etc/passwd"}, {"par": "x"}, {"outpar": "y"},
                    {"vfile": "z"}):
            with self.assertRaises(self.runner.ParameterError):
                self.runner.validate_params(bad)

    def test_bad_key_rejected(self):
        for bad in ({"2f": 1}, {"a b": 1}, {"-f": 1}, {"": 1}):
            with self.assertRaises(self.runner.ParameterError):
                self.runner.validate_params(bad)

    def test_allowlist(self):
        self.assertTrue(self.runner.resolve_command("sufilter"))
        for blocked in ("sustack", "sunmo", "suvelan", "bash", "rm"):
            with self.assertRaises(self.runner.CommandNotAllowed):
                self.runner.resolve_command(blocked)


class TestSUFileReader(SUProjectTestCase):

    def test_geometry_matches_surange(self):
        path = self.root / "raw" / "test.su"
        geom = self.sufile.geometry(path)
        self.assertEqual(geom["ns"], 200)
        self.assertEqual(geom["dt_us"], 4000)
        self.assertEqual(geom["ntr"], 32)
        text = self.runner.capture_text("surange", stdin_path=path)
        self.assertIn("32 traces", text)
        self.assertIn("ns       200", text)

    def test_scan_reports_keys(self):
        report = self.sufile.scan(self.root / "raw" / "test.su")
        self.assertIn("tracl", report["keys"])
        self.assertEqual(report["keys"]["tracl"]["min"], 1)
        self.assertEqual(report["keys"]["tracl"]["max"], 32)
        self.assertFalse(report["has_cdp"])

    def test_read_gather_shape(self):
        data, headers = self.sufile.read_gather(self.root / "raw" / "test.su", 0, 10)
        self.assertEqual(data.shape, (10, 200))
        self.assertEqual(len(headers["tracl"]), 10)

    def test_byte_order_is_detected_not_assumed(self):
        """An XDR-enabled SU build writes big-endian files; both must read alike."""
        import numpy as np
        native = self.root / "raw" / "test.su"
        swapped = self.root / "work" / "test_swapped.su"
        info = self.sufile.rewrite_byte_order(native, swapped)
        self.assertNotEqual(info["from_byte_order"], info["to_byte_order"])

        a, b = self.sufile.geometry(native), self.sufile.geometry(swapped)
        self.assertNotEqual(a["byte_order"], b["byte_order"])
        for key in ("ns", "dt_us", "ntr"):
            self.assertEqual(a[key], b[key], key)

        sa, sb = self.sufile.scan(native), self.sufile.scan(swapped)
        self.assertEqual(sa["keys"], sb["keys"])
        da, _ = self.sufile.read_gather(native, 0, 32)
        db, _ = self.sufile.read_gather(swapped, 0, 32)
        self.assertTrue(np.array_equal(da, db))

    def test_swapping_twice_returns_the_original(self):
        once = self.root / "work" / "once.su"
        twice = self.root / "work" / "twice.su"
        self.sufile.rewrite_byte_order(self.root / "raw" / "test.su", once)
        self.sufile.rewrite_byte_order(once, twice)
        self.assertEqual((self.root / "raw" / "test.su").read_bytes(),
                         twice.read_bytes())

    def test_status_reports_the_build_byte_order(self):
        from sumcp import suenv
        info = suenv.su_output_byte_order()
        self.assertIn(info["detected"], ("little", "big"))
        self.assertEqual(info["xdr_build"], info["detected"] != info["machine"])

    def test_delrt_sets_the_start_time(self):
        """suwind tmin= shifts the record start; the axis must follow."""
        r = self.tools.su_pipeline("raw/test.su", "work/delayed.su",
                                   [{"command": "suwind",
                                     "params": {"tmin": 0.2, "tmax": 0.6}}],
                                   overwrite=True)
        self.assertTrue(r["ok"], r)
        geom = self.sufile.geometry(self.root / "work" / "delayed.su")
        self.assertEqual(geom["delrt_ms"], 200)
        self.assertAlmostEqual(geom["t_start_s"], 0.2)
        self.assertAlmostEqual(geom["t_end_s"], 0.2 + geom["record_length_s"])
        preview = self.tools.su_preview("work/delayed.su", "qc/delayed.png", count=8)
        self.assertAlmostEqual(preview["t_start_s"], 0.2)
        self.assertGreater(preview["t_end_s"], 0.2)
        # the original has no delay
        self.assertEqual(self.sufile.geometry(self.root / "raw" / "test.su")["delrt_ms"], 0)

    def test_non_su_file_raises(self):
        junk = self.root / "work" / "junk.su"
        junk.write_bytes(b"\x00" * 1000)
        with self.assertRaises(self.sufile.SUFormatError):
            self.sufile.geometry(junk)


class TestExecution(SUProjectTestCase):

    def test_single_run_produces_output(self):
        r = self.tools.su_run("sufilter", "raw/test.su", "work/bp.su",
                              {"f": [5, 10, 60, 80], "amps": [0, 1, 1, 0]},
                              overwrite=True)
        self.assertTrue(r["ok"], r)
        out = self.root / "work" / "bp.su"
        self.assertEqual(self.sufile.geometry(out)["ntr"], 32)
        self.assertIn("< raw/test.su > work/bp.su", r["shell_equivalent"])

    def test_pipeline_matches_equivalent_shell_chain(self):
        steps = [{"command": "suwind", "params": {"tmin": 0.0, "tmax": 0.5}},
                 {"command": "sugain", "params": {"tpow": 2}}]
        r = self.tools.su_pipeline("raw/test.su", "work/chain.su", steps, overwrite=True)
        self.assertTrue(r["ok"], r)
        reference = self.root / "work" / "reference.su"
        chain = (f'{self._program("suwind")} tmin=0.0 tmax=0.5 < {self.root}/raw/test.su '
                 f'| {self._program("sugain")} tpow=2 > {reference}')
        subprocess.run(["bash", "-c", chain], check=True, stderr=subprocess.DEVNULL)
        self.assertEqual((self.root / "work" / "chain.su").read_bytes(),
                         reference.read_bytes())

    def test_failed_step_leaves_no_partial_output(self):
        r = self.tools.su_run("suwind", "raw/test.su", "work/bad.su",
                              {"tmin": 9.0, "tmax": 1.0}, overwrite=True)
        if not r["ok"]:
            self.assertFalse((self.root / "work" / "bad.su").exists())

    def test_rejections_are_reported_not_raised(self):
        r = self.tools.su_run("sustack", "raw/test.su", "work/x.su")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_type"], "CommandNotAllowed")
        r = self.tools.su_run("sufilter", "raw/test.su", "/etc/x.su")
        self.assertEqual(r["error_type"], "PathPolicyError")
        r = self.tools.su_run("sufilter", "raw/missing.su", "work/x.su")
        self.assertEqual(r["error_type"], "FileNotFoundError")


class TestProvenance(SUProjectTestCase):

    def test_every_execution_is_logged_with_a_hash(self):
        # Since audit-0.2 every tool call also writes a "tool_call" entry; the claim tested here is about the
        # su_run execution records.
        runs = lambda: [e for e in self.provenance.read_log(10000)
                        if e.get("kind") == "su_run"]
        before = len(runs())
        self.tools.su_run("sugain", "raw/test.su", "work/gain.su", {"tpow": 1},
                          overwrite=True)
        self.tools.su_run("sustack", "raw/test.su", "work/never.su")   # rejected
        entries = runs()
        self.assertEqual(len(entries), before + 2)
        success = [e for e in entries if e["status"] == "success"][-1]
        self.assertEqual(success["kind"], "su_run")
        self.assertIn("sha256", success["output_file"])
        self.assertEqual(len(success["output_file"]["sha256"]), 64)
        rejected = [e for e in entries if e["status"] == "rejected"][-1]
        self.assertEqual(rejected["error_type"], "CommandNotAllowed")

    def test_log_is_valid_jsonl(self):
        with open(self.config.PROCESSING_LOG, encoding="utf-8") as fh:
            for line in fh:
                json.loads(line)

    def test_hash_reproduces_for_identical_processing(self):
        a = self.tools.su_run("sugain", "raw/test.su", "work/h1.su", {"tpow": 2},
                              overwrite=True)
        b = self.tools.su_run("sugain", "raw/test.su", "work/h2.su", {"tpow": 2},
                              overwrite=True)
        self.assertTrue(a["ok"] and b["ok"])
        entries = {e["output"]: e for e in self.provenance.read_log(10000)
                   if e.get("kind") == "su_run" and e.get("status") == "success"}
        self.assertEqual(entries["work/h1.su"]["output_file"]["sha256"],
                         entries["work/h2.su"]["output_file"]["sha256"])


class TestPreview(SUProjectTestCase):

    def test_png_is_written(self):
        r = self.tools.su_preview("raw/test.su", "qc/test.png", count=32)
        self.assertTrue(r["ok"], r)
        png = self.root / "qc" / "test.png"
        self.assertTrue(png.exists() and png.stat().st_size > 5000)
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_preview_must_be_png_in_project(self):
        self.assertFalse(self.tools.su_preview("raw/test.su", "qc/test.jpg")["ok"])
        self.assertFalse(self.tools.su_preview("raw/test.su", "/tmp/out.png")["ok"])

    def test_missing_gather_is_reported(self):
        r = self.tools.su_preview("raw/test.su", "qc/none.png", fldr=9999)
        self.assertFalse(r["ok"])


class TestInspect(SUProjectTestCase):

    def test_inspect_returns_structure_and_notes(self):
        r = self.tools.su_inspect("raw/test.su")
        self.assertTrue(r["ok"])
        self.assertEqual(r["structured"]["ntr"], 32)
        self.assertIn("32 traces", r["surange"])
        self.assertTrue(any("cdp" in n for n in r["notes"]))

    def test_help_and_search(self):
        self.assertIn("SUFILTER", self.tools.su_help("sufilter")["doc"])
        self.assertFalse(self.tools.su_help("no_such_program_xyz")["ok"])
        self.assertTrue(self.tools.su_search("bandpass")["ok"])
        self.assertFalse(self.tools.su_search("x", mode="bogus")["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
