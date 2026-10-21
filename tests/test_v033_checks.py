"""v0.33 checks: L0/L1 land reflection window, G1 gate frequency, G3 split spread, R2."""

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
from sumcp import analysis, conditioning as K, iterate, stack      # noqa: E402


def _line(path, t0=0.15, v=2500.0, nshot=14, ns=1000, dt=0.002, xmax=3000.0, jitter=0.0):
    offs = np.r_[-np.arange(xmax, 0, -50.0), np.arange(50.0, xmax + 1, 50.0)]
    ntr = nshot * offs.size
    hdr = np.zeros((ntr, 60), dtype="<i4")
    h16 = hdr.view("<i2")
    data = np.zeros((ntr, ns), dtype="<f4")
    t = np.arange(ns) * dt
    rng = np.random.default_rng(3)
    k = 0
    for s in range(nshot):
        dt0 = jitter * rng.standard_normal()
        for x in offs:
            hdr[k, 0] = k + 1
            hdr[k, 2] = s + 1
            hdr[k, 9] = int(x)
            fb = t0 + dt0 + abs(x) / v
            a = (np.pi * 25 * (t - fb - 0.02)) ** 2
            data[k] = (1 - 2 * a) * np.exp(-a) * (t >= fb - 0.01)
            b = (np.pi * 25 * (t - np.sqrt(1.6 ** 2 + (x / 2200.0) ** 2))) ** 2
            data[k] += 0.3 * (1 - 2 * b) * np.exp(-b)          # a weaker reflection
            k += 1
    h16[:, 57] = ns
    h16[:, 58] = int(dt * 1e6)
    path.write_bytes(np.concatenate([hdr.view("u1"), data.view("u1")], axis=1).tobytes())


class FirstArrivals(unittest.TestCase):
    def test_window_start_is_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.su"
            _line(p)
            r = A.first_arrivals(p)
        self.assertEqual(r["status"], "MEASURED", r)
        self.assertAlmostEqual(r["t_a_s"], 0.15 + 3000 / 2500, delta=0.02)
        self.assertAlmostEqual(r["velocity_m_s"], 2500, delta=50)
        self.assertEqual(r["shots"], 14)

    def test_too_few_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.su"
            _line(p, nshot=5)
            r = A.first_arrivals(p)
        self.assertEqual(r["status"], "UNKNOWN")

    def test_inconsistent_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.su"
            _line(p, jitter=0.3)
            r = A.first_arrivals(p)
        self.assertEqual(r["status"], "UNKNOWN", r)

    def test_robust_line(self):
        x = np.linspace(700, 2200, 40)
        t = 0.2 + x / 3000.0
        t[::7] += 0.5                                     # a later event picked on some traces
        a, p, n = A.fit_first_arrival_line(x, t)
        self.assertAlmostEqual(a, 0.2, delta=0.005)
        self.assertAlmostEqual(1 / p, 3000, delta=30)


FA = {"status": "MEASURED", "t_a_s": 1.467, "intercept_s": 0.178, "velocity_m_s": 2739.0,
      "slowness_s_per_m": 1 / 2739.0, "max_offset_m": 3525.0}


class LandOnly(unittest.TestCase):
    def test_land_needs_s1_pass(self):
        self.assertIsNone(A.land_first_arrivals({}))
        self.assertIsNone(A.land_first_arrivals(
            {"acquisition_statics": {"applied": False, "first_arrivals": FA}}))
        self.assertIsNone(A.land_first_arrivals(
            {"acquisition_statics": {"applied": True, "verdict": "FAIL", "first_arrivals": FA}}))
        self.assertIs(A.land_first_arrivals(
            {"acquisition_statics": {"applied": True, "verdict": "PASS", "first_arrivals": FA}}), FA)

    def test_marine_window_unchanged(self):
        m = {"capabilities": {}}
        w = stack.reflection_window(m, 3000.0)
        self.assertEqual(w["t_s"], 3000.0 / 1492.0)
        self.assertEqual(w["class"], "ASSUMED")
        self.assertNotIn("land", w)
        t, v, c, _ = iterate.gate_window({"direct_velocity_m_s": None, "max_offset_m": 3000.0})
        self.assertEqual((t, v, c), (3000.0 / 1492.0, 1492.0, "ASSUMED"))

    def test_land_window(self):
        m = {"capabilities": {}, "acquisition_statics": {"applied": True, "verdict": "PASS",
                                                         "first_arrivals": FA}}
        w = stack.reflection_window(m, 3525.0)
        self.assertEqual(w["t_s"], 1.467)
        self.assertEqual(w["class"], "MEASURED")
        w2 = stack.reflection_window(m, 3000.0)
        self.assertAlmostEqual(w2["t_s"], 0.178 + 3000 / 2739.0, places=6)
        t, v, c, _ = iterate.gate_window({"first_arrivals": FA, "max_offset_m": 3525.0})
        self.assertEqual((t, v, c), (1.467, 2739.0, "MEASURED"))


