"""Standard SPS/RPS/XPS external acquisition geometry (v0.13.0)."""

from __future__ import annotations

import hashlib
import importlib
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

NS, DT_US = 32, 4000
SHOTS, CHANNELS = 5, 6
FIRST_RECORD, FIRST_SOURCE, FIRST_STATION = 40, 100, 200
SOURCE_STEP, STATION_STEP_M, SOURCE_X0, STATION_X0 = 2, 25.0, 5000.0, 4000.0

# SU header word offsets used by the fixture writer (SEG-Y trace-header bytes minus one).
WORDS = {"tracl": (0, "i"), "fldr": (8, "i"), "tracf": (12, "i"),
         "cdp": (20, "i"), "trid": (28, "h"), "offset": (36, "i"),
         "sx": (72, "i"), "sy": (76, "i"), "gx": (80, "i"), "gy": (84, "i"),
         "scalco": (70, "h"), "counit": (88, "h"),
         "ns": (114, "h"), "dt": (116, "h")}


def _su_file(path, headers, ns=NS):
    """Write a minimal big-endian-free (native little) SU file."""
    ntr = len(headers)
    rng = np.random.default_rng(7)
    with open(path, "wb") as out:
        for i in range(ntr):
            head = bytearray(240)
            values = {"ns": ns, "dt": DT_US, **headers[i]}
            for key, value in values.items():
                off, code = WORDS[key]
                struct.pack_into("<" + code, head, off, int(value))
            out.write(bytes(head))
            out.write(rng.standard_normal(ns).astype("<f4").tobytes())
    return path


def _plain_headers(with_geometry=False, shift_m=0.0):
    """SHOTS x CHANNELS traces, plus one auxiliary trace per record."""
    rows, tracl = [], 0
    for s in range(SHOTS):
        record = FIRST_RECORD + s
        rows.append({"tracl": (tracl := tracl + 1), "fldr": record,
                     "tracf": -1, "trid": 0})
        for c in range(1, CHANNELS + 1):
            row = {"tracl": (tracl := tracl + 1), "fldr": record,
                   "tracf": c, "trid": 1}
            if with_geometry:
                sx = SOURCE_X0 + s * SOURCE_STEP * STATION_STEP_M + shift_m
                gx = STATION_X0 + (s + c - 1) * STATION_STEP_M
                row.update(sx=int(sx), sy=0, gx=int(gx), gy=0,
                           scalco=1, counit=1, offset=int(gx - sx))
            rows.append(row)
    return rows


def _sps_text(kind, rows, spec):
    head = ["H26 DEFINITION OF FIELD            COLS       FORMAT       UNIT"]
    for name, lo, hi in spec:
        head.append(f"H26 {name:<28}{lo:>3}-{hi:>3}           A1       none")
    return "\n".join(head + rows) + "\n"


SR_SPEC = [("Record identification", 1, 1), ("Line name", 2, 17),
           ("Point number", 18, 25), ("Map grid easting", 26, 35),
           ("Map grid northing", 36, 45), ("Surface elevation", 46, 51)]
X_SPEC = [("Record identification", 1, 1), ("Field record number", 2, 9),
          ("Line name", 10, 25), ("Point number", 26, 33),
          ("From channel", 34, 38), ("To channel", 39, 43),
          ("Channel increment", 44, 44), ("Line name", 45, 60),
          ("From receiver", 61, 68), ("To receiver", 69, 76)]
LINE = "L1"


def _s_row(point, x):
    return f"S{LINE:<16}{point:>8}{x:>10.1f}{0.0:>10.1f}{0.0:>6.1f}"


def _r_row(point, x):
    return f"R{LINE:<16}{point:>8}{x:>10.1f}{0.0:>10.1f}{0.0:>6.1f}"


def _x_row(record, point, c1, c2, r1, r2, step=1):
    return (f"X{record:>8}{LINE:<16}{point:>8}{c1:>5}{c2:>5}{step:>1}"
            f"{LINE:<16}{r1:>8}{r2:>8}")


