"""Baseline study 02 (rule 3 of study 01's LOG Addendum 2): audit archived subagent transcripts for isolation
breaches."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TDIR = ROOT / "results/baseline02/transcripts"
RUN_RE = re.compile(r"b0[12]-(?:[0-9a-f]{4}|dry-dev[12])-(?:b|c0|c)-r[12](?:-x\d)?")
CASE_RE = re.compile(r"case_(?:[0-9a-f]{4}|dev[12])")
HIDDEN_RE = re.compile(r"results/baseline0[12]|dev/baseline0[12]|Marm2_v2|_b0[12]_hold")
LISTING = ("su_list_files", "dataset_list", "list_files")         # names only: recorded
RECORDS = ("su_log", "job_list", "job_status", "job_result", "dataset_manifest", "survey_overview")
SIZE_CASES = ("4133", "8383")


def short(name):
    return name.split("__")[-1]


def events(path):
    calls, out = {}, []
    for line in path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get("type") == "tool_use":
                calls[c.get("id")] = (short(c.get("name", "")), json.dumps(c.get("input"), ensure_ascii=False))
            elif c.get("type") == "tool_result":
                tool, args = calls.get(c.get("tool_use_id"), ("?", ""))
                body = c.get("content")
                text = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
                out.append((tool, args, text))
    return out


def audit(run, path):
    case = run.split("-")[1]
    own_case = f"case_{case}"
    invalid, record = [], []
    for tool, args, text in events(path):
        others = sorted({r for r in RUN_RE.findall(text) if r != run})
        other_cases = sorted({c for c in CASE_RE.findall(args + text) if c != own_case})
        hidden_in_args = HIDDEN_RE.findall(args)
        if tool in LISTING:
            if others or other_cases or HIDDEN_RE.search(text):
                record.append(f"{tool}: listing shows {others[:3] + other_cases[:3]}")
            if case in SIZE_CASES and "Baseline02_challenge" in text and other_cases and "bytes" in text:
                invalid.append(f"(iv) {tool} listed the challenge folder with sizes")
            continue
        if others and tool in RECORDS:
            invalid.append(f"(i) {tool} returned records of {others[:3]}")
        elif others:
            record.append(f"{tool}: output mentions {others[:3]}")
        if other_cases and CASE_RE.search(args):
            invalid.append(f"(ii) {tool} called on {other_cases[:3]}")
        if hidden_in_args:
            invalid.append(f"(iii) {tool} called with {sorted(set(hidden_in_args))}")
    return {"run": run, "invalid": sorted(set(invalid)), "record": sorted(set(record))[:20]}


def main():
    res = []
    for p in sorted(TDIR.glob("b02-*.jsonl")):
        res.append(audit(p.stem, p))
    (TDIR / "audit.json").write_text(json.dumps(res, indent=1))
    for r in res:
        tag = "INVALID " + "; ".join(r["invalid"]) if r["invalid"] else ("RECORD" if r["record"] else "clean")
        print(f"{r['run']:22s} {tag}")
    print(f"{len(res)} transcripts audited")


if __name__ == "__main__":
    main()
