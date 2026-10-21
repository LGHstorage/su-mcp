"""v0.26 checks: the DMO operation (registry, solo, parameters, budgets, flat-event chain)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import config, runner                                  # noqa: E402
from sumcp import conditioning as K                               # noqa: E402
from sumcp import iterate as I                                    # noqa: E402
from sumcp import stack as S                                      # noqa: E402

HAVE_SU = all(runner.find_program(p) for p in ("sudmofk", "sunmo", "susort"))


def _model(v=2000.0, cdps=(10, 50)):
    return {"locations": [{"cdp": c, "function": [{"t0_s": 0.0, "v_m_s": v},
                                                  {"t0_s": 2.0, "v_m_s": v}]} for c in cdps]}


class Registry(unittest.TestCase):
    def test_dmo_is_a_solo_operation_without_parameters(self):
        self.assertIn("dmo", K.REGISTRY)
        self.assertIn("dmo", K.SOLO_OPERATIONS)
        with self.assertRaises(ValueError):
            K.REGISTRY["dmo"]["build"]({"vdmo": 1500}, {})
        self.assertEqual(K.REGISTRY["dmo"]["build"]({}, {}), [("dmo", {}, False)])

    def test_programs_are_trusted_only(self):
        self.assertIn("sudmofk", config.TRUSTED_SU_COMMANDS)
        self.assertNotIn("sudmofk", config.ALLOWED_SU_COMMANDS)
        self.assertIn("susort", config.TRUSTED_SU_COMMANDS)

    def test_budgets(self):
        self.assertEqual(K.MAX_PASSES, 3)
        self.assertEqual(S.MAX_VELOCITY_ANALYSES, 6)
        self.assertGreaterEqual(tuple(int(x) for x in config.VERSION.split(".")), (0, 26, 0))


class Parameters(unittest.TestCase):
    def test_marmousi_v2_geometry(self):
        # 20 m bins would give noffmix 1; v2 uses 10 m bins (cdp step 1) and 40 m shots
        cdp = np.repeat(np.arange(545, 1141), 3)
        sx = np.arange(cdp.size) * 40.0 / 3
        sx = np.round(sx / 40.0) * 40.0
        t = np.arange(0, 2.6, 0.004)
        args, info = I.dmo_parameters(cdp, sx, 10.0, _model(cdps=(637, 1048)), t)
        self.assertEqual(args["noffmix"], 4)
        self.assertEqual(args["dxcdp"], 10.0)
        self.assertEqual((args["cdpmin"], args["cdpmax"]), (545, 1140))
        self.assertEqual(args["tdmo"][:3], [0.0, 0.1, 0.2])
        self.assertTrue(all(v == 2000.0 for v in args["vdmo"]))
        self.assertEqual(info["shot_spacing_m"], 40.0)

    def test_cdp_step_scales_the_spacing(self):
        cdp = np.arange(100, 200, 2)
        args, _ = I.dmo_parameters(cdp, cdp * 12.5, 12.5, _model(cdps=(100, 198)),
                                   np.arange(0, 1.0, 0.004))
        self.assertEqual(args["dxcdp"], 25.0)
        self.assertEqual(args["noffmix"], 2)

    def test_scalco(self):
        self.assertTrue(np.allclose(I._scaled([100, 100, 100], [-10, 10, 0]), [10, 1000, 100]))

    def test_needs_a_validated_velocity(self):
        with self.assertRaises(ValueError):
            I._dmo_check({"capabilities": {}})


def _gathers(path, ncdp=60, nfold=12, dt=0.004, ns=376, bin_m=10.0, v=2000.0, t0s=(0.6, 1.0)):
    """CMP-sorted flat reflections with hyperbolic moveout at every CMP."""
    ntr = ncdp * nfold
    hdr = np.zeros((ntr, 60), dtype="<i4")
    h16 = hdr.view("<i2")
    cdp = np.repeat(np.arange(1, ncdp + 1), nfold)
    off = np.tile(100.0 + 2 * bin_m * 2 * np.arange(nfold), ncdp)
    hdr[:, 0] = np.arange(1, ntr + 1)
    hdr[:, 5] = cdp
    hdr[:, 9] = off.astype(int)
    hdr[:, 18] = (cdp * bin_m - off / 2).astype(int)
    hdr[:, 19] = (cdp * bin_m + off / 2).astype(int)
    h16[:, 35] = 1
    h16[:, 57] = ns
    h16[:, 58] = int(dt * 1e6)
    t = np.arange(ns) * dt
    data = np.zeros((ntr, ns), dtype="<f4")
    for t0 in t0s:
        tx = np.sqrt(t0 ** 2 + (off[:, None] / v) ** 2)
        a = (np.pi * 20.0 * (t[None, :] - tx)) ** 2
        data += ((1 - 2 * a) * np.exp(-a)).astype("<f4")
    path.write_bytes(np.concatenate([hdr.view("u1"), data.view("u1")], axis=1).tobytes())
    return cdp, off


@unittest.skipUnless(HAVE_SU, "SU sudmofk/sunmo/susort not installed")
class FlatEventsThroughTheChain(unittest.TestCase):
    """DMO must leave zero-dip reflections alone and keep the (cdp, offset) order (gate D1)."""

    def test_flat_events_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "g.su"
            cdp, off = _gathers(src)
            model = _model(cdps=(10, 50))
            t = np.arange(376) * 0.004
            args, _ = I.dmo_parameters(cdp, cdp * 10.0 - off / 2, 10.0, model, t)
            I._dmo_chain(src, tmp / "dmo.su", tmp, model, args, "a")
            I._dmo_chain(src, tmp / "ref.su", tmp, model, args, "b", with_dmo=False)
            c0, o0, _ = I._read_all(src)
            c1, o1, out = I._read_all(tmp / "dmo.su")
            _, _, ref = I._read_all(tmp / "ref.su")
        self.assertTrue(np.array_equal(c0, c1) and np.array_equal(o0, o1))
        mid = (c1 > 10) & (c1 < 50)            # away from the line ends
        a, b = out[mid].ravel(), ref[mid].ravel()
        corr = float(a @ b / np.sqrt((a @ a) * (b @ b)))
        self.assertGreater(corr, 0.9)


if __name__ == "__main__":
    unittest.main()
