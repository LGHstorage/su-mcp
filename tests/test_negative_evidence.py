"""Evidence of absence, and the three states a suppression branch can be in."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

import numpy as np

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import reflection as R   # noqa: E402

NS, DT = 800, 0.004
WATER = 1492.0


def offsets_spread(n=48, lo=200.0, hi=3000.0):
    return np.linspace(lo, hi, n)


def matched_noise(n, ns, rng, colour=True):
    """Noise with a seismic-looking spectrum, which is what makes it hard."""
    white = rng.normal(0.0, 1.0, (n, ns))
    if not colour:
        return white
    spec = np.abs(np.fft.rfft(white, axis=1))
    freq = np.fft.rfftfreq(ns, DT)
    shape = np.exp(-0.5 * ((freq - 35.0) / 22.0) ** 2) + 1e-3
    phase = rng.uniform(-np.pi, np.pi, spec.shape)
    phase[:, 0] = 0.0
    out = np.fft.irfft(spec * shape * np.exp(1j * phase), n=ns, axis=1)
    return out / (out.std() + 1e-30)


def add_hyperbola(data, offsets, t0, velocity, amplitude, f0=30.0):
    ns = data.shape[1]
    rms = float(np.sqrt((data ** 2).mean()) + 1e-30)
    half = int(1.5 / f0 / DT)
    tau = np.arange(-half, half + 1) * DT
    wav = (1 - 2 * (np.pi * f0 * tau) ** 2) * np.exp(-(np.pi * f0 * tau) ** 2)
    wav *= amplitude * rms / (np.abs(wav).max() + 1e-30)
    out = data.copy()
    for i, x in enumerate(np.asarray(offsets)):
        k = int(round(np.sqrt(t0 ** 2 + (x / velocity) ** 2) / DT))
        if half < k < ns - half - 1:
            out[i, k - half:k + half + 1] += wav
    return out


def add_direct_wave(data, offsets, amplitude=6.0, velocity=WATER, f0=30.0):
    ns = data.shape[1]
    rms = float(np.sqrt((data ** 2).mean()) + 1e-30)
    half = int(1.5 / f0 / DT)
    tau = np.arange(-half, half + 1) * DT
    wav = (1 - 2 * (np.pi * f0 * tau) ** 2) * np.exp(-(np.pi * f0 * tau) ** 2)
    wav *= amplitude * rms / (np.abs(wav).max() + 1e-30)
    out = data.copy()
    for i, x in enumerate(np.asarray(offsets)):
        k = int(round((abs(x) / velocity) / DT))
        if half < k < ns - half - 1:
            out[i, k - half:k + half + 1] += wav
    return out


FIXTURE = REPO / "test_dataset" / "VikingAdversarial" / "A03_NOISE_ONLY.segy"


def a03_gather(cdp=1100):
    """The exact gather round 1 called INCONCLUSIVE."""
    if not FIXTURE.exists():
        raise unittest.SkipTest(f"fixture not present: {FIXTURE}")
    file_hdr, hdr = 3600, 240
    with open(FIXTURE, "rb") as f:
        f.seek(file_hdr)
        first = f.read(hdr)
    ns = int(np.frombuffer(first[114:116], dtype=">i2")[0])
    dt = int(np.frombuffer(first[116:118], dtype=">i2")[0]) * 1e-6
    stride = hdr + ns * 4
    ntr = (FIXTURE.stat().st_size - file_hdr) // stride
    keep_off, keep_data = [], []
    with open(FIXTURE, "rb") as f:
        for i in range(ntr):
            f.seek(file_hdr + i * stride)
            head = f.read(hdr)
            if int(np.frombuffer(head[20:24], dtype=">i4")[0]) != cdp:
                continue
            keep_off.append(abs(int(np.frombuffer(head[36:40], dtype=">i4")[0])))
            raw = np.frombuffer(f.read(ns * 4), dtype=">u4").astype(np.uint32)
            sign = 1.0 - 2.0 * ((raw >> 31) & 1).astype(np.float64)
            expo = ((raw >> 24) & 0x7F).astype(np.int32)
            mant = (raw & 0x00FFFFFF).astype(np.float64) / float(1 << 24)
            keep_data.append(sign * mant * np.power(16.0, (expo - 64).astype(float)))
    return np.asarray(keep_off, dtype=float), np.asarray(keep_data), dt


class BranchStatusTest(unittest.TestCase):
    """VALID, BROKEN, NOT_APPLICABLE -- and the difference between the last two."""

    def test_no_direct_wave_makes_a_standing_down_branch_not_applicable(self):
        rng = np.random.default_rng(7)
        off = offsets_spread()
        data = matched_noise(len(off), NS, rng)
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=False)
        self.assertEqual(got["direct_wave"]["value"], "ABSENT")
        statuses = set(got["branch_status"].values())
        self.assertIn(R.BRANCH_NOT_APPLICABLE, statuses)
        self.assertNotIn(R.BRANCH_BROKEN, statuses,
                         "a branch with no direct wave to suppress is not broken")

    def test_the_two_kinds_are_reported_separately(self):
        rng = np.random.default_rng(11)
        off = offsets_spread()
        data = matched_noise(len(off), NS, rng)
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=False)
        self.assertEqual(sorted(got["branches_not_applicable"]),
                         sorted(n for n, s in got["branch_status"].items()
                                if s == R.BRANCH_NOT_APPLICABLE))
        for name in got["branches_not_applicable"]:
            self.assertIn("premise does not hold",
                          got["branches"][name]["status_reason"])


class NegativeEvidenceTest(unittest.TestCase):
    """Case 1 and case 2: absence with, and without, the sensitivity to claim it."""

    def _noise_gather(self, seed=3, n=48):
        rng = np.random.default_rng(seed)
        off = offsets_spread(n)
        return off, matched_noise(n, NS, rng)

    def test_clean_noise_with_sensitivity_is_a_FAIL(self):
        """The round-1 defect, on the gather that produced it."""
        off, data, dt = a03_gather()
        got = R.assess(data, off, dt, 0.0, water=WATER, run_sensitivity=True)
        self.assertEqual(got["direct_wave"]["value"], "ABSENT")
        self.assertEqual(got["agreed_candidates"], [])
        self.assertTrue(got["raw_detector"]["valid"], got["raw_detector"])
        self.assertIn(R.BRANCH_NOT_APPLICABLE, set(got["branch_status"].values()))
        self.assertNotIn(R.BRANCH_BROKEN, set(got["branch_status"].values()))
        self.assertLessEqual(got["detection_threshold_x_rms"]["value"],
                             R.INFORMATIVE_THRESHOLD_X_RMS)
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.FAIL,
                         got["feasibility_reason"])
        self.assertIn("No reflection here", got["feasibility_reason"])

    def test_without_the_ladder_the_same_gather_is_INCONCLUSIVE(self):
        """No detection limit means no licence to call an absence a result."""
        off, data, dt = a03_gather()
        got = R.assess(data, off, dt, 0.0, water=WATER, run_sensitivity=False)
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE)

    def test_an_insensitive_gather_is_INCONCLUSIVE_not_FAIL(self):
        """Phase-random noise: no branch recovers an injected reflection until 1.6x the record RMS, so an absence
        here says something about what this gather could have shown, not about the subsurface."""
        off, data = self._noise_gather()
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        self.assertEqual(got["direct_wave"]["value"], "ABSENT")
        self.assertTrue(got["raw_detector"]["valid"])
        threshold = got["detection_threshold_x_rms"]["value"]
        self.assertTrue(threshold is None
                        or threshold > R.INFORMATIVE_THRESHOLD_X_RMS,
                        f"fixture is too sensitive to test this: {threshold}")
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE,
                         got["feasibility_reason"])
        self.assertIn("sensitivity", got["feasibility_reason"].lower())

    def test_the_conditions_are_all_required(self):
        sound = {"valid": True, "checks": {}, "failed": [], "reason": ""}
        broken = {"valid": False, "checks": {}, "failed": ["panel_varies"],
                  "reason": "x"}
        base = dict(direct_present=False, detector=sound, strongest_real=0.05,
                    level=0.10, agreed=[], threshold=0.4, run_sensitivity=True)
        self.assertTrue(R.negative_evidence_holds(**base))
        self.assertFalse(R.negative_evidence_holds(**{**base, "direct_present": True}))
        self.assertFalse(R.negative_evidence_holds(**{**base, "detector": broken}))
        self.assertFalse(R.negative_evidence_holds(**{**base, "strongest_real": 0.5}))
        self.assertFalse(R.negative_evidence_holds(**{**base, "agreed": [{"x": 1}]}))
        self.assertFalse(R.negative_evidence_holds(**{**base, "threshold": None}))
        self.assertFalse(R.negative_evidence_holds(**{**base, "threshold": 1.6}))
        self.assertFalse(R.negative_evidence_holds(**{**base,
                                                      "run_sensitivity": False}))

    def test_the_thresholds_are_the_existing_ones(self):
        """Phase 1 introduces no number of its own."""
        self.assertEqual(R.INFORMATIVE_THRESHOLD_X_RMS, 0.5)
        self.assertEqual(R.MIN_VOTERS, 2)


class PositiveTest(unittest.TestCase):
    """Case 3: no direct wave, but there IS a reflection."""

    def test_a_reflection_without_a_direct_wave_still_passes(self):
        rng = np.random.default_rng(13)
        off = offsets_spread()
        data = add_hyperbola(matched_noise(len(off), NS, rng), off,
                             t0=1.2, velocity=2000.0, amplitude=3.0)
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=False)
        self.assertEqual(got["direct_wave"]["value"], "ABSENT")
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.PASS,
                         got["feasibility_reason"])
        self.assertTrue(got["agreed_candidates"])


class BrokenBranchTest(unittest.TestCase):
    """Case 4: a direct wave IS present and a branch that was needed failed."""

    def test_a_broken_branch_with_a_direct_wave_present_is_INCONCLUSIVE(self):
        rng = np.random.default_rng(17)
        off = offsets_spread(n=48, lo=100.0, hi=1500.0)
        data = add_direct_wave(matched_noise(len(off), NS, rng), off)
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        if got["direct_wave"]["value"] not in ("PRESENT", "ROBUST"):
            self.skipTest("the fixture did not produce a detectable direct wave")
        # With a direct wave present, a branch standing down is a malfunction, not a premise failing, so the
        # negative path must stay shut whatever the branches say.
        self.assertNotEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.FAIL,
                            "an absence must not be claimed while a direct "
                            "wave is present and the branches are in doubt")
        self.assertNotIn(R.BRANCH_NOT_APPLICABLE,
                         set(got["branch_status"].values()),
                         "NOT_APPLICABLE means there was nothing to suppress; "
                         "there is a direct wave here")

    def test_the_negative_path_is_closed_whenever_a_direct_wave_is_present(self):
        sound = {"valid": True, "checks": {}, "failed": [], "reason": ""}
        self.assertFalse(R.negative_evidence_holds(
            direct_present=True, detector=sound, strongest_real=0.01,
            level=0.10, agreed=[], threshold=0.05, run_sensitivity=True))
        blocker = R._negative_path_blocker(True, sound, 0.01, 0.1, 0.05, True)
        self.assertIn("direct wave IS present", blocker)


class DetectorValidityTest(unittest.TestCase):
    """Case 5: the raw detector itself is not usable."""

    def test_a_degenerate_panel_is_not_a_sound_detector(self):
        flat = np.zeros((40, 50))
        level = 0.0
        lev = {"resolvable": True}
        got = R._detector_validity(flat, level, lev)
        self.assertFalse(got["valid"])
        self.assertIn("significance_level_measured", got["failed"])
        self.assertIn("panel_varies", got["failed"])

    def test_an_unreadable_velocity_axis_is_not_a_sound_detector(self):
        panel = np.random.default_rng(0).normal(size=(40, 50))
        got = R._detector_validity(panel, 0.1, {"resolvable": False})
        self.assertFalse(got["valid"])
        self.assertIn("velocity_axis_readable", got["failed"])

    def test_a_normal_panel_is_sound(self):
        panel = np.random.default_rng(0).normal(size=(40, 50))
        got = R._detector_validity(panel, 0.1, {"resolvable": True})
        self.assertTrue(got["valid"], got["failed"])

    def test_a_dead_gather_does_not_produce_a_FAIL(self):
        """All-zero traces: there is no detector to read, so nothing is concluded."""
        off = offsets_spread()
        data = np.zeros((len(off), NS))
        got = R.assess(data, off, DT, 0.0, water=WATER, run_sensitivity=True)
        self.assertFalse(got["raw_detector"]["valid"])
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE,
                         got.get("feasibility_reason"))


if __name__ == "__main__":
    unittest.main()
