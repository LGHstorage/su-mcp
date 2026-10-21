"""v0.19 checks: conditioning registry and QC gate, bounded re-picking."""

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

from sumcp import config, runner, sufile, tools                     # noqa: E402
from sumcp import conditioning as K                         # noqa: E402
from sumcp import iterate as I                              # noqa: E402
from sumcp import stack as S                                # noqa: E402

CTX = {"dt_s": 0.002, "max_offset_m": 3000.0, "direct_velocity_m_s": 1500.0}
HAVE_SU = all(runner.find_program(p) for p in ("sufilter", "sudipfilt", "sumute",
                                               "sunull", "sushw"))


class Registry(unittest.TestCase):
    def test_every_program_is_trusted_not_agent_reachable_by_name(self):
        for name, entry in K.REGISTRY.items():
            program = entry["program"].split()[0]
            if program == "in-process":          # v0.20 datum_shift: numpy only
                continue
            self.assertIn(program, config.TRUSTED_SU_COMMANDS, name)
        for gated in ("sudipfilt", "supef", "sumute"):
            self.assertNotIn(gated, config.ALLOWED_SU_COMMANDS)

    def test_menu_has_no_code(self):
        for entry in K.menu().values():
            self.assertNotIn("build", entry)
            self.assertIn("purpose", entry)
            self.assertIn("caution", entry)

    def test_tools_are_exposed(self):
        for name in ("conditioning_menu", "condition_gathers", "refine_velocity"):
            self.assertIn(name, tools.__all__)
        self.assertTrue(tools.conditioning_menu()["ok"])


class Resolve(unittest.TestCase):
    def test_at_most_three_operations(self):
        ops = [{"op": "agc"}] * 4
        with self.assertRaises(ValueError):
            K.resolve(ops, CTX)
        self.assertEqual(len(K.resolve(ops[:3], CTX)), 3)

    def test_unknown_operation(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "suradon"}], CTX)
        with self.assertRaises(ValueError):
            K.resolve([], CTX)

    def test_bandpass_corners_must_rise_below_nyquist(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "bandpass", "f": [5, 3, 25, 35]}], CTX)
        with self.assertRaises(ValueError):
            K.resolve([{"op": "bandpass", "f": [5, 10, 200, 300]}], CTX)
        (_, prog, args, pg), = K.resolve([{"op": "bandpass", "f": [3, 5, 25, 35]}], CTX)
        self.assertEqual((prog, pg), ("sufilter", False))

    def test_mute_needs_measured_direct_velocity(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "mute_direct"}], {**CTX, "direct_velocity_m_s": None})
        (_, prog, args, _), = K.resolve([{"op": "mute_direct"}], CTX)
        self.assertEqual(args["xmute"], [-3000.0, 0, 3000.0])
        self.assertAlmostEqual(args["tmute"][0], 2.1)

    def test_ranges_are_enforced(self):
        with self.assertRaises(ValueError):
            K.resolve([{"op": "agc", "window_s": 5}], CTX)
        with self.assertRaises(ValueError):
            K.resolve([{"op": "dip_filter", "reject_below_m_s": 50}], CTX)
        with self.assertRaises(ValueError):
            K.resolve([{"op": "predictive_decon", "minlag_s": 0.1, "maxlag_s": 0.05}], CTX)

    def test_arguments_pass_the_parameter_policy(self):
        for ops in ([{"op": "bandpass", "f": [3, 5, 25, 35]}], [{"op": "agc"}],
                    [{"op": "mute_direct"}],
                    [{"op": "predictive_decon", "minlag_s": 0.02, "maxlag_s": 0.2}]):
            for _, _, args, _ in K.resolve(ops, CTX):
                runner.validate_params(args)


