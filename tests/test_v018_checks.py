"""v0.18 checks: velocity-support fraction (E1)."""

import unittest

from sumcp import stack as S


class SupportFraction(unittest.TestCase):
    def test_clean_benchmark_is_mostly_measured(self):
        f = S.support_fraction(1.40, 2.602, 2.24)
        self.assertAlmostEqual(f, 0.699, places=2)
        self.assertGreaterEqual(f, S.MIN_MEASURED_FRACTION)

    def test_shallow_support_is_partial(self):
        self.assertLess(S.support_fraction(1.40, 2.602, 1.48), S.MIN_MEASURED_FRACTION)

    def test_clipped(self):
        self.assertEqual(S.support_fraction(1.40, 2.602, 1.0), 0.0)
        self.assertEqual(S.support_fraction(1.40, 2.602, 3.0), 1.0)

    def test_record_ending_before_direct_wave(self):
        self.assertIsNone(S.support_fraction(3.0, 2.6, 2.0))


if __name__ == "__main__":
    unittest.main()