class Mute(unittest.TestCase):
    def test_marine_mute_args_unchanged(self):
        (_, args, _), = K._mute_direct({"extra_s": 0.1}, {"direct_velocity_m_s": 1500.0,
                                                          "max_offset_m": 3000.0, "dt_s": 0.004})
        self.assertEqual(args["tmute"], [round(3000 / 1500 + 0.1, 4), 0.1, round(3000 / 1500 + 0.1, 4)])

    def test_land_mute_uses_first_arrivals(self):
        (_, args, _), = K._mute_direct({"extra_s": 0.1}, {"direct_velocity_m_s": None,
                                                          "first_arrivals": FA,
                                                          "max_offset_m": 3525.0, "dt_s": 0.002})
        self.assertAlmostEqual(args["tmute"][0], 0.178 + 3525 / 2739.0 + 0.1, places=3)
        self.assertAlmostEqual(args["tmute"][1], 0.278, places=4)

    def test_no_velocity_refused(self):
        with self.assertRaises(ValueError):
            K._mute_direct({}, {"direct_velocity_m_s": None, "max_offset_m": 3000.0, "dt_s": 0.004})


class GateFrequency(unittest.TestCase):
    def test_ricker_peaks_recovered(self):
        for dt, n in ((0.002, 1501), (0.004, 751)):
            t = np.arange(n) * dt
            for f0 in (8.7, 25.0, 44.0):
                a = (np.pi * f0 * (t - 1.0)) ** 2
                r = ((1 - 2 * a) * np.exp(-a))[None] + 0.02 * np.random.default_rng(0).standard_normal((20, n))
                self.assertAlmostEqual(iterate.gate_hz(r, dt), f0, delta=0.05 * f0, msg=(dt, f0))

    def test_broadband_is_stable(self):
        # a flat 10-90 Hz spectrum with random phase: argmax is arbitrary, G1 is not
        rng = np.random.default_rng(1)
        n, dt = 1501, 0.002
        f = np.fft.rfftfreq(n, dt)
        vals = []
        for _ in range(6):
            spec = ((f > 10) & (f < 90)) * np.exp(2j * np.pi * rng.random((30, f.size)))
            vals.append(iterate.gate_hz(np.fft.irfft(spec, n, axis=1), dt))
        self.assertLess(np.ptp(vals), 2.0)
        self.assertAlmostEqual(np.mean(vals), np.sqrt(np.pi) / 2 * 50, delta=3)

    def test_old_name_goes_through_g1(self):
        self.assertIs(iterate._dominant_hz, iterate.gate_hz)


class SplitSpread(unittest.TestCase):
    def test_split(self):
        x = np.r_[np.arange(3500, 0, -25.0), np.arange(25, 3500, 25.0)]
        self.assertTrue(analysis.is_split_spread(x))

    def test_end_on(self):
        self.assertFalse(analysis.is_split_spread(np.arange(100, 3000, 25.0)))
        self.assertFalse(analysis.is_split_spread(np.arange(3000, 100, -25.0)))


class Reporting(unittest.TestCase):
    def test_r2_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "g.su"
            _line(p, nshot=2, ns=200)
            prior = {"applied": True, "verdict": "PASS", "intercept_before_s": 0.1195,
                     "intercept_after_s": 0.0301, "output": "work/x.su"}
            use, rec = A.apply({"acquisition_statics": prior}, "x", p, "r")
        self.assertEqual(use, p)
        self.assertEqual(rec["status"], "APPLIED_AT_SORT_CMP")
        self.assertIn("applied at sort_cmp", rec["reason"])

    def test_marine_message_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "g.su"
            _line(p, nshot=2, ns=200)
            use, rec = A.apply({"acquisition_statics": {"applied": False}}, "x", p, "r")
        self.assertEqual(rec["reason"], "no source or receiver statics in headers")


if __name__ == "__main__":
    unittest.main()
