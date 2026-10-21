"""v0.20 checks: R3 relocation, S1 scope, T1 datum shift, RS residual statics, G1 feasibility gate, G2 two-window
injection, W1 reliability warning."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import cmp, evidence, runner, sufile                  # noqa: E402
from sumcp import conditioning as K                              # noqa: E402
from sumcp import iterate as I                                   # noqa: E402
from sumcp import stack as S                                     # noqa: E402

HAVE_SU = all(runner.find_program(p) for p in ("suresstat", "sunull", "sushw"))


class Relocation(unittest.TestCase):
    """R3: relocated supergathers must read different traces from the failed one."""

    def test_end_location_moves_by_an_eighth_and_a_quarter_spacing(self):
        analysed = [637, 740, 843, 945, 1048]
        eligible = list(range(560, 1110))
        c = I.relocation_candidates(1048, eligible, analysed, 103)
        self.assertEqual(c, [1035, 1061, 1022])       # inward first on ties

    def test_candidates_are_outside_the_failed_supergather(self):
        analysed = [637, 740, 843, 945, 1048]
        c = I.relocation_candidates(843, list(range(560, 1110)), analysed, 103)
        self.assertTrue(all(abs(x - 843) > I.SUPERGATHER_HALF * 2 for x in c))

    def test_snaps_to_eligible_and_skips_taken(self):
        c = I.relocation_candidates(150, [137, 162, 170], [110, 130, 150, 170, 190], 40)
        # targets 145/155 have nothing eligible within 2 bins; 140 -> 137?
        self.assertEqual(c, [162])

    def test_zero_spacing_gives_nothing(self):
        self.assertEqual(I.relocation_candidates(150, range(100, 200), [150], 0), [])


class Scope(unittest.TestCase):
    def _grade(self, cdps_valid):
        reports = [{"cdp": c, "valid": v} for c, v in cdps_valid]
        return S.grade_velocity_locations(reports), reports

    def test_end_failure_is_scoped(self):
        grade, reports = self._grade([(637, 1), (740, 1), (843, 1), (945, 1), (1048, 0)])
        self.assertFalse(grade["ok"])
        self.assertEqual(I.scope_from_grade(grade, reports), [637, 945])

    def test_too_few_valid_is_not_scoped(self):
        grade, reports = self._grade([(637, 1), (740, 1), (843, 0), (945, 0), (1048, 0)])
        self.assertIsNone(I.scope_from_grade(grade, reports))

    def test_short_span_is_not_scoped(self):
        grade, reports = self._grade([(637, 0), (740, 1), (760, 1), (780, 1), (1048, 0)])
        self.assertLess(grade["coverage_fraction"], I.SCOPE_MIN_FRACTION)
        self.assertIsNone(I.scope_from_grade(grade, reports))

    def test_passing_model_has_no_scope(self):
        grade, reports = self._grade([(637, 1), (740, 1), (843, 1), (945, 1), (1048, 1)])
        self.assertIsNone(I.scope_from_grade(grade, reports))


class Shifts(unittest.TestCase):
    def test_shift_samples(self):
        x = np.arange(10.0)
        np.testing.assert_array_equal(I.shift_samples(x, 3)[:7], x[3:])
        self.assertTrue(np.all(I.shift_samples(x, 3)[7:] == 0))
        np.testing.assert_array_equal(I.shift_samples(x, -2)[2:], x[:8])
        self.assertTrue(np.all(I.shift_samples(x, 20) == 0))

    def test_trace_statics_follow_suresstat_sign(self):
        # an event delayed by +d samples is corrected by a static of +d
        tr = np.zeros((2, 50))
        tr[0, 25] = 1
        tr[1, 22] = 1
        out = I.apply_trace_statics(tr, [5, 2])
        self.assertEqual(int(np.argmax(out[0])), 20)
        self.assertEqual(int(np.argmax(out[1])), 20)


class DatumCheck(unittest.TestCase):
    TZ = {"intercept_s": 0.108, "tolerance_s": 0.115, "direct_velocity_m_s": 1500.0,
          "gather": {"fldr": 63}}

    def test_refuses_without_a_measured_lag(self):
        with self.assertRaises(ValueError):
            I._datum_check({"status": "UNKNOWN"}, {"reason": "direct wave absent"})

    def test_refuses_within_a_quarter_period(self):
        with self.assertRaises(ValueError):
            I._datum_check({"status": "PASS"}, {**self.TZ, "intercept_s": -0.002})

    def test_accepts_displaced_and_failed(self):
        self.assertEqual(I._datum_check({"status": "PASS"}, self.TZ)[0], 0.108)
        self.assertEqual(I._datum_check({"status": "FAIL"},
                                        {**self.TZ, "intercept_s": 0.148})[0], 0.148)

    def test_gather_key(self):
        self.assertEqual(I._gather_key({"fldr": 63}), ("fldr", 63))
        self.assertEqual(I._gather_key({"cdp": 1100}), ("cdp", 1100))
        self.assertEqual(I._gather_key({"channel": 5}), ("tracf", 5))

    def test_time_datum_discloses_the_shift(self):
        tz = {"evidence": {"intercept_s": 0.002, "tolerance_s": 0.115,
                           "datum_shift_applied_s": -0.108,
                           "before_datum_shift": {"intercept_s": 0.108}}}
        d = S.time_datum(tz)
        self.assertEqual(d["level"], "WITHIN_RESOLUTION")
        self.assertEqual(d["datum_shift_applied_ms"], -108.0)
        self.assertIn("zero-phase-equivalent datum", d["statement"])


class SoloOperations(unittest.TestCase):
    CTX = {"dt_s": 0.002, "max_offset_m": 2100.0, "direct_velocity_m_s": 1500.0}

    def test_time_shifting_operations_run_alone(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "datum_shift"}, {"op": "agc"}], self.CTX)
        with self.assertRaises(ValueError):
            K.resolve([{"op": "bandpass", "f": [3, 5, 25, 35]},
                       {"op": "residual_statics"}], self.CTX)
        self.assertEqual(K.resolve([{"op": "datum_shift"}], self.CTX)[0][0], "datum_shift")

    def test_they_take_no_parameters(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "datum_shift", "shift_s": 0.1}], self.CTX)
        with self.assertRaises(ValueError):
            K.resolve([{"op": "residual_statics", "ntpick": 99}], self.CTX)

    def test_menu_lists_their_gates(self):
        m = K.menu()
        self.assertIn("gate", m["datum_shift"])
        self.assertIn("gate", m["residual_statics"])


class TwoWindowInjection(unittest.TestCase):
    def test_shallow_set_sits_above_the_last_direct_arrival(self):
        data = np.random.default_rng(0).standard_normal((24, 1301))
        off = np.linspace(100, 2100, 24)
        sets = K.inject_sets(data, off, 0.002, 0.0, 1.4, 2.602, 1500.0, 8.7)
        t = np.arange(1301) * 0.002
        near = sets["shallow"][0]                       # nearest trace
        self.assertLess(t[int(np.argmax(np.abs(near)))], 1.4)
        self.assertGreater(t[int(np.argmax(np.abs(sets["deep"][0])))], 1.4)

    def test_a_mute_above_the_direct_wave_fails_the_shallow_set(self):
        data = np.random.default_rng(1).standard_normal((24, 1301))
        off = np.linspace(100, 2100, 24)
        dt = 0.002
        sets = K.inject_sets(data, off, dt, 0.0, 1.4, 2.602, 1500.0, 8.7)
        t = np.arange(1301) * dt

        def mute(x):
            y = x.copy()
            for i, o in enumerate(off):
                y[i, t < o / 1500.0 + 0.1] = 0
            return y
        self.assertGreaterEqual(K.preservation(mute(data + sets["deep"]), mute(data),
                                               sets["deep"]), 0.9)
        self.assertLess(K.preservation(mute(data + sets["shallow"]), mute(data),
                                       sets["shallow"]), 0.9)

    def test_reliability(self):
        rng = np.random.default_rng(2)
        a = rng.standard_normal(80)
        self.assertAlmostEqual(K.reliability(a, a), 1.0)
        self.assertLess(K.reliability(a, rng.standard_normal(80)), 0.5)
        self.assertEqual(K.reliability(np.zeros(5), np.zeros(5)), 0.0)


class ReliabilityWarning(unittest.TestCase):
    def test_cases_from_the_ladders(self):
        warn = lambda lvl, ceil, sup: S.reliability_warning(
            {"level": lvl, "correlation_ceiling": ceil}, {"level": sup})["level"]
        self.assertEqual(warn("CLEAR", 0.971, "PARTIAL"), "OK")      # statics 15 ms, good
        self.assertEqual(warn("CLEAR", 0.903, "PARTIAL"), "WARN")    # band noise 1.6x, bad
        self.assertEqual(warn("NOISE_LIMITED", 0.81, "PARTIAL"), "WARN")
        self.assertEqual(warn("CLEAR", 0.999, "MEASURED"), "OK")     # v2
        self.assertEqual(warn("NOISE_LIMITED", 0.88, "MEASURED"), "WARN")

    def test_feasibility_disclosure(self):
        self.assertIsNone(S.feasibility_disclosure({"status": "PASS"}))
        d = S.feasibility_disclosure({"status": "UNKNOWN",
                                      "evidence": {"verdict": "INCONCLUSIVE"}})
        self.assertEqual(d["status"], "INCONCLUSIVE")


class FeasibilityGate(unittest.TestCase):
    def _manifest(self, status, verdict=None):
        m = {"dataset_id": "fixture", "capabilities": {}}
        for name in cmp.STACK_TRACK_PREREQUISITES:
            if name != "reflection.processing_feasible":
                evidence.set_capability(m, name, evidence.PASS, {}, "test", "run")
        if status is not None:
            evidence.set_capability(m, "reflection.processing_feasible", status,
                                    {"verdict": verdict} if verdict else {}, "test", "run",
                                    notes=["measured"])
        return m

    def test_inconclusive_is_admitted(self):
        self.assertEqual(cmp.feasibility_gate(
            self._manifest(evidence.UNKNOWN, "INCONCLUSIVE")), "INCONCLUSIVE")

    def test_pass_is_admitted(self):
        self.assertEqual(cmp.feasibility_gate(self._manifest(evidence.PASS, "PASS")), "PASS")

    def test_fail_and_never_evaluated_still_refuse(self):
        with self.assertRaises(evidence.PrerequisiteError):
            cmp.feasibility_gate(self._manifest(evidence.FAIL, "FAIL"))
        with self.assertRaises(evidence.PrerequisiteError):
            cmp.feasibility_gate(self._manifest(None))
        with self.assertRaises(evidence.PrerequisiteError):
            cmp.feasibility_gate(self._manifest(evidence.UNKNOWN))   # no verdict recorded

    def test_other_prerequisites_still_gate(self):
        m = self._manifest(evidence.UNKNOWN, "INCONCLUSIVE")
        evidence.set_capability(m, "geometry.receiver_positions_trustworthy",
                                evidence.FAIL, {}, "test", "run", notes=["copied headers"])
        with self.assertRaises(evidence.PrerequisiteError):
            cmp.feasibility_gate(m)


@unittest.skipUnless(HAVE_SU, "SU programs not installed")
class ResidualStaticsOnSynthetic(unittest.TestCase):
    """suresstat recovers known surface-consistent statics, with the sign apply uses, and finds nothing to repeat
    on a statics-free line."""

    def _line(self, tmp, sigma_ms):
        nshot, nch, ns, dt = 40, 24, 700, 0.004
        rng = np.random.default_rng(5)
        sx = np.repeat(np.arange(nshot) * 20.0, nch)
        off = np.tile(100 + np.arange(nch) * 40.0, nshot)
        gx = sx + off
        fldr = np.repeat(np.arange(1, nshot + 1), nch)
        cdp = np.rint((sx + gx) / 20).astype(int)
        ug, ig = np.unique(gx, return_inverse=True)
        s_true = rng.normal(0, sigma_ms, nshot)
        r_true = rng.normal(0, sigma_ms, ug.size)
        tau = s_true[fldr - 1] + r_true[ig]
        t = np.arange(ns) * dt
        data = sum(K.ricker(t[None, :] - (t0 + tau[:, None] / 1000), 15.0)
                   for t0 in (0.8, 1.4, 2.0))
        data = data + 0.1 * rng.standard_normal(data.shape)
        env = {**os.environ, **runner.su_env()}
        with open(tmp / "b.su", "wb") as fh:
            p1 = subprocess.Popen([runner.find_program("sunull"), f"nt={ns}",
                                   f"ntr={sx.size}", f"dt={dt}"], stdout=subprocess.PIPE,
                                  env=env)
            subprocess.run([runner.find_program("sushw"), "key=fldr", "a=1"],
                           stdin=p1.stdout, stdout=fh, env=env, check=True)
            p1.stdout.close()
            p1.wait()
        g = sufile.geometry(tmp / "b.su")
        sufile.write_header_columns(tmp / "b.su", tmp / "h.su",
                                    {"fldr": fldr, "cdp": cdp, "gx": gx.astype(int)})
        raw = np.frombuffer((tmp / "h.su").read_bytes(), np.uint8).reshape(sx.size, -1)
        (tmp / "d.su").write_bytes(K.write_block(raw, data, g))
        ranks = (I._ranks(fldr), I._ranks(np.stack([gx, 0 * gx], 1)), I._ranks(cdp))
        return ranks, s_true, r_true

    def test_recovers_statics_and_repeats_between_halves(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ranks, s_true, _ = self._line(tmp, 12.0)
            cr = ranks[2]
            full = I._suresstat(tmp / "d.su", ranks, np.ones(cr.size, bool), 9, tmp, "a")
            self.assertGreater(np.corrcoef(full[0][1:], s_true)[0, 1], 0.9)
            self.assertGreater(np.polyfit(s_true, full[0][1:], 1)[0], 0.8)   # sign
            ho = I._suresstat(tmp / "d.su", ranks, cr % 2 == 1, 9, tmp, "o")
            he = I._suresstat(tmp / "d.su", ranks, cr % 2 == 0, 9, tmp, "e")
            self.assertGreaterEqual(K.reliability(ho[0][1:], he[0][1:]), K.RELIABILITY_MIN)

    def test_statics_free_line_has_nothing_to_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ranks, _, _ = self._line(tmp, 0.0)
            cr = ranks[2]
            ho = I._suresstat(tmp / "d.su", ranks, cr % 2 == 1, 9, tmp, "o")
            he = I._suresstat(tmp / "d.su", ranks, cr % 2 == 0, 9, tmp, "e")
            self.assertLess(K.reliability(ho[0][1:], he[0][1:]), K.RELIABILITY_MIN)


if __name__ == "__main__":
    unittest.main()