class Injection(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.off = np.linspace(100, 3000, 40)
        self.data = rng.standard_normal((40, 1300))

    def test_events_sit_below_the_direct_wave(self):
        ev = K.inject_events(self.data, self.off, 0.002, 0.0, 2.0, 2.6, 1500.0, 20.0)
        t = np.arange(1300) * 0.002
        energy = (ev ** 2).sum(axis=0)
        self.assertLess(energy[t < 1.9].sum(), 1e-3 * energy.sum())

    def test_window_too_short(self):
        self.assertIsNone(K.inject_events(self.data, self.off, 0.002, 0.0, 2.4, 2.6,
                                          1500.0, 20.0))

    def test_identity_and_linear_filters(self):
        ev = K.inject_events(self.data, self.off, 0.002, 0.0, 1.0, 2.6, 1500.0, 20.0)
        self.assertAlmostEqual(K.preservation(self.data + ev, self.data, ev), 1.0)
        self.assertEqual(K.preservation(self.data * 0, self.data * 0, ev), 0.0)

        def band(x, lo, hi):
            f = np.fft.rfftfreq(x.shape[1], 0.002)
            s = np.fft.rfft(x, axis=1)
            s[:, (f < lo) | (f > hi)] = 0
            return np.fft.irfft(s, n=x.shape[1], axis=1)
        keep = K.preservation(band(self.data + ev, 3, 40), band(self.data, 3, 40), ev)
        lose = K.preservation(band(self.data + ev, 45, 90), band(self.data, 45, 90), ev)
        self.assertGreaterEqual(keep, K.PRESERVATION_MIN)
        self.assertLess(lose, K.PRESERVATION_MIN)


class Bookkeeping(unittest.TestCase):
    def test_gather_runs(self):
        self.assertEqual(I.gather_runs([5, 5, 6, 6, 6, 8]),
                         [(5, 0, 2), (6, 2, 5), (8, 5, 6)])
        with self.assertRaises(ValueError):
            I.gather_runs([5, 6, 5])

    def test_supergather_clips_at_line_ends(self):
        line = list(range(100, 120))
        self.assertEqual(I.supergather_cdps(line, 110, 2), [108, 109, 110, 111, 112])
        self.assertEqual(I.supergather_cdps(line, 100, 2), [100, 101, 102])
        self.assertEqual(len(I.supergather_cdps(line, 110, 4)), 9)
        with self.assertRaises(ValueError):
            I.supergather_cdps(line, 200, 2)

    def test_relocation_stays_within_a_quarter_spacing(self):
        # v0.20 R3 replaced the v0.19 nearest-CMP rule; see test_v020_checks.
        eligible = list(range(100, 200))
        analysed = [110, 130, 150, 170, 190]
        c = I.relocation_candidates(150, eligible, analysed, 20)
        self.assertTrue(all(0 < abs(x - 150) <= 5 + I.RELOCATE_SNAP_BINS for x in c))
        self.assertEqual(I.relocation_candidates(150, [150, 130], analysed, 20), [])

    def test_budgets_are_the_declared_ones(self):
        self.assertEqual(S.MAX_VELOCITY_ANALYSES, 6)   # v0.26 DMO: 4 -> 6
        self.assertEqual(I.MAX_REFINE_ATTEMPTS, 3)
        self.assertEqual(K.MAX_PASSES, 3)              # v0.26 DMO: 2 -> 3
        self.assertEqual(K.MAX_OPERATIONS, 3)
        self.assertTrue(issubclass(S.BudgetExhausted, ValueError))


@unittest.skipUnless(HAVE_SU, "SU programs not installed")
class ChainOnRealPrograms(unittest.TestCase):
    """The chain runs the real programs and the gate separates in-band from out-of-band."""

    def _gather(self, tmp):
        """A gather written by SU itself, so it has the byte order SU expects."""
        rng = np.random.default_rng(1)
        off = np.arange(100, 3100, 100)
        env = {**os.environ, **runner.su_env()}
        with open(tmp / "blank.su", "wb") as fh:
            p1 = subprocess.Popen([runner.find_program("sunull"), "nt=1300",
                                   f"ntr={off.size}", "dt=0.002"],
                                  stdout=subprocess.PIPE, env=env)
            subprocess.run([runner.find_program("sushw"), "key=cdp,offset",
                            "a=7,100", "b=0,100"], stdin=p1.stdout, stdout=fh,
                           env=env, check=True)
            p1.stdout.close()
            p1.wait()
        self.geom = sufile.geometry(tmp / "blank.su")
        raw = np.frombuffer((tmp / "blank.su").read_bytes(), np.uint8).reshape(off.size, -1)
        data = 0.1 * rng.standard_normal((off.size, 1300))
        (tmp / "g.su").write_bytes(K.write_block(raw, data, self.geom))
        return data, off

    def _qc(self, ops, tmp, data, off):
        steps = K.resolve(ops, CTX)
        raw = np.frombuffer((tmp / "g.su").read_bytes(), np.uint8).reshape(off.size, -1)
        ev = K.inject_events(data, off, 0.002, 0.0, 1.0,
                             2.6, 1500.0, 15.0)
        (tmp / "i.su").write_bytes(K.write_block(raw, data + ev, self.geom))
        I._apply_chain(steps, tmp / "g.su", tmp / "g_o.su", tmp)
        I._apply_chain(steps, tmp / "i.su", tmp / "i_o.su", tmp)
        rd = lambda p: sufile.read_traces(p, np.arange(off.size)).astype(float)
        return K.preservation(rd(tmp / "i_o.su"), rd(tmp / "g_o.su"), ev)

    def test_bandpass_in_and_out_of_band(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            data, off = self._gather(tmp)
            self.assertGreaterEqual(self._qc([{"op": "bandpass", "f": [3, 5, 25, 35]}],
                                             tmp, data, off), K.PRESERVATION_MIN)
            self.assertLess(self._qc([{"op": "bandpass", "f": [30, 35, 60, 70]}],
                                     tmp, data, off), K.PRESERVATION_MIN)

    def test_dip_filter_runs_per_gather_and_keeps_trace_count(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            data, off = self._gather(tmp)
            p = self._qc([{"op": "dip_filter", "reject_below_m_s": 1000}], tmp, data, off)
            self.assertTrue(-1.0 <= p <= 1.0)
            self.assertEqual((tmp / "g_o.su").stat().st_size, (tmp / "g.su").stat().st_size)


if __name__ == "__main__":
    unittest.main()
