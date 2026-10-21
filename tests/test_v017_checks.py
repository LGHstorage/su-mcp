"""v0.17 checks: R2b direct-wave-zone exemption and N1 half-stack S/N."""

import unittest

import numpy as np

from sumcp import stack as S
from sumcp import velocity as V

OFFSETS = np.arange(200.0, 2101.0, 20.0)
DW = {"velocity_m_s": 1499.5, "period_s": 0.1145}


def fn(points, semblance=0.5):
    return [{"t0_s": t, "v_m_s": v, "semblance": semblance, "held": False}
            for t, v in points]


class DirectWaveZone(unittest.TestCase):
    good = [(0.6, 1600), (1.0, 1800), (1.4, 2000), (1.8, 2200)]

    def run_validate(self, function, direct_wave):
        dense = [(p["t0_s"], True) for p in function]
        info = {"points": len(function), "fraction": 1.0, "to_s": function[-1]["t0_s"]}
        return V.validate(function, 0.1, 2.0, support_info=info,
                          scan_edges=(1400.0, 5500.0), dense_cleared=dense,
                          direct_wave=direct_wave, offsets=OFFSETS)

    def test_shallow_edge_pick_is_the_direct_wave(self):
        self.assertTrue(V.in_direct_wave_zone({"t0_s": 0.04, "v_m_s": 1400.0}, DW, OFFSETS))

    def test_separable_edge_pick_is_not(self):
        self.assertFalse(V.in_direct_wave_zone({"t0_s": 0.32, "v_m_s": 1400.0}, DW, OFFSETS))

    def test_no_measured_direct_wave_no_exemption(self):
        self.assertFalse(V.in_direct_wave_zone({"t0_s": 0.04, "v_m_s": 1400.0}, None, OFFSETS))
        self.assertFalse(V.in_direct_wave_zone({"t0_s": 0.04, "v_m_s": 1400.0}, DW, None))

    def test_exempt_pick_does_not_invalidate(self):
        out = self.run_validate(fn([(0.04, 1400)] + self.good), DW)
        self.assertTrue(out["valid"], out["problems"])
        self.assertEqual(out["scan_edge_picks"]["direct_wave_zone_t0_s"], [0.04])
        self.assertEqual(out["scan_edge_picks"]["supported_t0_s"], [])

    def test_without_direct_wave_r2_still_applies(self):
        out = self.run_validate(fn([(0.04, 1400)] + self.good), None)
        self.assertFalse(out["valid"])
        self.assertEqual(out["scan_edge_picks"]["supported_t0_s"], [0.04])

    def test_separable_edge_pick_still_invalidates(self):
        out = self.run_validate(fn([(0.32, 1400)] + self.good), DW)
        self.assertFalse(out["valid"])
        self.assertEqual(out["scan_edge_picks"]["supported_t0_s"], [0.32])


class HalfStack(unittest.TestCase):
    def gathers(self, noise, fold=24, ncmp=30, ns=600, seed=0):
        rng = np.random.default_rng(seed)
        sig = rng.standard_normal((ncmp, ns))
        data = np.repeat(sig, fold, axis=0) + noise * rng.standard_normal((ncmp * fold, ns))
        cdp = np.repeat(np.arange(ncmp), fold)
        off = np.tile(np.arange(fold) * 20.0, ncmp)
        return data, cdp, off

    def test_noise_free_is_coherent(self):
        r = np.median(S.half_stack_correlations(*self.gathers(0.0)))
        self.assertGreater(r, 0.999)

    def test_matches_theory(self):
        # per-half S/N (power) = 12 / sigma^2; r = snr_h / (1 + snr_h)
        for sigma in (1.0, 3.0, 5.0):
            r = np.median(S.half_stack_correlations(*self.gathers(sigma)))
            snr_h = 12 / sigma ** 2
            self.assertAlmostEqual(r, snr_h / (1 + snr_h), delta=0.04)

    def test_low_fold_cmps_skipped(self):
        self.assertEqual(S.half_stack_correlations(*self.gathers(1.0, fold=6)), [])


if __name__ == "__main__":
    unittest.main()