def _default_set(tmp, tag="fixture", *, drop_source=None, drop_receiver=None,
                 duplicate_record=None, bad_range=False, shift_m=0.0):
    sources = [(FIRST_SOURCE + s * SOURCE_STEP,
                SOURCE_X0 + s * SOURCE_STEP * STATION_STEP_M + shift_m)
               for s in range(SHOTS)]
    stations = [(FIRST_STATION + k, STATION_X0 + k * STATION_STEP_M)
                for k in range(SHOTS + CHANNELS)]
    s_rows = [_s_row(p, x) for p, x in sources if p != drop_source]
    r_rows = [_r_row(p, x) for p, x in stations if p != drop_receiver]
    x_rows = []
    for s in range(SHOTS):
        last = CHANNELS + (1 if bad_range and s == 0 else 0)
        x_rows.append(_x_row(FIRST_RECORD + s, FIRST_SOURCE + s * SOURCE_STEP,
                             1, CHANNELS, FIRST_STATION + s,
                             FIRST_STATION + s + last - 1))
    if duplicate_record is not None:
        x_rows.append(_x_row(duplicate_record, FIRST_SOURCE, 1, CHANNELS,
                             FIRST_STATION, FIRST_STATION + CHANNELS - 1))
    paths = {}
    for kind, rows, spec in (("SPS", s_rows, SR_SPEC), ("RPS", r_rows, SR_SPEC),
                             ("XPS", x_rows, X_SPEC)):
        p = Path(tmp) / "raw" / f"{tag}.{kind}"
        p.write_text(_sps_text(kind, rows, spec))
        paths[kind] = p
    return paths


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ExternalGeometryTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("raw", "work", "results", "qc", "logs", "state"):
            (cls.root / name).mkdir()
        os.environ["SU_MCP_ROOT"] = str(cls.root)
        import sumcp
        from sumcp import (analysis, config, evidence, external, geometry,
                           ingest, paths, provenance, sps, sufile, suenv, tools)
        for module in (config, paths, provenance, suenv, sufile, evidence,
                       geometry, external, sps, ingest, analysis, tools, sumcp):
            importlib.reload(module)
        from sumcp import (analysis, evidence, external, ingest,  # noqa: F811
                           sps, sufile, tools)
        cls.analysis, cls.evidence, cls.external = analysis, evidence, external
        cls.ingest, cls.sps, cls.sufile, cls.tools = ingest, sps, sufile, tools

    def _dataset(self, name, *, with_geometry=False, shift_m=0.0):
        path = self.root / "raw" / f"{name}.su"
        _su_file(path, _plain_headers(with_geometry, shift_m))
        self.ingest.register_su(name, str(path), "fixture")
        return path

    def _assign(self, name, paths, **kw):
        return self.analysis.assign_external_geometry(
            name, str(paths["SPS"]), str(paths["RPS"]), str(paths["XPS"]), **kw)

    # ---------------------------------------------------------------- 1 ----
    def test_valid_set_assigns_exactly(self):
        paths = _default_set(self.root, "t1")
        src = self._dataset("t1")
        got = self._assign("t1", paths)
        self.assertTrue(got["assigned"], got.get("problems"))
        self.assertEqual(got["verdict"]["verdict"], "ACCEPTED")
        self.assertEqual(got["counts"]["placed"], SHOTS * CHANNELS)
        self.assertEqual(got["counts"]["excluded_non_data"], SHOTS)
        self.assertEqual(got["counts"]["unplaced_data_traces"], 0)
        self.assertEqual(got["layouts"]["X"]["source"], "declared")

        copy = self.root / "work" / "t1" / "t1_geom.su"
        geom = self.sufile.geometry(copy)
        self.assertEqual(geom["ntr"], SHOTS * CHANNELS)
        cols = self.sufile.read_header_columns(
            copy, ["sx", "gx", "offset", "scalco", "fldr", "tracf"], geom)
        scale = abs(int(cols["scalco"][0])) or 1
        # every trace's source and receiver are the ones the relation names
        for i in range(geom["ntr"]):
            s = int(cols["fldr"][i]) - FIRST_RECORD
            c = int(cols["tracf"][i])
            self.assertAlmostEqual(
                cols["sx"][i] / scale,
                SOURCE_X0 + s * SOURCE_STEP * STATION_STEP_M, places=3)
            self.assertAlmostEqual(
                cols["gx"][i] / scale,
                STATION_X0 + (s + c - 1) * STATION_STEP_M, places=3)
            self.assertAlmostEqual(
                abs(float(cols["offset"][i])),
                abs(cols["gx"][i] / scale - cols["sx"][i] / scale), delta=1.0)

    # ---------------------------------------------------------------- 2 ----
    def test_missing_source_is_refused(self):
        paths = _default_set(self.root, "t2", drop_source=FIRST_SOURCE)
        self._dataset("t2")
        got = self._assign("t2", paths)
        self.assertFalse(got["assigned"])
        self.assertFalse(
            got["checks"]["sources_present_in_S"]["supports_assignment"])
        self.assertEqual(
            self.evidence.capability_status(self.evidence.load("t2"),
                                            "geometry.external_geometry_assigned"),
            self.evidence.FAIL)
        self.assertFalse((self.root / "work" / "t2" / "t2_geom.su").exists())

    # ---------------------------------------------------------------- 3 ----
    def test_missing_receiver_is_refused(self):
        paths = _default_set(self.root, "t3", drop_receiver=FIRST_STATION + 1)
        self._dataset("t3")
        got = self._assign("t3", paths)
        self.assertFalse(got["assigned"])
        self.assertFalse(
            got["checks"]["receivers_present_in_R"]["supports_assignment"])

    # ---------------------------------------------------------------- 4 ----
    def test_duplicate_relation_is_refused(self):
        paths = _default_set(self.root, "t4", duplicate_record=FIRST_RECORD)
        self._dataset("t4")
        got = self._assign("t4", paths)
        self.assertFalse(got["assigned"])
        self.assertFalse(
            got["checks"]["assignment_is_unambiguous"]["supports_assignment"])
        self.assertGreater(
            got["checks"]["assignment_is_unambiguous"]["channels_claimed_twice"], 0)

    # ---------------------------------------------------------------- 5 ----
    def test_channel_range_mismatch_is_refused(self):
        paths = _default_set(self.root, "t5", bad_range=True)
        self._dataset("t5")
        got = self._assign("t5", paths)
        self.assertFalse(got["assigned"])
        self.assertFalse(got["checks"]
                         ["channel_range_matches_receiver_range"]
                         ["supports_assignment"])

    # ---------------------------------------------------------------- 6 ----
    def test_absent_header_geometry_resolves_the_processing_offset(self):
        paths = _default_set(self.root, "t6")
        self._dataset("t6")
        before = self.evidence.load("t6")
        self.assertEqual(
            self.evidence.capability_status(before,
                                            "geometry.processing_offset_resolved"),
            self.evidence.UNKNOWN)
        got = self._assign("t6", paths)
        self.assertTrue(got["assigned"])
        self.assertEqual(got["header_comparison"]["case"],
                         "1_segy_geometry_absent")
        after = self.evidence.load("t6")
        for name in ("geometry.shotpoint_mapping",
                     "geometry.external_geometry_assigned",
                     "geometry.assignment_validated",
                     "geometry.processing_offset_resolved"):
            self.assertEqual(self.evidence.capability_status(after, name),
                             self.evidence.PASS, name)
        canonical = self.evidence.get_capability(
            after, "geometry.processing_offset_resolved")["evidence"]
        self.assertTrue(canonical["resolved"])
        # downstream reads the processing copy, not the imported file
        self.assertTrue(self.evidence.processing_su(after)["path"]
                        .endswith("t6_geom.su"))

    # ---------------------------------------------------------------- 7 ----
    def test_consistent_header_geometry_validates(self):
        paths = _default_set(self.root, "t7")
        self._dataset("t7", with_geometry=True)
        got = self._assign("t7", paths)
        self.assertTrue(got["assigned"], got.get("problems"))
        self.assertEqual(got["header_comparison"]["case"],
                         "2_segy_geometry_present_and_consistent")
        self.assertFalse(got["header_comparison"]["conflict"])

    # ---------------------------------------------------------------- 8 ----
    def test_conflicting_header_geometry_is_refused_not_overwritten(self):
        # the acquisition files put the sources a long way from where the headers put them; neither is declared
        # authoritative here
        paths = _default_set(self.root, "t8", shift_m=5000.0)
        src = self._dataset("t8", with_geometry=True)
        before = _sha(src)
        got = self._assign("t8", paths)
        self.assertFalse(got["assigned"])
        self.assertTrue(got["header_comparison"]["conflict"])
        self.assertEqual(got["header_comparison"]["case"],
                         "3_segy_geometry_present_and_conflicting")
        self.assertFalse((self.root / "work" / "t8" / "t8_geom.su").exists())
        self.assertEqual(_sha(src), before)
        after = self.evidence.load("t8")
        self.assertTrue(self.evidence.processing_su(after)["path"]
                        .endswith("t8.su"))

    # ---------------------------------------------------------------- 9 ----
    def test_the_original_file_is_never_modified(self):
        paths = _default_set(self.root, "t9")
        src = self._dataset("t9")
        before = _sha(src)
        got = self._assign("t9", paths)
        self.assertTrue(got["assigned"])
        self.assertEqual(_sha(src), before)
        self.assertFalse(got["source_file_modified"])
        proof = self.evidence.get_capability(
            self.evidence.load("t9"),
            "geometry.external_geometry_assigned")["evidence"]
        self.assertFalse(proof["source_file_modified"])
        self.assertTrue(proof["source_file_sha256_unchanged"])

    # --------------------------------------------------- parser generality --
    def test_layout_comes_from_the_file_not_from_the_code(self):
        """The same content in different columns must read the same."""
        wide_sr = [("Record identification", 1, 1), ("Line name", 2, 9),
                   ("Point number", 10, 19), ("Map grid easting", 20, 32),
                   ("Map grid northing", 33, 45), ("Surface elevation", 46, 55)]
        rows = [f"R{'L1':<8}{FIRST_STATION:>10}{1234.5:>13.1f}"
                f"{6789.0:>13.1f}{0.0:>10.1f}"]
        p = self.root / "raw" / "wide.RPS"
        p.write_text(_sps_text("RPS", rows, wide_sr))
        read = self.sps.read_file(p)
        self.assertEqual(read["layout"]["source"], "declared")
        self.assertEqual(read["record_type"], "R")
        row = read["records"][0]
        self.assertEqual(int(row["point"]), FIRST_STATION)
        self.assertAlmostEqual(float(row["x"]), 1234.5)
        self.assertAlmostEqual(float(row["y"]), 6789.0)

    def test_a_file_that_declares_nothing_falls_back_and_says_so(self):
        p = self.root / "raw" / "bare.RPS"
        p.write_text("R" + " " * 16 + f"{FIRST_STATION:>8}" + " " * 20
                     + f"{1000.0:>9.1f}{2000.0:>10.1f}\n")
        read = self.sps.read_file(p)
        self.assertEqual(read["layout"]["source"], "fallback")
        self.assertEqual(int(read["records"][0]["point"]), FIRST_STATION)

    def test_a_mixed_file_is_rejected(self):
        p = self.root / "raw" / "mixed.SPS"
        p.write_text(_sps_text("SPS", [_s_row(1, 0.0), _r_row(2, 0.0)], SR_SPEC))
        with self.assertRaises(self.sps.SPSError):
            self.sps.read_file(p)


if __name__ == "__main__":
    unittest.main()
