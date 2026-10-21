"""v0.32 checks: S1 acquisition statics (SEG-Y direction, first-break gate)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import acqstatics as A                                 # noqa: E402
from sumcp import config, runner, sufile                          # noqa: E402

HAVE_SU = runner.find_program("sustatic") is not None


def _shots(path, intercept, sstat, gstat, nshot=12, ns=500, dt=0.002, v=2000.0):
    offs = np.r_[-np.arange(400, 40, -30), np.arange(70, 430, 30)].astype(float)
    ntr = nshot * offs.size
    hdr = np.zeros((ntr, 60), dtype="<i4")
    h16 = hdr.view("<i2")
    data = np.zeros((ntr, ns), dtype="<f4")
    t = np.arange(ns) * dt
    k = 0
    for s in range(nshot):
        for x in offs:
            hdr[k, 0] = k + 1
            hdr[k, 2] = s + 1                     # fldr
            hdr[k, 9] = int(x)                    # offset
            h16[k, 49] = sstat                     # byte 98
            h16[k, 50] = gstat                     # byte 100
            h16[k, 51] = sstat + gstat             # byte 102
            fb = intercept + abs(x) / v
            a = (np.pi * 25 * (t - fb - 0.02)) ** 2
            data[k] = ((1 - 2 * a) * np.exp(-a)) * (t >= fb - 0.01)
            k += 1
    h16[:, 57] = ns
    h16[:, 58] = int(dt * 1e6)
    path.write_bytes(np.concatenate([hdr.view("u1"), data.view("u1")], axis=1).tobytes())


class Intercept(unittest.TestCase):
    def test_intercept_is_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "g.su"
            _shots(p, 0.12, 0, 0)
            r = A.first_break_intercept(p)
        self.assertAlmostEqual(r["intercept_s"], 0.12, delta=0.01)
        self.assertEqual(r["shots"], 12)


@unittest.skipUnless(HAVE_SU, "SU sustatic not installed")
class Direction(unittest.TestCase):
    def _apply(self, intercept, s, g):
        with tempfile.TemporaryDirectory() as tmp:
            old = (config.WORK_DIR, A.safe_output_path, A.as_rel)
            config.WORK_DIR = Path(tmp)
            A.safe_output_path = lambda p, overwrite=False: Path(p)
            A.as_rel = lambda p: str(p)
            try:
                (Path(tmp) / "t").mkdir()
                src = Path(tmp) / "t" / "g.su"
                _shots(src, intercept, s, g)
                use, rec = A.apply({"artifacts": {}, "history": []}, "t", src, "r")
                h = sufile.read_header_columns(use, ["sstat", "gstat", "tstat"])
                after = A.first_break_intercept(use)
            finally:
                config.WORK_DIR, A.safe_output_path, A.as_rel = old
        return rec, h, after

    def test_negative_statics_move_first_breaks_up(self):
        rec, h, after = self._apply(0.12, -50, -50)
        self.assertEqual(rec["verdict"], "PASS", rec)
        self.assertAlmostEqual(after["intercept_s"], 0.02, delta=0.01)
        self.assertFalse(np.any(h["sstat"]) or np.any(h["gstat"]))
        self.assertTrue(np.all(np.asarray(h["tstat"]) == -100))

    def test_statics_that_move_first_breaks_away_are_refused(self):
        rec, h, after = self._apply(0.02, 50, 50)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertFalse(rec["applied"])
        self.assertAlmostEqual(after["intercept_s"], 0.02, delta=0.01)     # left uncorrected
        self.assertFalse(np.any(h["sstat"]) or np.any(h["gstat"]) or np.any(h["tstat"]))


class Convention(unittest.TestCase):
    def test_segy_sign(self):
        self.assertEqual(A.SIGN_SEGY, -1)


if __name__ == "__main__":
    unittest.main()
