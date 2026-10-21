"""The canonical processing offset, and the circle it must not close."""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("SU_MCP_LOG_DIR",
                      tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import geometry, sufile   # noqa: E402

NS = 8


def write_su(path: Path, *, sx, gx, offset, counit=1, scalco=1,
             cdp=None, fldr=None, tracf=None) -> Path:
    """A minimal big-endian SU file, enough for the coordinate code to read."""
    n = len(sx)
    cdp = np.arange(1, n + 1) if cdp is None else np.asarray(cdp)
    fldr = np.ones(n, dtype=int) if fldr is None else np.asarray(fldr)
    tracf = np.arange(1, n + 1) if tracf is None else np.asarray(tracf)
    words = {"tracl": np.arange(1, n + 1), "fldr": fldr, "tracf": tracf,
             "cdp": cdp, "offset": np.asarray(offset),
             "sx": np.asarray(sx), "sy": np.zeros(n, dtype=int),
             "gx": np.asarray(gx), "gy": np.zeros(n, dtype=int),
             "scalco": np.full(n, scalco), "scalel": np.ones(n, dtype=int),
             "counit": np.full(n, counit), "ns": np.full(n, NS),
             "dt": np.full(n, 4000), "trid": np.ones(n, dtype=int)}
    samples = np.zeros((n, NS), dtype=">f4")
    with open(path, "wb") as f:
        for i in range(n):
            head = bytearray(240)
            for key, values in words.items():
                off, code = sufile.KEY_FORMATS[key]
                head[off:off + struct.calcsize(code)] = struct.pack(
                    ">" + code, int(values[i]))
            f.write(bytes(head))
            f.write(samples[i].tobytes())
    return path


class AngularPlausibilityTest(unittest.TestCase):
    """Could these numbers be the angular unit the header claims?"""

    def test_metres_cannot_be_decimal_degrees(self):
        scaled = {"sx": np.array([14237.0, 18212.0]), "sy": np.zeros(2),
                  "gx": np.array([12500.0, 16450.0]), "gy": np.zeros(2)}
        out = geometry._angular_plausibility(scaled, [3])
        self.assertTrue(out["impossible_as_angles"])
        self.assertEqual(out["limit"], 180.0)

    def test_real_degrees_are_left_alone(self):
        scaled = {"sx": np.array([-77.65, -75.23]), "sy": np.array([33.88, 32.34]),
                  "gx": np.array([-77.66, -75.24]), "gy": np.array([33.88, 32.34])}
        out = geometry._angular_plausibility(scaled, [3])
        self.assertFalse(out["impossible_as_angles"])

    def test_a_length_unit_has_no_angular_limit(self):
        scaled = {k: np.array([1.0, 2.0]) for k in ("sx", "sy", "gx", "gy")}
        out = geometry._angular_plausibility(scaled, [1])
        self.assertFalse(out["unit_is_angular"])
        self.assertFalse(out["impossible_as_angles"])


class NoCircularityTest(unittest.TestCase):
    """The units decision must not depend on the offset header."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.sx = np.full(60, 14000) + (np.arange(60) // 10) * 25
        # Offsets must vary, or the corroboration figure is never computed and the test would pass for the wrong
        # reason.
        self.gx = self.sx - (300 + 25 * (np.arange(60) % 10))
        self.true_offset = self.gx - self.sx
        self.addCleanup(self.tmp.cleanup)

    def _units(self, offset, counit):
        path = write_su(self.dir / f"c{counit}_{abs(int(offset[0]))}.su",
                        sx=self.sx, gx=self.gx, offset=offset, counit=counit)
        resolved = geometry.resolve_coordinates(path, sufile.geometry(path))
        return resolved

    def test_units_survive_a_corrupted_offset_header(self):
        honest = self._units(self.true_offset, 3)
        corrupt = self._units(self.true_offset * 2, 3)
        self.assertTrue(honest["units_are_lengths"])
        self.assertEqual(honest["units_are_lengths"], corrupt["units_are_lengths"],
                         "doubling the offset header changed the units decision; "
                         "the decision is still reading the offset header")

    def test_the_offset_agreement_is_reported_as_corroboration_only(self):
        corrupt = self._units(self.true_offset * 2, 3)
        ev = corrupt["unit_evidence"]
        self.assertIn("coordinate magnitudes", ev["decided_by"])
        self.assertFalse(ev["offset_header_corroborates"])
        self.assertIn("does not use it", ev["corroboration_role"])


class ThreeWayTest(unittest.TestCase):
    """Use the header, use the coordinates, or refuse."""

    TRUSTED = {"trustworthy": True, "checks": {}, "failed": [],
               "reason": "The coordinates stand on their own."}
    UNTRUSTED = {"trustworthy": False, "checks": {}, "failed": ["units_resolved"],
                 "reason": "The coordinates cannot be used."}

    @staticmethod
    def offsets(agrees, relative=0.0, state="varying"):
        return {"header_state": state, "agrees": agrees,
                "difference": {"relative_median": relative}}

    def test_header_agrees_so_the_header_is_used(self):
        out = geometry.processing_offset(self.offsets(True, 0.0), self.TRUSTED)
        self.assertTrue(out["resolved"])
        self.assertEqual(out["origin"], geometry.OFFSET_FROM_HEADER)
        self.assertFalse(out["repair_required"])

    def test_header_wrong_but_coordinates_trusted_so_repair(self):
        out = geometry.processing_offset(self.offsets(False, 1.0), self.TRUSTED)
        self.assertTrue(out["resolved"])
        self.assertEqual(out["origin"], geometry.OFFSET_FROM_COORDINATES)
        self.assertTrue(out["repair_required"])

    def test_header_wrong_and_coordinates_untrusted_so_refuse(self):
        out = geometry.processing_offset(self.offsets(False, 1.0), self.UNTRUSTED)
        self.assertFalse(out["resolved"])
        self.assertIsNone(out["origin"])
        self.assertFalse(out["repair_required"])

    def test_an_empty_offset_header_is_repaired_not_refused(self):
        """A zeroed offset is missing information, not contradictory."""
        out = geometry.processing_offset(self.offsets(None, state="zero"),
                                         self.TRUSTED)
        self.assertTrue(out["resolved"])
        self.assertEqual(out["origin"], geometry.OFFSET_FROM_COORDINATES)

    def test_an_empty_offset_header_with_no_coordinates_is_refused(self):
        """Line 32: no offsets and no coordinates. There is nothing to use."""
        out = geometry.processing_offset(self.offsets(None, state="zero"),
                                         self.UNTRUSTED)
        self.assertFalse(out["resolved"])


class AuthorityTest(unittest.TestCase):
    """Coordinate trust is decided on its own evidence."""

    @staticmethod
    def resolved(units=True, n_sx=60, n_gx=60, scalco=(1,)):
        return {"units_are_lengths": units, "scalco_values": list(scalco),
                "source": {"sx": {"n_unique": n_sx}},
                "receiver": {"gx": {"n_unique": n_gx}}}

    CLASSIFIED = {"kind": geometry.ACQ_MOVING_RECEIVERS, "status": "ESTABLISHED"}

    def test_a_good_survey_earns_authority(self):
        out = geometry.coordinate_offset_authority(
            self.resolved(), {"receiver_extent_m": 3950.0}, self.CLASSIFIED)
        self.assertTrue(out["trustworthy"], out["failed"])
        self.assertEqual(out["independent_of"], "the offset header")

    def test_unresolved_units_lose_it(self):
        out = geometry.coordinate_offset_authority(
            self.resolved(units=False), {"receiver_extent_m": 3950.0},
            self.CLASSIFIED)
        self.assertFalse(out["trustworthy"])
        self.assertIn("units_resolved_as_lengths", out["failed"])

    def test_constant_coordinates_lose_it(self):
        out = geometry.coordinate_offset_authority(
            self.resolved(n_gx=1), {"receiver_extent_m": 0.0}, self.CLASSIFIED)
        self.assertFalse(out["trustworthy"])
        self.assertIn("receiver_coordinates_vary", out["failed"])

    def test_an_uninterpretable_scalco_loses_it(self):
        out = geometry.coordinate_offset_authority(
            self.resolved(scalco=(7,)), {"receiver_extent_m": 3950.0},
            self.CLASSIFIED)
        self.assertFalse(out["trustworthy"])
        self.assertIn("scalco_interpretable", out["failed"])


class PrerequisiteTest(unittest.TestCase):
    def test_the_offset_gate_is_on_the_stack_track(self):
        from sumcp import cmp
        self.assertIn("geometry.processing_offset_resolved",
                      cmp.STACK_TRACK_PREREQUISITES)

    def test_the_diagnosis_alone_is_not_the_gate(self):
        """offset_header_consistent FAILs on a file that may still be processed."""
        from sumcp import cmp
        self.assertNotIn("geometry.offset_header_consistent",
                         cmp.STACK_TRACK_PREREQUISITES)


if __name__ == "__main__":
    unittest.main()
