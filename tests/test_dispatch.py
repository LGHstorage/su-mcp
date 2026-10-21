"""The worker and job layer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
# Every tool call writes an audit entry now, so the suite gets its own log: test runs in logs/processing.jsonl
# would corrupt the record the adversarial suite reads to decide whether a forbidden program ran.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))



class WorkerTest(unittest.TestCase):

    def _worker(self, request: dict):
        return subprocess.run(
            [sys.executable, "-m", "sumcp.worker"], input=json.dumps(request),
            capture_output=True, text=True, cwd=str(REPO), timeout=120)

    def test_stdout_carries_only_the_result(self):
        done = self._worker({"tool": "su_status", "arguments": {}})
        payload = json.loads(done.stdout)      # raises if anything else leaked
        self.assertIn("ok", payload)

    def test_only_declared_tools_are_reachable(self):
        """getattr on the tools module would otherwise expose every import in it, os, subprocess, Path, as a
        callable tool name."""
        for name in ("os", "subprocess", "config", "evidence", "_fail"):
            with self.subTest(name=name):
                payload = json.loads(self._worker(
                    {"tool": name, "arguments": {}}).stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error_type"], "UnknownTool")

    def test_a_raising_tool_comes_back_as_a_refusal(self):
        payload = json.loads(self._worker(
            {"tool": "su_help", "arguments": {"nonexistent_argument": 1}}).stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)


class DispatchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs", "state", "jobs", "tmp"):
            (cls.root / name).mkdir()
        os.environ["SU_MCP_ROOT"] = str(cls.root)
        os.environ["SU_MCP_RUNTIME"] = str(cls.root)
        import importlib
        from sumcp import config, dispatch, paths
        for module in (config, paths, dispatch):
            importlib.reload(module)
        cls.config, cls.dispatch = config, dispatch

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("SU_MCP_ROOT", None)
        os.environ.pop("SU_MCP_RUNTIME", None)
        cls.tmp.cleanup()

    def test_timeout_is_a_result_not_an_exception(self):
        out = self.dispatch.call("su_status", {}, timeout=0.01)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_type"], "Timeout")
        self.assertIn("run_as_job", out["error"])

    def test_job_runs_and_its_result_is_readable(self):
        job = self.dispatch.start_job("su_status", {})
        self.assertEqual(job["status"], "running")
        for _ in range(60):
            state = self.dispatch.job_status(job["job_id"])
            if state["status"] != "running":
                break
            time.sleep(0.5)
        self.assertEqual(state["status"], "finished")
        self.assertIn("ok", self.dispatch.job_result(job["job_id"]))

    def test_result_is_refused_while_the_job_is_unfinished(self):
        job = self.dispatch.start_job("su_status", {})
        self.dispatch.cancel_job(job["job_id"])
        with self.assertRaises(self.dispatch.JobError):
            # either still unfinished, or cancelled before it wrote anything
            for _ in range(3):
                self.dispatch.job_result(job["job_id"])
                time.sleep(0.2)

    def test_unknown_job_id_names_what_exists(self):
        with self.assertRaises(self.dispatch.JobError):
            self.dispatch.job_status("nosuchjob")

    def test_a_job_id_cannot_escape_the_job_directory(self):
        for bad in ("../../etc/passwd", "a/b", ""):
            with self.subTest(bad=bad), self.assertRaises(self.dispatch.JobError):
                self.dispatch.job_status(bad)


class RuntimeSplitTest(unittest.TestCase):
    """work/ may sit on a different filesystem from the project root, and no caller, including every path already
    written into a manifest, should have to know that."""

    def test_names_survive_the_split(self):
        import importlib
        tmp = tempfile.TemporaryDirectory()
        root, runtime = Path(tmp.name) / "proj", Path(tmp.name) / "rt"
        for base, names in ((root, ("raw", "results", "qc", "logs", "state")),
                            (runtime, ("work", "jobs", "tmp"))):
            for name in names:
                (base / name).mkdir(parents=True)
        os.environ["SU_MCP_ROOT"], os.environ["SU_MCP_RUNTIME"] = str(root), str(runtime)
        try:
            from sumcp import config, paths
            importlib.reload(config)
            importlib.reload(paths)
            (runtime / "work" / "line.su").write_bytes(b"x")
            resolved = paths.safe_input_path("work/line.su")
            self.assertEqual(resolved, (runtime / "work" / "line.su").resolve())
            self.assertEqual(paths.as_rel(resolved), str(Path("work") / "line.su"))
            self.assertEqual(paths.safe_input_path("raw/../raw/x.su"),
                             (root / "raw" / "x.su").resolve())
            with self.assertRaises(paths.PathPolicyError):
                paths.safe_output_path("raw/x.su")
        finally:
            os.environ.pop("SU_MCP_ROOT", None)
            os.environ.pop("SU_MCP_RUNTIME", None)
            from sumcp import config, paths
            importlib.reload(config)
            importlib.reload(paths)
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()


class DataDirTest(unittest.TestCase):
    """Field data that does not live in raw/."""

    def setUp(self):
        import importlib
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs", "state"):
            (self.root / name).mkdir()
        (self.root / "test_dataset" / "Survey").mkdir(parents=True)
        (self.root / "test_dataset" / "Survey" / "line.segy").write_bytes(b"x")
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere" / "secret.segy").write_bytes(b"x")
        os.environ["SU_MCP_ROOT"] = str(self.root)
        os.environ["SU_MCP_RUNTIME"] = str(self.root)
        os.environ.pop("SU_MCP_DATA_DIRS", None)
        from sumcp import config, paths
        importlib.reload(config)
        importlib.reload(paths)
        self.config, self.paths = config, paths

    def tearDown(self):
        import importlib
        for key in ("SU_MCP_ROOT", "SU_MCP_RUNTIME", "SU_MCP_DATA_DIRS"):
            os.environ.pop(key, None)
        from sumcp import config, paths
        importlib.reload(config)
        importlib.reload(paths)
        self.tmp.cleanup()

    def test_a_declared_archive_is_readable_by_name(self):
        path = self.paths.safe_input_path("test_dataset/Survey/line.segy")
        self.assertTrue(path.exists())
        self.assertEqual(self.paths.as_rel(path),
                         str(Path("test_dataset") / "Survey" / "line.segy"))

    def test_an_archive_is_never_writable(self):
        with self.assertRaises(self.paths.PathPolicyError):
            self.paths.safe_output_path("test_dataset/Survey/out.su")

    def test_undeclared_directories_are_still_refused(self):
        for name in ("elsewhere/secret.segy", "../outside.segy", "/etc/passwd"):
            with self.subTest(name=name):
                with self.assertRaises(self.paths.PathPolicyError):
                    self.paths.safe_input_path(name)

    def test_the_declaration_can_be_set_explicitly(self):
        import importlib
        os.environ["SU_MCP_DATA_DIRS"] = str(self.root / "elsewhere")
        from sumcp import config, paths
        importlib.reload(config)
        importlib.reload(paths)
        self.assertTrue(paths.safe_input_path("elsewhere/secret.segy").exists())
        # and naming one directory does not quietly keep the defaults
        with self.assertRaises(paths.PathPolicyError):
            paths.safe_input_path("test_dataset/Survey/line.segy")
