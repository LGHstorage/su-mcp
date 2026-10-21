"""v0.24 checks: migration velocity, Dix, the impulse gate (M1), inheritance, gating."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import config, evidence, runner                        # noqa: E402
from sumcp import migrate as M                                    # noqa: E402

HAVE_SU = runner.find_program("sumigps") is not None


def _fn(pairs):
    return [{"t0_s": t, "v_m_s": v} for t, v in pairs]


class Velocity(unittest.TestCase):
    def test_dix_of_constant_is_constant(self):
        v = M.dix(np.full(500, 2000.0), 0.004)
        self.assertTrue(np.allclose(v, 2000.0))

    def test_dix_recovers_two_layers(self):
        dt, n = 0.002, 1000
        t = np.arange(n) * dt
        vint = np.where(t < 1.0, 1500.0, 2500.0)
        vrms = np.sqrt(np.cumsum(vint ** 2) / np.arange(1, n + 1))
        got = M.dix(vrms, dt)
        self.assertTrue(np.allclose(got[10:490], 1500.0, rtol=1e-3))
        self.assertTrue(np.allclose(got[520:], 2500.0, rtol=1e-3))

    def test_rms_grid_interpolates_slowness_squared_and_holds_ends(self):
        t = np.array([0.0, 1.0])
        locs = [{"cdp": 10, "function": _fn([(0, 1500.0), (1, 1500.0)])},
                {"cdp": 20, "function": _fn([(0, 3000.0), (1, 3000.0)])}]
        g = M.rms_grid(locs, [0, 10, 15, 20, 30], t)
        mid = 1 / np.sqrt(0.5 / 1500 ** 2 + 0.5 / 3000 ** 2)
        self.assertTrue(np.allclose(g[:, 0], [1500, 1500, mid, 3000, 3000]))

    def test_lateral_spread_counts_only_supported_times(self):
        t = np.arange(0, 2.0, 0.1)
        locs = [{"cdp": 1, "function": _fn([(0, 1500.0), (2, 2000.0)])},
                {"cdp": 2, "function": _fn([(0, 1500.0), (2, 3000.0)])}]
        s = M.lateral_spread(locs, {1: 0.5, 2: 0.5}, t)
        self.assertLess(s["spread"], 0.2)
        s2 = M.lateral_spread(locs, {1: 1.9, 2: 1.9}, t)
        self.assertGreater(s2["spread"], s["spread"])


class FocusWindows(unittest.TestCase):
    def test_windows_scale_with_the_period(self):
        # the gate was first written at 20 Hz, 2 ms, 10 m, 1800 m/s: +-12 samples, +-2 traces
        ht, hx, _, _ = M.focus_windows(0.002, 10.0, 1 / 20.0, 1800.0)
        self.assertEqual((ht, hx), (12, 2))
        ht, hx, _, _ = M.focus_windows(0.002, 10.0, 1 / 5.76, 2000.0)
        self.assertEqual(ht, 43)
        self.assertGreater(hx, 2)

    def test_a_perfect_point_focuses(self):
        mig = np.zeros((101, 801))
        t = (np.arange(801) - 400) * 0.002
        a = (np.pi * 20 * t) ** 2
        mig[50] = (1 - 2 * a) * np.exp(-a)
        f = M.focus(mig, 50, 0.8, 0.002, 0.05, 10.0, 1800.0)
        self.assertTrue(f["ok"])
        self.assertGreater(f["focus"], 0.9)   # a Ricker keeps ~95% within +-T/2


@unittest.skipUnless(HAVE_SU, "SU sumigps not installed")
class ImpulseGateOnSynthetic(unittest.TestCase):
    """The gate must pass the right operator and velocity and fail the usual mistakes."""

    def _run(self, vint_for_migration, dx_for_migration):
        ns, dt, ntr, dx = 1001, 0.002, 300, 10.0
        t = np.arange(ns) * dt
        vint = 1500 + 2000 * t / 2.0
        vrms = np.sqrt(np.cumsum(vint ** 2) / np.arange(1, ns + 1))
        apexes = [(75, 0.6), (150, 1.0), (225, 1.4)]
        imp = M.impulse_section(ntr, ns, dt, dx, 20.0, apexes,
                                lambda i, t0: float(np.interp(t0, t, vrms)))
        hdr = np.zeros((ntr, 60), dtype="<i4")
        h16 = hdr.view("<i2")
        hdr[:, 0] = np.arange(1, ntr + 1)
        hdr[:, 5] = np.arange(1000, 1000 + ntr)
        h16[:, 57] = ns
        h16[:, 58] = int(dt * 1e6)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = tmp / "imp.su"
            p.write_bytes(np.concatenate([hdr.view("u1"), imp.astype("<f4").view("u1")],
                                         axis=1).tobytes())
            from sumcp import sufile
            geom = sufile.geometry(p)
            run = M._Runner(p, geom, tmp, dx_for_migration)
            mig = run.migrate(p, vint_for_migration(vint, vrms))
        return [M.focus(mig, i0, t0, dt, 0.05, dx, float(np.interp(t0, t, vrms)))
                for i0, t0 in apexes]

    def test_correct_setting_passes(self):
        self.assertTrue(all(f["ok"] for f in self._run(lambda vi, vr: vi, 10.0)))

    def test_rms_given_as_interval_fails(self):
        self.assertFalse(all(f["ok"] for f in self._run(lambda vi, vr: vr, 10.0)))

    def test_doubled_trace_spacing_fails(self):
        self.assertFalse(all(f["ok"] for f in self._run(lambda vi, vr: vi, 20.0)))


class Gating(unittest.TestCase):
    def test_sumigps_is_trusted_not_allowed(self):
        self.assertIn("sumigps", config.TRUSTED_SU_COMMANDS)
        self.assertNotIn("sumigps", config.ALLOWED_SU_COMMANDS)

    def test_capability_is_declared(self):
        self.assertIn("migration.completed", evidence.CAPABILITIES)

    def test_tool_is_exposed(self):
        from sumcp import tools
        self.assertIn("migrate_stack", tools.__all__)
        server = (REPO / "server.py").read_text(encoding="utf-8")
        self.assertIn("def migrate_stack(", server)

    def test_unknown_method_is_refused(self):
        with self.assertRaises(ValueError):
            M.migrate_stack("anything", method="kirchhoff")


if __name__ == "__main__":
    unittest.main()


class Aperture(unittest.TestCase):
    """v0.25 M5."""

    def test_long_line_short_record_is_not_edge_dominated(self):
        t = np.arange(0, 2.6, 0.002)
        v = np.full(t.size, 1800.0)
        e = M.edge_fraction(596, 10.0, t, v, 1.4)
        self.assertLess(e["fraction"], M.EDGE_FRACTION_MAX)

    def test_short_line_long_record_is(self):
        t = np.arange(0, 6.0, 0.004)
        v = np.full(t.size, 2200.0)
        e = M.edge_fraction(200, 12.5, t, v, 2.17)
        self.assertGreater(e["fraction"], 0.95)

    def test_fraction_grows_as_the_line_shrinks(self):
        t = np.arange(0, 2.6, 0.002)
        v = np.full(t.size, 2000.0)
        fs = [M.edge_fraction(n, 10.0, t, v, 1.4)["fraction"] for n in (600, 400, 200)]
        self.assertTrue(fs[0] < fs[1] < fs[2])
