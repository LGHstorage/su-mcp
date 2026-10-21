"""Who the sensitivity ladder is allowed to ask, and where the cdp came from."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import reflection as R   # noqa: E402

FIXTURE = REPO / "test_dataset" / "VikingAdversarial" / "A03_NOISE_ONLY.segy"
NS, DT, WATER = 800, 0.004, 1492.0


def noise_gather(n=48, ns=NS, seed=7):
    """Spectrum-shaped noise on a wide aperture: no direct wave, no reflection."""
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, (n, ns))
    spectrum = np.abs(np.fft.rfft(white, axis=1))
    freq = np.fft.rfftfreq(ns, DT)
    shape = np.exp(-0.5 * ((freq - 45.0) / 35.0) ** 2)
    phase = rng.uniform(-np.pi, np.pi, spectrum.shape)
    out = np.fft.irfft(spectrum * shape[None, :] * np.exp(1j * phase), n=ns, axis=1)
    return out, np.linspace(200.0, 3000.0, n)


class LadderPollingTest(unittest.TestCase):

    def test_the_ladder_records_who_it_polled(self):
        data, off = noise_gather()
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        self.assertTrue(got["sensitivity_ladder"], "the ladder did not run")
        for rung in got["sensitivity_ladder"]:
            self.assertIn("polled", rung)
            self.assertIn("detected_by_polled", rung)
            self.assertTrue(set(rung["detected_by_polled"])
                            <= set(rung["polled"]))

    def test_only_qualified_branches_are_polled(self):
        data, off = noise_gather()
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        voters = [n for n, s in got["branch_status"].items()
                  if s == R.BRANCH_VALID]
        self.assertEqual(got["detection_limit_polled_branches"], voters)
        for rung in got["sensitivity_ladder"]:
            self.assertEqual(sorted(rung["polled"]), sorted(voters))

    def test_a_not_applicable_branch_cannot_raise_the_detection_limit(self):
        """The limit is the first rung every POLLED branch recovers."""
        data, off = noise_gather()
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        polled = got["detection_limit_polled_branches"]
        threshold = got["detection_threshold_x_rms"]["value"]
        if threshold is None:
            self.skipTest("nothing was recovered on this gather at any rung")
        rungs = {r["amplitude_x_rms"]: r for r in got["sensitivity_ladder"]}
        self.assertEqual(sorted(rungs[threshold]["detected_by_polled"]),
                         sorted(polled),
                         "the reported limit is not a rung every polled "
                         "branch recovered")
        for amp, rung in rungs.items():
            if amp < threshold:
                self.assertNotEqual(sorted(rung["detected_by_polled"]),
                                    sorted(polled),
                                    f"{amp}x was recovered by every polled "
                                    f"branch but is below the reported limit")

    def test_the_polled_limit_is_never_looser_than_the_all_branch_limit(self):
        """Polling fewer branches can only lower the limit, never raise it."""
        data, off = noise_gather()
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        polled = got["detection_threshold_x_rms"]["value"]
        all_branches = None
        for rung in got["sensitivity_ladder"]:
            if sorted(rung["detected_by"]) == sorted(got["branch_status"]):
                all_branches = rung["amplitude_x_rms"]
                break
        if polled is None or all_branches is None:
            self.skipTest("one of the two limits was not reached on this gather")
        self.assertLessEqual(polled, all_branches)


class A03LadderTest(unittest.TestCase):
    """The real gather the fix was made for."""

    def setUp(self):
        if not FIXTURE.exists():
            self.skipTest(f"fixture not present: {FIXTURE}")
        file_hdr, hdr = 3600, 240
        with open(FIXTURE, "rb") as f:
            f.seek(file_hdr)
            first = f.read(hdr)
        ns = int(np.frombuffer(first[114:116], dtype=">i2")[0])
        self.dt = int(np.frombuffer(first[116:118], dtype=">i2")[0]) * 1e-6
        stride = hdr + ns * 4
        ntr = (FIXTURE.stat().st_size - file_hdr) // stride
        off, rows = [], []
        with open(FIXTURE, "rb") as f:
            for i in range(ntr):
                f.seek(file_hdr + i * stride)
                head = f.read(hdr)
                if int(np.frombuffer(head[20:24], dtype=">i4")[0]) != 1100:
                    continue
                off.append(abs(int(np.frombuffer(head[36:40], dtype=">i4")[0])))
                raw = np.frombuffer(f.read(ns * 4), dtype=">u4").astype(np.uint32)
                sign = 1.0 - 2.0 * ((raw >> 31) & 1).astype(np.float64)
                expo = ((raw >> 24) & 0x7F).astype(np.int32)
                mant = (raw & 0x00FFFFFF).astype(np.float64) / float(1 << 24)
                rows.append(sign * mant * np.power(16.0, (expo - 64).astype(float)))
        self.off = np.asarray(off, dtype=float)
        self.data = np.asarray(rows)

    def test_a03_still_fails_and_its_limit_came_from_the_voters(self):
        got = R.assess(self.data, self.off, self.dt, 0.0, water=WATER,
                       run_sensitivity=True)
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.FAIL)
        polled = got["detection_limit_polled_branches"]
        self.assertTrue(polled, "nothing was polled")
        self.assertEqual(
            polled,
            [n for n, s in got["branch_status"].items() if s == R.BRANCH_VALID])
        threshold = got["detection_threshold_x_rms"]["value"]
        self.assertIsNotNone(threshold)
        self.assertLessEqual(threshold, R.INFORMATIVE_THRESHOLD_X_RMS,
                             "the FAIL rests on a limit above the threshold at "
                             "which a negative result means anything")


if __name__ == "__main__":
    unittest.main()


class CdpOriginTest(unittest.TestCase):
    """Where the processing copy's cdp came from, written down."""

    @staticmethod
    def comparison(header, computed):
        from sumcp import cmp as CMP
        return CMP._compare_with_header(np.asarray(header), np.asarray(computed))

    def origin(self, header, computed):
        from sumcp import cmp as CMP
        header = np.asarray(header)
        return CMP.cdp_origin(header, self.comparison(header, computed),
                              "work/x/x.su")

    def test_a_header_that_groups_the_same_way_is_kept(self):
        header = [1000, 1000, 1001, 1001]
        computed = [7, 7, 8, 8]          # different numbers, same grouping
        got = self.origin(header, computed)
        self.assertFalse(got["applied"])
        self.assertEqual(got["origin"], "TRACE_HEADERS")
        self.assertEqual(got["header_state"], "varying")

    def test_a_header_that_merges_coordinate_bins_is_replaced(self):
        header = [500, 500, 500, 500]    # one shot number over two real bins
        computed = [7, 7, 8, 8]
        got = self.origin(header, computed)
        self.assertTrue(got["applied"])
        self.assertEqual(got["origin"], "DERIVED_FROM_COORDINATES")
        self.assertEqual(got["header_bins"], 1)
        self.assertEqual(got["computed_bins"], 2)
        self.assertGreaterEqual(got["header_bins_split_by_coordinates"], 1)

    def test_a_header_that_splits_coordinate_bins_is_replaced(self):
        header = [10, 11, 12, 13]
        computed = [7, 7, 8, 8]
        got = self.origin(header, computed)
        self.assertTrue(got["applied"])
        self.assertEqual(got["origin"], "DERIVED_FROM_COORDINATES")
        self.assertGreaterEqual(got["computed_bins_merged_in_header"], 1)

    def test_an_absent_header_leaves_nothing_to_agree_with(self):
        got = self.origin([0, 0, 0, 0], [7, 7, 8, 8])
        self.assertTrue(got["applied"])
        self.assertEqual(got["origin"], "DERIVED_FROM_COORDINATES")
        self.assertEqual(got["header_state"], "absent")

    def test_the_imported_file_is_never_rewritten(self):
        for header in ([1000, 1000, 1001, 1001], [500, 500, 500, 500],
                       [0, 0, 0, 0]):
            got = self.origin(header, [7, 7, 8, 8])
            self.assertFalse(got["source_file_modified"])
            self.assertEqual(got["source_file"], "work/x/x.su")
