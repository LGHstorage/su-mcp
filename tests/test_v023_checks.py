"""v0.23 checks: N2 quality warning, T2 tiers, L1 log retry."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SU_MCP_LOG_DIR", tempfile.mkdtemp(prefix="su-mcp-test-log-"))

from sumcp import provenance                                     # noqa: E402
from sumcp import stack as S                                     # noqa: E402

FEAS = {"status": "INCONCLUSIVE"}
MEASURED = {"level": "MEASURED", "measured_fraction": 0.79}


def snr(ceiling):
    return {"level": "CLEAR" if ceiling >= 0.9 else "NOISE_LIMITED",
            "correlation_ceiling": ceiling}


class N2(unittest.TestCase):
    def test_v022_released_stacks(self):
        # (ceiling, E2, feasibility) of released v0.22 stacks and the tier v0.23 gives them
        cases = [((0.912, 0.58, None), "WARN"),      # band noise 1.6x, the v0.22 C
                 ((0.897, 0.74, FEAS), "WARN"),      # white 1.7x
                 ((0.916, 0.77, FEAS), "WARN"),      # white 1.5x
                 ((0.944, 0.76, FEAS), "WARN"),      # white 1.2x (good: a false alarm)
                 ((0.960, 0.63, None), "OK"),        # band 1.0x
                 ((0.999, 0.80, FEAS), "CAUTION"),   # statics 18 ms, G1
                 ((0.999, 0.81, None), "OK")]        # v2
        for (c, f, feas), tier in cases:
            got = S.reliability_warning(snr(c), {"level": "MEASURED", "measured_fraction": f}, feas)
            self.assertEqual(got["level"], tier, (c, f, feas, got))

    def test_w3_still_warns(self):
        got = S.reliability_warning(snr(0.99), {"level": "PARTIAL", "measured_fraction": 0.2})
        self.assertEqual(got["level"], "WARN")
        self.assertIn("E2", got["quality_reasons"][0])

    def test_tiers_are_reported_apart(self):
        got = S.reliability_warning(snr(0.93), MEASURED, FEAS)
        self.assertEqual(got["level"], "WARN")
        self.assertEqual(len(got["quality_reasons"]), 1)
        self.assertEqual(len(got["provenance_reasons"]), 1)
        self.assertEqual(got["reasons"], got["quality_reasons"] + got["provenance_reasons"])

    def test_unknown_ceiling_does_not_warn_by_itself(self):
        self.assertEqual(S.reliability_warning({"status": "UNKNOWN"}, MEASURED)["level"], "OK")


class LogRetry(unittest.TestCase):
    def test_transient_permission_error_is_waited_out(self):
        real_open = open
        calls = {"n": 0}

        def flaky(path, *a, **k):
            if str(path).endswith("processing.jsonl") and calls["n"] < 2:
                calls["n"] += 1
                raise PermissionError(13, "locked")
            return real_open(path, *a, **k)
        with mock.patch("builtins.open", flaky), mock.patch("time.sleep"):
            provenance.record({"kind": "test"})
        self.assertEqual(calls["n"], 2)

    def test_persistent_permission_error_still_raises(self):
        def locked(path, *a, **k):
            raise PermissionError(13, "locked")
        with mock.patch("builtins.open", locked), mock.patch("time.sleep"):
            with self.assertRaises(PermissionError):
                provenance.record({"kind": "test"})


if __name__ == "__main__":
    unittest.main()
