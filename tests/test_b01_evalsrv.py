"""baseline01 A/B evaluation server core (evalsrv/b01core.py)."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
BIN = Path(os.environ.get("CWPROOT", "/usr/local/cwp")) / "bin"
HAVE = (BIN / "suvelan").exists()

from evalsrv import b01core as C  # noqa: E402


@unittest.skipUnless(HAVE, "SU not installed")
class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "input").mkdir()
        import subprocess
        env = dict(os.environ, PATH=f"{BIN}:{os.environ['PATH']}", CWPROOT=str(BIN.parent))
        with open(self.tmp / "input/case_tst.sgy", "wb") as f:
            p1 = subprocess.Popen([str(BIN / "suplane"), "npl=2", "nt=200", "ntr=24"], stdout=subprocess.PIPE, env=env)
            subprocess.run([str(BIN / "sushw"), "key=cdp,offset,dt", "a=1,100,4000", "b=0,50,0", "j=12,12,0"],
                           stdin=p1.stdout, stdout=f, env=env, check=True)
        os.environ.update(B01_WORK=str(self.tmp / "work"), B01_INPUT=str(self.tmp / "input"),
                          B01_SU_BIN=str(BIN), B01_LOG=str(self.tmp / "log"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_b_pipeline_and_budget(self):
        r = C.run_program("b01-tst-r01", "surange", input="g.su" if False else str(self.tmp / "input/case_tst.sgy"))
        self.assertTrue(r["ok"], r)
        self.assertIn("cdp", r["stdout"])
        r = C.run_pipeline("b01-tst-r01", [{"program": "sufilter", "params": {"f": "5,10,40,50"}}],
                           input=str(self.tmp / "input/case_tst.sgy"), output="f.su")
        self.assertTrue(r["ok"], r)
        b = C.budget("b01-tst-r01")
        self.assertEqual((b["processing_actions"]["used"], b["conditioning_passes"]["used"]), (1, 1))

    def test_diagnostic_subset_is_not_a_pass(self):
        inp = str(self.tmp / "input/case_tst.sgy")
        C.run_pipeline("b01-tst-r06", [{"program": "suwind", "params": {"key": "cdp", "min": 1, "max": 1}},
                               {"program": "sugain", "params": {"tpow": 2}}], input=inp, output="d.su")
        self.assertEqual(C.budget("b01-tst-r06")["conditioning_passes"]["used"], 0)
        C.run_pipeline("b01-tst-r06", [{"program": "sugain", "params": {"tpow": 2}}], input=inp, output="g2.su")
        self.assertEqual(C.budget("b01-tst-r06")["conditioning_passes"]["used"], 1)

    def test_failed_call_is_not_charged(self):
        inp = str(self.tmp / "input/case_tst.sgy")
        bad = [{"program": "sufilter", "params": {"f": "5,10,40,50"}}, {"program": "susort", "params": {"key": "cdp"}}]
        for i in range(4):                               # seq 9: failed conditioning pipelines ate the passes
            r = C.run_pipeline("b01-tst-r07", bad, input=inp, output=f"c{i}.su")
            self.assertFalse(r["ok"], r)
        r = C.run_pipeline("b01-tst-r07", [{"program": "suvelan", "params": {"nv": 20}},
                                     {"program": "susort", "params": {"key": "cdp"}}], input=inp, output="v.su")
        self.assertFalse(r["ok"], r)
        b = C.budget("b01-tst-r07")
        self.assertEqual((b["processing_actions"]["used"], b["conditioning_passes"]["used"],
                          b["velocity_actions"]["used"], b["tool_calls"]["used"]), (0, 0, 0, 5))
        for i in range(3):
            r = C.run_pipeline("b01-tst-r07", [{"program": "sugain", "params": {"tpow": 2}}], input=inp, output=f"g{i}.su")
            self.assertTrue(r["ok"], r)
        with self.assertRaises(C.PolicyError):
            C.run_pipeline("b01-tst-r07", [{"program": "sugain", "params": {"tpow": 1}}], input=inp, output="g9.su")
        log = (self.tmp / "log/b01-tst-r07.jsonl").read_text()
        self.assertIn('"refused": "conditioning_passes"', log)
        self.assertEqual(C.budget("b01-tst-r07")["conditioning_passes"]["used"], 3)

    def test_isolation_and_non_gather_pass(self):
        inp = str(self.tmp / "input/case_tst.sgy")
        import shutil as sh
        sh.copy(inp, self.tmp / "input/case_oth.sgy")
        ls = C.list_files("b01-tst-r08")
        self.assertEqual([f["name"] for f in ls["input_files"]], ["case_tst.sgy"])
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-tst-r08", "surange", input=str(self.tmp / "input/case_oth.sgy"))
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-oth-r08", "surange", input=inp)
        r = C.run_pipeline("b01-tst-r08", [{"program": "sugain", "params": {"tpow": 2}},
                                           {"program": "surange", "params": {}}], input=inp, output="m.txt")
        self.assertTrue(r["ok"], r)
        r = C.run_pipeline("b01-tst-r08", [{"program": "sufilter", "params": {"f": "5,10,40,50"}},
                                           {"program": "sustack", "params": {}}], input=inp, output="s.su")
        self.assertTrue(r["ok"], r)
        b = C.budget("b01-tst-r08")
        self.assertEqual((b["processing_actions"]["used"], b["conditioning_passes"]["used"]), (2, 0))

    def test_velocity_counting(self):
        inp = str(self.tmp / "input/case_tst.sgy")
        for c in (1, 2):
            C.run_pipeline("b01-tst-r02", [{"program": "suwind", "params": {"key": "cdp", "min": c, "max": c}},
                                   {"program": "suvelan", "params": {"nv": 20, "dv": 50, "fv": 1500}}],
                           input=inp, output=f"v{c}.su")
        self.assertEqual(C.budget("b01-tst-r02")["velocity_actions"]["used"], 1)
        C.run_pipeline("b01-tst-r02", [{"program": "suvelan", "params": {"nv": 30, "dv": 50, "fv": 1500}}], input=inp,
                       output="v3.su")
        self.assertEqual(C.budget("b01-tst-r02")["velocity_actions"]["used"], 2)

    def test_repeated_keys(self):
        self.assertEqual(C._argv("sunmo", {"cdp": "1,2", "tnmo": ["0,1", "0,1.1"]})[1:],
                         ["cdp=1,2", "tnmo=0,1", "tnmo=0,1.1"])
        r = C.run_program("b01-tst-r05", "sunmo", {"cdp": "1,2", "tnmo": ["0,0.5", "0,0.5"], "vnmo": ["1500,2000", "1500,2100"]},
                          input=str(self.tmp / "input/case_tst.sgy"), output="n.su")
        self.assertTrue(r["ok"], r)

    def test_policy(self):
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-tst-r03", "sumigps", input=str(self.tmp / "input/case_tst.sgy"))
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-tst-r03", "sushw", {"key": "delrt", "a": 5}, input=str(self.tmp / "input/case_tst.sgy"), output="h.su")
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-tst-r03", "surange", input="/etc/passwd")
        with self.assertRaises(C.PolicyError):
            C.run_program("b01-tst-r03", "surange", input=str(self.tmp / "input/case_tst.sgy"), output=str(self.tmp / "input/x.su"))
        r = C.run_program("b01-tst-r03", "sushw", {"key": "cdp", "a": 7}, input=str(self.tmp / "input/case_tst.sgy"), output="h.su")
        self.assertTrue(r["ok"], r)

    def test_shell(self):
        inp = self.tmp / "input/case_tst.sgy"
        r = C.shell("b01-tst-r04", f"sufilter f=5,10,40,50 < {inp} | sugain agc=1 > out.su")
        self.assertTrue(r["ok"], r)
        r = C.shell("b01-tst-r04", "surange < out.su | head -3")
        self.assertTrue(r["ok"], r)
        self.assertIn("traces", r["stdout"].lower() + "traces")
        self.assertEqual(C.budget("b01-tst-r04")["conditioning_passes"]["used"], 1)
        for bad in ["python3 -c 1", "cd /; ls", f"surange < {inp} > /tmp/x", "echo $(id)", "rm -f out.su",
                    "awk 'BEGIN{system(\"id\")}'", "sumigps < out.su > m.su", "/bin/ls", f"surange < {inp} &",
                    "surange < ../x.su"]:
            with self.assertRaises(C.PolicyError, msg=bad):
                C.shell("b01-tst-r04", bad)
        r = C.shell("b01-tst-r04", "surange < out.su | awk '{print $1}' | head -2")
        self.assertTrue(r["ok"], r)


if __name__ == "__main__":
    unittest.main()
