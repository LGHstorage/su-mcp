"""v0.21 checks: W2 (G1 stacks are warned) and RS2 (random halves, materiality)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import iterate as I                                   # noqa: E402
from sumcp import stack as S                                     # noqa: E402


class W2(unittest.TestCase):
    CLEAR = {"level": "CLEAR", "correlation_ceiling": 0.961}
    MEASURED = {"level": "MEASURED"}

    def test_g1_stack_is_disclosed_even_when_n1_and_e1_are_quiet(self):
        # v0.23 T2: the W2 reason is a provenance CAUTION, no longer a quality WARN
        feas = S.feasibility_disclosure({"status": "UNKNOWN",
                                         "evidence": {"verdict": "INCONCLUSIVE"}})
        w = S.reliability_warning(self.CLEAR, self.MEASURED, feas)
        self.assertEqual(w["level"], "CAUTION")
        self.assertIn("feasibility not established", w["reasons"][0])

    def test_feasible_stack_is_unchanged(self):
        feas = S.feasibility_disclosure({"status": "PASS"})
        self.assertIsNone(feas)
        self.assertEqual(S.reliability_warning(self.CLEAR, self.MEASURED, feas)["level"], "OK")
        self.assertEqual(S.reliability_warning(self.CLEAR, self.MEASURED)["level"], "OK")


class RS2(unittest.TestCase):
    def test_random_halves_see_every_station_on_a_parity_locked_geometry(self):
        # a station whose CMPs step by two bins: parity halves put it on one side only
        cmp_rank = np.arange(1, 401)
        station_cmps = cmp_rank[::2][:40]
        halves = I.cmp_halves(cmp_rank)
        self.assertTrue(np.all(station_cmps % 2 == 1))           # parity-locked
        hit = halves[station_cmps - 1]
        self.assertGreaterEqual(hit.sum(), 5)
        self.assertGreaterEqual((~hit).sum(), 5)

    def test_halves_are_reproducible(self):
        r = np.arange(1, 597)
        np.testing.assert_array_equal(I.cmp_halves(r), I.cmp_halves(r))

    def test_materiality_line(self):
        period = 0.1145
        line = I.RS_MATERIAL_FRACTION * period
        self.assertAlmostEqual(line, 0.0084, places=4)
        self.assertFalse(I.statics_material(0.006, period)[1])    # v0.20 artefact level
        self.assertTrue(I.statics_material(0.014, period)[1])     # statics 12 ms level
        f, _ = I.statics_material(line, period)
        self.assertAlmostEqual(f, 0.9, places=6)


if __name__ == "__main__":
    unittest.main()
