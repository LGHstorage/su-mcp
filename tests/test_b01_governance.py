"""baseline01 C0: the governance switch (sumcp/governance.py)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(code, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("SU_MCP_")}
    e["SU_MCP_LOG_DIR"] = tempfile.mkdtemp(prefix="su-mcp-test-log-")
    e.update(env)
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=e, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def off_env(tmp):
    return {"SU_MCP_GOVERNANCE": "off", "SU_MCP_EVAL_DEPLOYMENT": "baseline01",
            "SU_MCP_RUNTIME": str(Path(tmp) / "rt"), "SU_MCP_STATE": str(Path(tmp) / "st")}


class Switch(unittest.TestCase):
    def test_production_default_is_on(self):
        rc, out, err = run("from sumcp import governance as g; print(g.off())")
        self.assertEqual((rc, out.strip()), (0, "False"), err)

    def test_off_refused_outside_evaluation(self):
        rc, out, err = run("import sumcp.governance", SU_MCP_GOVERNANCE="off")
        self.assertNotEqual(rc, 0)
        self.assertIn("GovernanceConfigError", err)
        rc, out, err = run("import sumcp.governance", SU_MCP_GOVERNANCE="off", SU_MCP_EVAL_DEPLOYMENT="baseline01")
        self.assertNotEqual(rc, 0)

    def test_off_in_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run("from sumcp import governance as g, config; print(g.off(), config.STATE_DIR)",
                               **off_env(tmp))
        self.assertEqual(rc, 0, err)
        self.assertTrue(out.startswith("True"))
        self.assertIn("st", out)


REQ = """
from sumcp import evidence as E
m = {"dataset_id": "x", "capabilities": {"geometry.fold_valid": {"status": "FAIL"},
     "velocity.validated": {"status": "FAIL"}, "dataset.imported": {"status": "PASS"}},
     "artifacts": {"cmp_sorted": {"path": "a"}, "velocity_model": {"path": "b"}}}
E.require(m, ["geometry.cmp_assigned", "geometry.fold_valid", "velocity.model_available", "velocity.validated",
              "dataset.imported"], "NMO")
print("passed")
try:
    E.require(m, ["nmo.applied"], "Stacking")
    print("no refusal")
except E.PrerequisiteError as exc:
    print("refused", "nmo.applied" in str(exc))
"""


class Requirements(unittest.TestCase):
    def test_mechanical_only_when_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run(REQ, **off_env(tmp))
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.split(), ["passed", "refused", "True"])

    def test_evidence_kept_when_on(self):
        rc, out, err = run(REQ)
        self.assertNotEqual(rc, 0)
        self.assertIn("velocity.validated", err)


SCRUB = """
import json
from sumcp import governance as g
r = {"ok": True, "run_id": "r", "dataset_id": "x", "model": "m.json",
     "locations": [{"cdp": 5, "valid": False, "problems": ["p"], "median_semblance": 0.1,
                    "function": [{"t0_s": 0.1, "v_m_s": 1500.0, "semblance": 0.2}]}],
     "capabilities": {"velocity.validated": "FAIL"}, "location_grade": {"ok": False}, "notes": ["n"]}
print(json.dumps(g.scrub("pick_velocity", r), sort_keys=True))
s = {"ok": True, "output": "s.su", "reliability": {"level": "WARN"}, "signal_to_noise": {}, "velocity_support": {}}
print(json.dumps(g.scrub("stack_cmp", s), sort_keys=True))
print(json.dumps(g.scrub("su_inspect", {"ok": True, "anything": 1}), sort_keys=True))
m = {"ok": True, "verdict": "PASS", "significance_level": 0.02, "candidates": [{"t0_s": 1.2, "velocity_m_s": 2000,
     "agreed": True, "class": "OBSERVED"}], "notes": ["x"], "slope_ms_per_channel": 8.0}
print(json.dumps(g.scrub("assess_reflection_feasibility", m), sort_keys=True))
"""


class Reporting(unittest.TestCase):
    def test_scrub_when_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run(SCRUB, **off_env(tmp))
        self.assertEqual(rc, 0, err)
        pick, stk, insp, meas = (json.loads(l) for l in out.strip().splitlines())
        self.assertEqual(pick["locations"],
                         [{"cdp": 5, "function": [{"t0_s": 0.1, "v_m_s": 1500.0, "semblance": 0.2}]}])
        self.assertEqual(meas["measurements"], {"candidates": [{"t0_s": 1.2, "velocity_m_s": 2000}],
                                                "slope_ms_per_channel": 8.0})
        for k in ("capabilities", "location_grade", "notes"):
            self.assertNotIn(k, pick)
        self.assertEqual(set(stk) - {"governance"}, {"ok", "output"})
        self.assertEqual(insp, {"ok": True, "anything": 1})

    def test_no_scrub_when_on(self):
        rc, out, err = run(SCRUB)
        self.assertEqual(rc, 0, err)
        pick = json.loads(out.splitlines()[0])
        self.assertIn("capabilities", pick)


if __name__ == "__main__":
    unittest.main()
