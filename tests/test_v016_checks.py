"""v0.16 checks: time-datum disclosure (report only) and band-limited absence."""

import unittest

import numpy as np

from sumcp import reflection as R
from sumcp import stack as S


def tz_cap(status, intercept=None, period=None, reason="r"):
    ev = {"gather": {"fldr": 63}, "reason": reason}
    if intercept is not None:
        ev.update(intercept_s=intercept, tolerance_s=period)
    return {"status": status, "evidence": ev}


class TimeDatum(unittest.TestCase):
    def test_small_lag_is_within_resolution(self):
        d = S.time_datum(tz_cap("PASS", -0.002, 0.1145))
        self.assertEqual(d["status"], "MEASURED")
        self.assertEqual(d["level"], "WITHIN_RESOLUTION")
        self.assertAlmostEqual(d["lag_ms"], -2.0)

    def test_lag_beyond_quarter_period_is_disclosed(self):
        d = S.time_datum(tz_cap("PASS", 0.048, 0.1145))
        self.assertEqual(d["level"], "DISPLACED")
        self.assertAlmostEqual(d["vertical_resolution_ms"], 28.6, places=1)
        self.assertIn("-48 ms", d["statement"])

    def test_quarter_period_boundary_is_inclusive(self):
        self.assertEqual(S.time_datum(tz_cap("PASS", 0.025, 0.1))["level"],
                         "WITHIN_RESOLUTION")
        self.assertEqual(S.time_datum(tz_cap("PASS", -0.026, 0.1))["level"],
                         "DISPLACED")

    def test_r1_fail_still_reports_the_lag(self):
        d = S.time_datum(tz_cap("FAIL", 0.148, 0.1145))
        self.assertEqual(d["status"], "MEASURED")
        self.assertEqual(d["level"], "DISPLACED")

    def test_unmeasured_is_unknown(self):
        self.assertEqual(S.time_datum(tz_cap("UNKNOWN", reason="ABSENT"))["status"],
                         "UNKNOWN")
        self.assertEqual(S.time_datum(None)["status"], "UNKNOWN")


class BandLimitedAbsence(unittest.TestCase):
    def test_fraction_of_a_low_frequency_record(self):
        dt, t = 0.002, np.arange(1300) * 0.002
        low = np.sin(2 * np.pi * 8.0 * t)[None, :].repeat(4, axis=0)
        self.assertLess(R.band_energy_fraction(low, dt, 30.0, 250.0), 0.01)
        self.assertGreater(R.band_energy_fraction(low, dt, 5.0, 90.0), 0.99)

    def test_white_noise_fraction_follows_bandwidth(self):
        rng = np.random.default_rng(0)
        w = rng.standard_normal((50, 2000))
        f = R.band_energy_fraction(w, 0.002, 30.0, 250.0)
        self.assertAlmostEqual(f, 220.0 / 250.0, delta=0.02)

    def test_fail_in_a_minority_band_is_inconclusive(self):
        self.assertEqual(R.band_limited_absence(R.FAIL, 0.0001), (R.INCONCLUSIVE, True))
        self.assertEqual(R.band_limited_absence(R.FAIL, 0.49), (R.INCONCLUSIVE, True))

    def test_fail_in_a_majority_band_stands(self):
        self.assertEqual(R.band_limited_absence(R.FAIL, 0.5), (R.FAIL, False))

    def test_never_touches_pass_or_inconclusive(self):
        for v in (R.PASS, R.INCONCLUSIVE):
            for f in (0.0, 0.3, 0.9):
                self.assertEqual(R.band_limited_absence(v, f), (v, False))


if __name__ == "__main__":
    unittest.main()
