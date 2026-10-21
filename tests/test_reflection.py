"""The three-branch reflection feasibility check."""

from __future__ import annotations

import os
import tempfile
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
# Every tool call writes an audit entry now, so the suite gets its own log: test runs in logs/processing.jsonl
# would corrupt the record the adversarial suite reads to decide whether a forbidden program ran.
os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))


from sumcp import claims as C          # noqa: E402
from sumcp import reflection as R      # noqa: E402

DT = 0.001
NS = 2000
WATER = 1492.0


def _ricker(t, tc, f0=60.0):
    a = (t - tc) * np.pi * f0
    return (1 - 2 * a ** 2) * np.exp(-a ** 2)


def _gather(reflection_amp=0.0, t_ref=0.6, v_ref=1900.0, noise=0.05, seed=0,
            direct_amp=3.0, ntr=120):
    rng = np.random.default_rng(seed)
    offsets = np.linspace(180.0, 2300.0, ntr)
    t = np.arange(NS) * DT
    data = np.zeros((ntr, NS))
    for i, x in enumerate(offsets):
        if direct_amp:
            data[i] += direct_amp * _ricker(t, x / WATER)
        if reflection_amp:
            data[i] += reflection_amp * _ricker(
                t, float(np.sqrt(t_ref ** 2 + (x / v_ref) ** 2)))
    data += noise * rng.standard_normal(data.shape)
    return data, offsets


class ClaimsTest(unittest.TestCase):

    def test_derived_inherits_the_weakest_input(self):
        obs = C.observed(3.125, "header")
        asm = C.assumed(1492.0, "default")
        self.assertEqual(C.derived(1.0, "fit", [obs])["class"], C.DERIVED)
        self.assertEqual(C.derived(1.0, "fit", [obs, asm])["class"], C.ASSUMED)
        self.assertFalse(C.is_established(C.hypothesized(1.0, "guess")))
        self.assertTrue(C.is_established(obs))


class BranchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        data, cls.off = _gather(noise=0.02)
        cls.data = R.bandpass(data, DT, 30, 250)
        cls.base = R.direct_stack_peak(cls.data, cls.off, DT, 0.0)

    def test_every_branch_suppresses_a_clean_direct_wave(self):
        for fn in (R.mute_predicted, R.subtract_template, R.suppress_slant):
            with self.subTest(branch=fn.__name__):
                out = fn(self.data, self.off, DT, 0.0)
                left = R.direct_stack_peak(out, self.off, DT, 0.0) / self.base
                self.assertLess(left, 0.6, f"left {left:.2f} of the direct wave")

    def test_slant_branch_does_not_add_energy(self):
        """The bug this test exists for: an inverse tau-p with a guessed normalisation returned 128% of the input
        energy and looked like a filter."""
        out = R.suppress_slant(self.data, self.off, DT, 0.0)
        self.assertLess(float(np.sqrt((out ** 2).mean())),
                        float(np.sqrt((self.data ** 2).mean())))

    def test_template_branch_does_not_subtract_itself(self):
        """Leave-one-out: on pure noise the template must not drive the stack to zero, which a self-inclusive
        template does whatever the data holds."""
        rng = np.random.default_rng(3)
        off = np.linspace(180.0, 2300.0, 120)
        data = R.bandpass(rng.standard_normal((120, NS)), DT, 30, 250)
        base = R.direct_stack_peak(data, off, DT, 0.0)
        left = R.direct_stack_peak(R.subtract_template(data, off, DT, 0.0),
                                   off, DT, 0.0) / base
        self.assertGreater(left, 0.3, f"removed {1 - left:.0%} of pure noise")

    def test_direct_wave_presence_is_tested_not_assumed(self):
        without, off = _gather(noise=0.02, direct_amp=0.0, reflection_amp=0.6)
        self.assertTrue(
            R._direct_wave_present(self.data, self.off, DT, 0.0, WATER)[0])
        self.assertFalse(
            R._direct_wave_present(R.bandpass(without, DT, 30, 250),
                                   off, DT, 0.0, WATER)[0])

    def test_batched_sinc_matches_the_direct_one(self):
        """The branch applies sinc(a(x_k - x_l)) through a rank-two identity and one fixed Cauchy matrix instead
        of building the matrix per frequency."""
        rng = np.random.default_rng(11)
        for spread in (np.sort(rng.uniform(0, 2200, 60)),
                       np.repeat(np.linspace(0, 2200, 30), 2)):  # duplicates
            x = spread - spread.mean()
            dx = x[:, None] - x[None, :]
            a = rng.uniform(0.003, 0.023, 20)
            z = rng.standard_normal((20, x.size)) + 1j * rng.standard_normal((20, x.size))
            want = np.stack([np.sinc(a[f] * dx) @ z[f] for f in range(a.size)])
            got = R._sinc_apply(z, x, dx, a)
            scale = np.abs(want).max()
            self.assertLess(float(np.abs(want - got).max()) / scale, 1e-9)

    def test_probe_avoids_the_rejected_slowness_band(self):
        """A probe at the water velocity is removed by the slant branch on purpose; placing one there makes a
        working filter look blind."""
        t0_grid = np.arange(0.1, 1.2, 0.02)
        v_grid = np.arange(1350.0, 3200.0, 50.0)
        semb = np.zeros((t0_grid.size, v_grid.size))
        t_probe, v_probe = R._pick_probe(semb, t0_grid, v_grid, WATER)
        self.assertGreater(v_probe, WATER + 400)
        self.assertGreaterEqual(t_probe, t0_grid[5])
        self.assertLessEqual(t_probe, t0_grid[-6])


