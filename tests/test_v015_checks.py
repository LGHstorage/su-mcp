"""v0.15 checks: time zero, scan-edge picks, slow candidates, Dix window."""

import unittest

import numpy as np

from sumcp import reflection as R
from sumcp import timezero as TZ
from sumcp import velocity as V


def ricker(t, f0):
    a = (np.pi * f0 * t) ** 2
    return (1 - 2 * a) * np.exp(-a)


def direct_gather(delay_s, f0=20.0, v=1500.0, dt=0.002, ns=1500, seed=0):
    rng = np.random.default_rng(seed)
    offsets = np.arange(100.0, 2020.0, 20.0)
    t = np.arange(ns) * dt
    data = np.stack([ricker(t - x / v - delay_s, f0) for x in offsets])
    data += 0.02 * rng.standard_normal(data.shape)
    return data, offsets, dt


class TimeZero(unittest.TestCase):
    def test_anchored_record_passes(self):
        data, x, dt = direct_gather(0.0)
        out = TZ.measure(data, x, dt, 0.0, 1492.0, "ROBUST")
        self.assertEqual(out["status"], TZ.PASS)
        self.assertLess(abs(out["intercept_s"]), 0.005)
        self.assertAlmostEqual(out["direct_velocity_m_s"], 1500.0, delta=15.0)

    def test_late_record_fails(self):
        data, x, dt = direct_gather(0.15)
        out = TZ.measure(data, x, dt, 0.0, 1492.0, "ROBUST")
        self.assertEqual(out["status"], TZ.FAIL)
        self.assertAlmostEqual(out["intercept_s"], 0.15, delta=0.005)

    def test_delay_within_one_period_passes(self):
        # A causal wavelet peaks after the shot instant; up to one period is the wavelet, not the clock.
        data, x, dt = direct_gather(0.03, f0=20.0)
        out = TZ.measure(data, x, dt, 0.0, 1492.0, "ROBUST")
        self.assertEqual(out["status"], TZ.PASS)

    def test_not_measured_without_robust_direct_wave(self):
        data, x, dt = direct_gather(0.15)
        for verdict in ("FRAGILE", "ABSENT"):
            out = TZ.measure(data, x, dt, 0.0, 1492.0, verdict)
            self.assertEqual(out["status"], TZ.UNKNOWN)


def fn(pairs, semblance=0.5):
    return [{"t0_s": t, "v_m_s": v, "semblance": semblance} for t, v in pairs]


class ScanEdge(unittest.TestCase):
    good = [(0.2, 1500), (0.6, 1600), (1.0, 1800), (1.4, 2000), (1.8, 2200)]

    def run_validate(self, function, cleared):
        dense = [(p["t0_s"], cleared) for p in function]
        info = {"points": len(function), "fraction": 1.0,
                "to_s": function[-1]["t0_s"]}
        return V.validate(function, 0.1, 2.0, support_info=info,
                          scan_edges=(1400.0, 5500.0), dense_cleared=dense)

    def test_supported_edge_pick_invalidates(self):
        f = fn([(0.2, 1400)] + self.good[1:])
        out = self.run_validate(f, True)
        self.assertFalse(out["valid"])
        self.assertEqual(out["scan_edge_picks"]["supported_t0_s"], [0.2])

    def test_unconstrained_edge_pick_is_reported_not_failed(self):
        f = fn([(0.2, 1400)] + self.good[1:])
        out = self.run_validate(f, False)
        self.assertTrue(out["valid"], out["problems"])
        self.assertEqual(out["scan_edge_picks"]["unconstrained_t0_s"], [0.2])

    def test_interior_picks_untouched(self):
        out = self.run_validate(fn(self.good), True)
        self.assertTrue(out["valid"], out["problems"])
        self.assertEqual(out["scan_edge_picks"]["supported_t0_s"], [])

    def test_without_scan_edges_behaves_as_before(self):
        f = fn([(0.2, 1400)] + self.good[1:])
        info = {"points": 5, "fraction": 1.0, "to_s": 1.8}
        out = V.validate(f, 0.1, 2.0, support_info=info)
        self.assertTrue(out["valid"], out["problems"])
        self.assertIsNone(out["scan_edge_picks"])


