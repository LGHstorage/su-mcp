"""v0.28 checks: depth axis, conversion, Z1 depth impulse gate, Z2, Z4, gating."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import config, evidence, runner, sufile                # noqa: E402
from sumcp import depth as Z                                      # noqa: E402
from sumcp import migrate as M                                    # noqa: E402

HAVE_SU = runner.find_program("sumigpspi") is not None


class Axis(unittest.TestCase):
    def test_constant_velocity_depth(self):
        z = Z.depth_axis(np.full(501, 2000.0), 0.002)
        self.assertAlmostEqual(z[500], 1000.0)          # 1.0 s two-way at 2000 m/s

    def test_conversion_moves_an_event_to_its_depth(self):
        dt, ns = 0.002, 1001
        t = np.arange(ns) * dt
        tr = np.exp(-((t - 1.0) / 0.01) ** 2)
        z = Z.depth_axis(np.full(ns, 3000.0), dt)
        zg = np.arange(0, 1600, 5.0)
        out = Z.convert_trace(tr, z, zg)
        self.assertAlmostEqual(zg[np.argmax(out)], 1500.0, delta=5.0)

    def test_below_the_record_is_zero(self):
        z = Z.depth_axis(np.full(11, 2000.0), 0.01)
        out = Z.convert_trace(np.ones(11), z, np.array([0.0, 50.0, 500.0]))
        self.assertEqual(out[-1], 0.0)


class Interval(unittest.TestCase):
    def test_z2_flags_a_blown_up_dix(self):
        t = np.arange(0, 2.0, 0.002)
        good = np.full(t.size, 2500.0)
        bad = good.copy(); bad[800] = 9000.0
        r = Z.interval_check([1, 2], [good, bad], {1: 1.9, 2: 1.9}, t, 0.5)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["violations"][0]["cdp"], 2)
        r = Z.interval_check([1, 2], [good, bad], {1: 1.9, 2: 1.0}, t, 0.5)   # outside support
        self.assertEqual(r["verdict"], "PASS")

    def test_z4_reads_the_conditioning_history(self):
        self.assertFalse(Z.dmo_accepted({}))
        self.assertFalse(Z.dmo_accepted({"conditioning": [{"accepted": False, "operations": [{"op": "dmo"}]}]}))
        self.assertTrue(Z.dmo_accepted({"conditioning": [{"accepted": True, "operations": [{"op": "dmo"}]}]}))


class Inheritance(unittest.TestCase):
    def test_depth_products_carry_m5(self):
        src = (REPO / "sumcp" / "depth.py").read_text(encoding="utf-8")
        self.assertIn("M.edge_fraction(", src)
        self.assertIn("stack reliability + M5 + Z4", src)


class Gating(unittest.TestCase):
    def test_programs_and_capability(self):
        self.assertIn("sumigpspi", config.TRUSTED_SU_COMMANDS)
        self.assertNotIn("sumigpspi", config.ALLOWED_SU_COMMANDS)
        self.assertIn("depth.completed", evidence.CAPABILITIES)
        for m in Z.DEPTH_METHODS:
            self.assertIn(m, M.METHODS)
        self.assertEqual(M.DEFAULT_METHOD, "phase_shift_smooth")


@unittest.skipUnless(HAVE_SU, "SU sumigpspi not installed")
class DepthImpulseGate(unittest.TestCase):
    """Z1 must pass the right velocity, trace spacing and depth step and fail the usual mistakes."""

    def _run(self, vint_for_mig, dx_mig, dz_mig=Z.DZ_M):
        ns, dt, ntr, dx = 751, 0.002, 240, 10.0
        t = np.arange(ns) * dt
        vint = 1500 + 1500 * t / 1.5
        vrms = np.sqrt(np.cumsum(vint ** 2) / np.arange(1, ns + 1))
        apexes = [(60, 0.45), (120, 0.75), (180, 1.05)]
        imp = M.impulse_section(ntr, ns, dt, dx, 20.0, apexes, lambda i, t0: float(np.interp(t0, t, vrms)))
        hdr = np.zeros((ntr, 60), dtype="<i4"); h16 = hdr.view("<i2")
        hdr[:, 0] = np.arange(1, ntr + 1); hdr[:, 5] = np.arange(1000, 1000 + ntr)
        h16[:, 57] = ns; h16[:, 58] = int(dt * 1e6)
        z = Z.depth_axis(vint, dt)
        nz = int(z[-1] / Z.DZ_M) + 1
        zg = np.arange(nz) * Z.DZ_M
        vm = vint_for_mig(vint, vrms)
        vz = np.interp(zg, Z.depth_axis(vm, dt), vm)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = tmp / "imp.su"
            p.write_bytes(np.concatenate([hdr.view("u1"), imp.astype("<f4").view("u1")], axis=1).tobytes())
            img = Z._pspi(tmp, p, np.repeat(vz[:, None], ntr, axis=1), nz, dz_mig, dx_mig, "t")
        out = []
        for i0, t0 in apexes:
            v0 = float(np.interp(t0, t, vint))
            out.append(Z.focus_depth(img, i0, float(np.interp(t0, t, z)), Z.DZ_M, v0 * 0.05 / 2, dx, v0))
        return out

    def test_correct_setting_passes(self):
        self.assertTrue(all(f["ok"] for f in self._run(lambda vi, vr: vi, 10.0)))

    def test_rms_given_as_interval_fails(self):
        self.assertFalse(all(f["ok"] for f in self._run(lambda vi, vr: vr, 10.0)))

    def test_doubled_trace_spacing_fails(self):
        self.assertFalse(all(f["ok"] for f in self._run(lambda vi, vr: vi, 20.0)))

    def test_wrong_depth_step_fails(self):
        self.assertFalse(all(f["ok"] for f in self._run(lambda vi, vr: vi, 10.0, dz_mig=2 * Z.DZ_M)))


if __name__ == "__main__":
    unittest.main()