class ControlTest(unittest.TestCase):
    """Both directions, or the verdict means nothing."""

    def test_positive_control_finds_a_planted_reflection(self):
        data, off = _gather(reflection_amp=0.6, noise=0.05)
        out = R.assess(data, off, DT, 0.0, t0_range=(0.1, 1.2),
                       run_sensitivity=False)
        hit = [c for c in out["agreed_candidates"]
               if abs(c["t0_s"] - 0.6) < 0.1 and abs(c["v_m_s"] - 1900) < 300]
        self.assertTrue(hit, out["agreed_candidates"])
        self.assertEqual(out["REFLECTION_PROCESSING_FEASIBLE"], R.PASS)

    def test_negative_control_fails_with_a_threshold_attached(self):
        data, off = _gather(reflection_amp=0.0, noise=0.05)
        out = R.assess(data, off, DT, 0.0, t0_range=(0.1, 1.2))
        self.assertEqual(out["REFLECTION_PROCESSING_FEASIBLE"], R.FAIL)
        self.assertIsNotNone(out["detection_threshold_x_rms"]["value"])
        self.assertLessEqual(out["detection_threshold_x_rms"]["value"],
                             R.INFORMATIVE_THRESHOLD_X_RMS)

    def test_an_insensitive_gather_is_inconclusive_not_negative(self):
        """The distinction the whole tool exists for: a gather that could not have shown a reflection has not
        shown that there is none."""
        data, off = _gather(reflection_amp=0.0, noise=0.05)
        out = R.assess(data, off, DT, 0.0, t0_range=(0.1, 1.2),
                       amplitudes=(1.6,))
        self.assertEqual(out["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE)

    def test_skipping_the_ladder_cannot_produce_a_negative(self):
        data, off = _gather(reflection_amp=0.0, noise=0.05)
        out = R.assess(data, off, DT, 0.0, t0_range=(0.1, 1.2),
                       run_sensitivity=False)
        self.assertEqual(out["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE)
        self.assertTrue(any("sensitivity ladder was skipped" in n
                            for n in out["notes"]), out["notes"])


class EvidenceStrengthTest(unittest.TestCase):
    """The direct-wave test is graded, not asserted."""

    def test_a_clean_direct_wave_is_robust(self):
        data, off = _gather(noise=0.02)
        got = R.direct_wave_evidence(data, off, DT, 0.0, WATER, 30, 250)
        self.assertEqual(got["verdict"], R.ROBUST)
        self.assertEqual(len(got["trials"]), 6)

    def test_no_direct_wave_reads_absent(self):
        data, off = _gather(direct_amp=0.0, reflection_amp=0.6, noise=0.02)
        got = R.direct_wave_evidence(data, off, DT, 0.0, WATER, 30, 250)
        self.assertEqual(got["verdict"], R.ABSENT)

    def test_a_weak_direct_wave_reads_fragile(self):
        """Detection that depends on how much data it is given must say so rather than collapsing to true or
        false."""
        data, off = _gather(direct_amp=0.35, noise=0.35, seed=5)
        got = R.direct_wave_evidence(data, off, DT, 0.0, WATER, 30, 250)
        hits = sum(t["detected"] for t in got["trials"])
        self.assertEqual(got["verdict"],
                         R.ROBUST if hits >= 5 else R.ABSENT if hits <= 0 else R.FRAGILE)
        self.assertIn(f"{hits} of", got["detected_in"])


class VotingTest(unittest.TestCase):
    """Who gets to veto."""

    def test_a_branch_that_adds_structure_loses_its_vote(self):
        report = {
            "predicted_mute": {"direct_wave_left_fraction": 0.2,
                               "outside_corridor_kept_fraction": 1.0},
            "template_subtraction": {"direct_wave_left_fraction": 0.6,
                                     "outside_corridor_kept_fraction": 0.9},
            "slant_domain": {"direct_wave_left_fraction": 3.4,
                             "outside_corridor_kept_fraction": 0.9},
        }
        voters, out = _vote(report, direct_present=True)
        self.assertEqual(voters, ["predicted_mute", "template_subtraction"])
        self.assertIn("adding structure", out["slant_domain"])

    def test_removing_the_direct_wave_is_not_grounds_for_disqualification(self):
        """The first version of this rule counted how much of the whole record survived, which disqualified the
        branch that worked on a gather where the direct wave IS most of the record."""
        report = {name: {"direct_wave_left_fraction": 0.05,
                         "outside_corridor_kept_fraction": 0.95}
                  for name in ("predicted_mute", "template_subtraction",
                               "slant_domain")}
        voters, out = _vote(report, direct_present=True)
        self.assertEqual(len(voters), 3)
        self.assertEqual(out, {})

    def test_with_no_direct_wave_a_branch_that_rewrites_the_record_is_dropped(self):
        report = {
            "predicted_mute": {"direct_wave_left_fraction": 0.5,
                               "outside_corridor_kept_fraction": 1.0},
            "template_subtraction": {"direct_wave_left_fraction": 1.0,
                                     "outside_corridor_kept_fraction": 0.999},
            "slant_domain": {"direct_wave_left_fraction": 3.4,
                             "outside_corridor_kept_fraction": 0.757},
        }
        voters, out = _vote(report, direct_present=False)
        self.assertEqual(voters, ["predicted_mute", "template_subtraction"])
        self.assertIn("no direct wave", out["slant_domain"])


def _vote(report, direct_present):
    """Mirror of the rule in assess(), kept here so the rule itself is tested rather than only its effect on a
    whole gather."""
    voters, disqualified = [], {}
    for name, branch in report.items():
        kept = branch["outside_corridor_kept_fraction"]
        left = branch["direct_wave_left_fraction"]
        if direct_present and left > 1.0:
            disqualified[name] = "adding structure"
        elif not direct_present and kept < R.MIN_OUTSIDE_KEPT_NO_DIRECT:
            disqualified[name] = "no direct wave here to suppress"
        else:
            voters.append(name)
    return voters, disqualified


class SeparabilityTest(unittest.TestCase):
    """A candidate that parallels the direct wave is residue, and one that crosses it is not, the threshold
    between them was calibrated, not guessed, so it is worth holding in place."""

    def test_real_reflections_clear_the_threshold_and_residue_does_not(self):
        offsets = np.linspace(177.0, 2373.0, 194)
        min_sep = 2.0 / 30.0
        real = [(1.95, 2050.0), (0.35, 2200.0), (0.60, 1900.0)]
        residue = [(0.15, 1650.0), (0.05, 1500.0)]
        for t_zero, v in real:
            frac, _ = R._direct_separation(t_zero, v, offsets, WATER, min_sep)
            self.assertGreaterEqual(frac, R.SEPARATION_FRACTION, f"{t_zero},{v}")
        for t_zero, v in residue:
            frac, _ = R._direct_separation(t_zero, v, offsets, WATER, min_sep)
            self.assertLess(frac, R.SEPARATION_FRACTION, f"{t_zero},{v}")


if __name__ == "__main__":
    unittest.main()


class VelocityLeverageTest(unittest.TestCase):
    """A semblance scan reads velocity from curvature across offset."""

    def _gather(self, offsets, seed=0, flat=True):
        rng = np.random.default_rng(seed)
        ns, dt = 700, 0.004
        data = rng.normal(0, 0.1, (len(offsets), ns))
        if flat:
            data[:, 150:160] += 1.0
        else:
            t = np.sqrt(0.6 ** 2 + (np.asarray(offsets) / 2000.0) ** 2)
            for i, tt in enumerate(t):
                k = int(tt / dt)
                if 0 < k < ns - 5:
                    data[i, k:k + 5] += 1.0
        return data, dt

    def test_a_stacked_section_is_inconclusive_not_a_pass(self):
        offsets = np.zeros(200)
        data, dt = self._gather(offsets)
        got = R.assess(data, offsets, dt, 0.0, run_sensitivity=False)
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE)
        self.assertFalse(got["velocity_leverage"]["resolvable"])
        self.assertEqual(got["agreed_candidates"], [])
        self.assertIn("every trace sits at", got["feasibility_reason"])

    def test_nothing_is_computed_once_the_axis_is_degenerate(self):
        """Reporting branch scores from a scan that cannot resolve velocity would invite exactly the reading the
        check exists to prevent."""
        offsets = np.zeros(200)
        data, dt = self._gather(offsets)
        got = R.assess(data, offsets, dt, 0.0, run_sensitivity=False)
        self.assertEqual(got["branches"], {})
        self.assertIsNone(got["detection_threshold_x_rms"]["value"])

    def test_a_real_gather_is_unaffected(self):
        offsets = np.linspace(200.0, 3000.0, 200)
        data, dt = self._gather(offsets, flat=False)
        got = R.assess(data, offsets, dt, 0.0, run_sensitivity=False)
        self.assertTrue(got["velocity_leverage"]["resolvable"])
        self.assertGreater(got["velocity_leverage"]["moveout_spread_samples"],
                           R.MIN_VELOCITY_LEVERAGE_SAMPLES)

    def test_a_narrow_far_offset_band_does_not_resolve_velocity(self):
        """Rewritten in v0.11.0, and the old version is the defect it fixes."""
        offsets = np.linspace(2000.0, 2010.0, 200)
        data, dt = self._gather(offsets)
        got = R.assess(data, offsets, dt, 0.0, run_sensitivity=False)
        self.assertFalse(got["velocity_leverage"]["resolvable"])
        self.assertEqual(got["REFLECTION_PROCESSING_FEASIBLE"], R.INCONCLUSIVE)
        self.assertLess(got["velocity_leverage"]["moveout_spread_samples"],
                        R.MIN_VELOCITY_LEVERAGE_SAMPLES)

    def test_a_wide_aperture_at_the_same_far_offsets_does_resolve(self):
        """The control for the test above: same far offsets, real aperture."""
        offsets = np.linspace(200.0, 2010.0, 200)
        data, dt = self._gather(offsets)
        got = R.assess(data, offsets, dt, 0.0, run_sensitivity=False)
        self.assertTrue(got["velocity_leverage"]["resolvable"])