class DixWindow(unittest.TestCase):
    def test_window_ends_before_both_endpoints_of_the_violation(self):
        pairs = [(0.2, 1500), (0.6, 1700), (1.0, 1900), (1.4, 2100),
                 (1.8, 2300), (2.2, 4200)]      # 1.8-2.2 s interval is wild
        f = fn(pairs)
        dense = [(p["t0_s"], True) for p in f]
        info = {"points": 6, "fraction": 1.0, "to_s": 2.2}
        out = V.validate(f, 0.1, 2.4, support_info=info, dense_cleared=dense)
        self.assertFalse(out["valid"])
        w = out["dix_valid_window"]
        self.assertEqual(w["first_violation_from_s"], 1.8)
        self.assertEqual(w["valid_to_s"], 1.4)
        self.assertEqual(w["status"], "REPORT_ONLY")

    def test_no_window_without_support_above(self):
        pairs = [(0.2, 1500), (0.22, 3000), (1.0, 3100)]   # wild from the top
        f = fn(pairs)
        dense = [(p["t0_s"], False) for p in f]
        info = {"points": 3, "fraction": 1.0, "to_s": 1.0}
        out = V.validate(f, 0.1, 1.2, support_info=info, dense_cleared=dense)
        self.assertIsNone(out["dix_valid_window"]["valid_to_s"])

    def test_clean_function_has_no_window(self):
        f = fn([(0.2, 1500), (0.6, 1600), (1.0, 1800)])
        info = {"points": 3, "fraction": 1.0, "to_s": 1.0}
        out = V.validate(f, 0.1, 1.2, support_info=info,
                         dense_cleared=[(p["t0_s"], True) for p in f])
        self.assertIsNone(out["dix_valid_window"])


class SlowCandidates(unittest.TestCase):
    def report(self, v):
        peak = {"t0_s": 0.6, "v_m_s": v, "semblance": 0.3}
        return {"a": {"peaks": [peak]}, "b": {"peaks": [dict(peak)]}}

    def agree(self, v, present):
        offsets = np.arange(200.0, 2120.0, 20.0)
        return R._agreement(self.report(v), ["a", "b"], 0.05, offsets, 1492.0,
                            0.067, present, v_step=50.0)

    def test_slower_than_direct_wave_rejected(self):
        agreed, rejected = self.agree(1400.0, True)
        self.assertEqual(agreed, [])
        self.assertIn("below the 1492 m/s direct wave", rejected[0]["rejected"])

    def test_within_one_scan_step_kept_to_other_rules(self):
        agreed, rejected = self.agree(1450.0, True)
        for c in rejected:
            self.assertNotIn("below the", c["rejected"])

    def test_faster_candidate_untouched(self):
        agreed, rejected = self.agree(2400.0, True)
        self.assertEqual(len(agreed), 1)

    def test_rule_needs_a_direct_wave(self):
        agreed, rejected = self.agree(1400.0, False)
        self.assertEqual(len(agreed), 1)


if __name__ == "__main__":
    unittest.main()


class HeaderStatics(unittest.TestCase):
    """tstat is the static already applied (SEG-Y); only sstat/gstat are applied."""

    def write(self, path, sstat, gstat, tstat, ntr=4, ns=16):
        import struct
        with open(path, "wb") as out:
            for i in range(ntr):
                head = bytearray(240)
                struct.pack_into("<i", head, 0, i + 1)
                struct.pack_into("<h", head, 98, sstat)
                struct.pack_into("<h", head, 100, gstat)
                struct.pack_into("<h", head, 102, tstat)
                struct.pack_into("<H", head, 114, ns)
                struct.pack_into("<H", head, 116, 4000)
                out.write(bytes(head) + np.zeros(ns, "<f4").tobytes())

    def run_statics(self, sstat, gstat, tstat):
        import tempfile
        from pathlib import Path
        from sumcp import stack
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "g.su"
            self.write(src, sstat, gstat, tstat)
            return stack._apply_header_statics({}, "t", src, "r")

    def test_tstat_only_is_left_alone(self):
        path, info = self.run_statics(0, 0, 11)
        self.assertFalse(info["applied"])
        self.assertIn("already applied", info["reason"])

    def test_no_statics_at_all(self):
        path, info = self.run_statics(0, 0, 0)
        self.assertFalse(info["applied"])

    def test_inconsistent_source_receiver_statics_still_refused(self):
        with self.assertRaises(ValueError):
            self.run_statics(-20, -30, 7)
