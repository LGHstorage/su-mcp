# Baseline study 02: run log

One line per run (seq, run, end UTC, subagent tokens, duration, model, notes), plus addenda.

- FROZEN 2026-10-04T05:05:33Z: FREEZE.json sha256 80bd0a39fd4f39fe143c45309a8d7d93747994eca56ec247f02985e4e1d651e4 (194 files). 18 cases, 72 runs, stage 1 = seq 1-36. Block 1 case staged (case_9135).

## Session 1 (orchestrator)

- start (2026-10-04T05:07:41Z): CRITERIA.md read once; hidden/ not read. su-b01-c0 and seismic-unix both appear in ToolSearch. The user asked for four case blocks this session (seq 1-16). sha256 of seq 1-16 task texts checked OK against runs.json. stage_case.py case_9135: staged, sha256 ok. Two runs at a time (positions 1-2, then 3-4). The Agent tool does not report a model name; no override is given (session model claude-opus-5-5).
- seq 1 | b02-9135-c0-r1 | end ≤2026-10-04T05:16:16Z (logged on return; seq 1-2 ran together) | subagent_tokens 117035 | 375926 ms | tool_uses 34 | model not reported | ended normally
- seq 2 | b02-9135-c-r1 | end ≤2026-10-04T05:16:16Z | subagent_tokens 142717 | 476203 ms | tool_uses 35 | model not reported | ended normally
- seq 3 | b02-9135-c-r2 | end ≤2026-10-04T05:26:23Z (logged on return; seq 3-4 ran together) | subagent_tokens 123895 | 212046 ms | tool_uses 22 | model not reported | ended normally
- seq 4 | b02-9135-c0-r2 | end ≤2026-10-04T05:26:23Z | subagent_tokens 144472 | 566595 ms | tool_uses 50 | model not reported | ended normally
- stage_case.py case_035a: staged case_035a.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 5 | b02-035a-c0-r1 | end ≤2026-10-04T05:34:14Z (logged on return; seq 5-6 ran together) | subagent_tokens 116163 | 350391 ms | tool_uses 30 | model not reported | ended normally
- seq 6 | b02-035a-c-r1 | end ≤2026-10-04T05:34:14Z | subagent_tokens 137845 | 432612 ms | tool_uses 33 | model not reported | ended normally
- seq 7 | b02-035a-c0-r2 | end ≤2026-10-04T05:42:17Z (logged on return; seq 7-8 ran together) | subagent_tokens 125110 | 451798 ms | tool_uses 38 | model not reported | ended normally
- seq 8 | b02-035a-c-r2 | end ≤2026-10-04T05:42:17Z | subagent_tokens 143679 | 396089 ms | tool_uses 32 | model not reported | ended normally
- stage_case.py case_8383: staged case_8383.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 9 | b02-8383-c0-r1 | end ≤2026-10-04T05:50:29Z (logged on return; seq 9-10 ran together) | subagent_tokens 135080 | 460210 ms | tool_uses 45 | model not reported | ended normally
- seq 10 | b02-8383-c-r1 | end ≤2026-10-04T05:50:29Z | subagent_tokens 126424 | 298065 ms | tool_uses 29 | model not reported | ended normally
- seq 11 | b02-8383-c0-r2 | end ≤2026-10-04T05:57:50Z (logged on return; seq 11-12 ran together) | subagent_tokens 114626 | 407703 ms | tool_uses 34 | model not reported | ended normally
- seq 12 | b02-8383-c-r2 | end ≤2026-10-04T05:57:50Z | subagent_tokens 133635 | 243432 ms | tool_uses 25 | model not reported | ended normally
- stage_case.py case_fd06: staged case_fd06.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 13 | b02-fd06-c-r1 | end ≤2026-10-04T06:05:34Z (logged on return; seq 13-14 ran together) | subagent_tokens 128024 | 308896 ms | tool_uses 28 | model not reported | ended normally
- seq 14 | b02-fd06-c0-r1 | end ≤2026-10-04T06:05:34Z | subagent_tokens 125096 | 422958 ms | tool_uses 35 | model not reported | ended normally
- seq 15 | b02-fd06-c-r2 | end ≤2026-10-04T06:12:49Z (logged on return; seq 15-16 ran together) | subagent_tokens 125848 | 239150 ms | tool_uses 25 | model not reported | ended normally
- seq 16 | b02-fd06-c0-r2 | end ≤2026-10-04T06:12:49Z | subagent_tokens 132317 | 389776 ms | tool_uses 39 | model not reported | ended normally
- session-end audit (2026-10-04T06:12:50Z): python3 dev/baseline02/audit_transcripts.py (f4092ef6), audit.json sha256 prefix fb8291eae9fd. Output:
    b02-035a-c-r1          clean
    b02-035a-c-r2          clean
    b02-035a-c0-r1         clean
    b02-035a-c0-r2         clean
    b02-8383-c-r1          clean
    b02-8383-c-r2          clean
    b02-8383-c0-r1         RECORD
    b02-8383-c0-r2         clean
    b02-9135-c-r1          clean
    b02-9135-c-r2          clean
    b02-9135-c0-r1         RECORD
    b02-9135-c0-r2         clean
    b02-fd06-c-r1          clean
    b02-fd06-c-r2          clean
    b02-fd06-c0-r1         clean
    b02-fd06-c0-r2         clean
    16 transcripts audited
- session 1 end (2026-10-04T06:12:50Z): blocks 1-4 (seq 1-16) done; no run interrupted, no -x2. 16 transcripts and 16 reports (.md/.json, each JSON names its own run). Reports are the verbatim SubagentHandback text extracted from the transcript. Subagent tokens 2071966 (C0 1009899, C 1062067). Nothing scored or opened by the orchestrator. The challenge folder holds case_fd06; next seq 17 (block 5, case_9eb1), stage it first. Stage 1 ends at seq 36: stop there.
- Erratum (2026-10-04, noted after seq 16, before any scoring): CRITERIA section 5 says "Interim look after stage
  1 (36 runs) ... the 24 runs are scored". "24" is a leftover of the 12-case draft. Stage 1 is the 36 runs of
  seq 1-36 (nine cases), as the same sentence, runs.json, RUNBOOK.md and score_all.py --stage 1 say; all 36 are
  scored at the interim. The frozen document is not edited.

## Session 2 (orchestrator)

- start (2026-10-04T06:15:23Z): the user asked for seq 17-36 (blocks 5-9, the rest of stage 1), stopping after seq 36. su-b01-c0 and seismic-unix both appear in ToolSearch. sha256 of seq 17-36 task texts checked OK; audit_transcripts.py f4092ef6 and stage_case.py be79a4cb unchanged. hidden/ not read.
- stage_case.py case_9eb1: staged case_9eb1.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 17 | b02-9eb1-c0-r1 | end ≤2026-10-04T06:23:21Z (logged on return; seq 17-18 ran together) | subagent_tokens 133948 | 440785 ms | tool_uses 41 | model not reported | ended normally
- seq 18 | b02-9eb1-c-r1 | end ≤2026-10-04T06:23:21Z | subagent_tokens 129983 | 315603 ms | tool_uses 29 | model not reported | ended normally
- seq 19 | b02-9eb1-c-r2 | end ≤2026-10-04T06:30:44Z (logged on return; seq 19-20 ran together) | subagent_tokens 128422 | 323908 ms | tool_uses 27 | model not reported | ended normally
- seq 20 | b02-9eb1-c0-r2 | end ≤2026-10-04T06:30:44Z | subagent_tokens 131416 | 404321 ms | tool_uses 42 | model not reported | ended normally
- stage_case.py case_34e7: staged case_34e7.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 21 | b02-34e7-c-r1 | end ≤2026-10-04T06:42:46Z (logged on return; seq 21-22 ran together) | subagent_tokens 140510 | 326683 ms | tool_uses 30 | model not reported | ended normally
- seq 22 | b02-34e7-c0-r1 | end ≤2026-10-04T06:42:46Z (logged on return; seq 21-22 ran together) | subagent_tokens 158773 | 626074 ms | tool_uses 62 | model not reported | ended normally
- seq 23 | b02-34e7-c-r2 | end ≤2026-10-04T06:50:06Z (logged on return; seq 23-24 ran together) | subagent_tokens 157587 | 283593 ms | tool_uses 29 | model not reported | ended normally
- seq 24 | b02-34e7-c0-r2 | end ≤2026-10-04T06:50:06Z (logged on return; seq 23-24 ran together) | subagent_tokens 124978 | 363771 ms | tool_uses 35 | model not reported | ended normally
- stage_case.py case_7fc7: staged case_7fc7.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/; challenge folder: case_7fc7.sgy 
- seq 25 | b02-7fc7-c0-r1 | end ≤2026-10-04T07:00:23Z (logged on return; seq 25-26 ran together) | subagent_tokens 148175 | 563749 ms | tool_uses 45 | model not reported | ended normally
- seq 26 | b02-7fc7-c-r1 | end ≤2026-10-04T07:00:23Z (logged on return; seq 25-26 ran together) | subagent_tokens 127500 | 318136 ms | tool_uses 27 | model not reported | ended normally
- seq 27 | b02-7fc7-c0-r2 | end ≤2026-10-04T07:08:41Z (logged on return; seq 27-28 ran together) | subagent_tokens 130272 | 461787 ms | tool_uses 40 | model not reported | ended normally
- seq 28 | b02-7fc7-c-r2 | end ≤2026-10-04T07:08:41Z (logged on return; seq 27-28 ran together) | subagent_tokens 129345 | 296686 ms | tool_uses 28 | model not reported | ended normally
- stage_case.py case_0cdd: staged case_0cdd.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 29 | b02-0cdd-c-r1 | end ≤2026-10-04T07:17:44Z (logged on return; seq 29-30 ran together) | subagent_tokens 157593 | 399005 ms | tool_uses 34 | model not reported | ended normally
- seq 30 | b02-0cdd-c0-r1 | end ≤2026-10-04T07:17:44Z (logged on return; seq 29-30 ran together) | subagent_tokens 123299 | 502058 ms | tool_uses 36 | model not reported | ended normally
- seq 31 | b02-0cdd-c-r2 | end ≤2026-10-04T07:23:18Z (logged on return; seq 31-32 ran together) | subagent_tokens 136178 | 293668 ms | tool_uses 29 | model not reported | ended normally
- seq 32 | b02-0cdd-c0-r2 | end ≤2026-10-04T07:23:18Z (logged on return; seq 31-32 ran together) | subagent_tokens 120851 | 197638 ms | tool_uses 25 | model not reported | ended normally
- stage_case.py case_4133: staged case_4133.sgy (sha256 ok); challenge folder holds only it; 17 in _b02_hold/
- seq 33 | b02-4133-c-r1 | end ≤2026-10-04T07:30:47Z (logged on return; seq 33-34 ran together) | subagent_tokens 111016 | 205437 ms | tool_uses 17 | model not reported | ended normally
- seq 34 | b02-4133-c0-r1 | end ≤2026-10-04T07:30:47Z (logged on return; seq 33-34 ran together) | subagent_tokens 129435 | 405812 ms | tool_uses 37 | model not reported | ended normally
- seq 35 | b02-4133-c0-r2 | end ≤2026-10-04T07:41:23Z (logged on return; seq 35-36 ran together) | subagent_tokens 120431 | 433853 ms | tool_uses 37 | model not reported | ended normally
- seq 36 | b02-4133-c-r2 | end ≤2026-10-04T07:41:23Z (logged on return; seq 35-36 ran together) | subagent_tokens 174141 | 555503 ms | tool_uses 47 | model not reported | ended normally
- session-end audit (2026-10-04T07:41:45Z): python3 dev/baseline02/audit_transcripts.py (f4092ef6), audit.json sha256 prefix 3c0e59fecf38. Output:
    b02-035a-c-r1          clean
    b02-035a-c-r2          clean
    b02-035a-c0-r1         clean
    b02-035a-c0-r2         clean
    b02-0cdd-c-r1          clean
    b02-0cdd-c-r2          clean
    b02-0cdd-c0-r1         clean
    b02-0cdd-c0-r2         clean
    b02-34e7-c-r1          clean
    b02-34e7-c-r2          clean
    b02-34e7-c0-r1         clean
    b02-34e7-c0-r2         clean
    b02-4133-c-r1          clean
    b02-4133-c-r2          clean
    b02-4133-c0-r1         RECORD
    b02-4133-c0-r2         RECORD
    b02-7fc7-c-r1          clean
    b02-7fc7-c-r2          clean
    b02-7fc7-c0-r1         RECORD
    b02-7fc7-c0-r2         clean
    b02-8383-c-r1          clean
    b02-8383-c-r2          clean
    b02-8383-c0-r1         RECORD
    b02-8383-c0-r2         clean
    b02-9135-c-r1          clean
    b02-9135-c-r2          clean
    b02-9135-c0-r1         RECORD
    b02-9135-c0-r2         clean
    b02-9eb1-c-r1          clean
    b02-9eb1-c-r2          clean
    b02-9eb1-c0-r1         clean
    b02-9eb1-c0-r2         RECORD
    b02-fd06-c-r1          clean
    b02-fd06-c-r2          clean
    b02-fd06-c0-r1         clean
    b02-fd06-c0-r2         clean
    36 transcripts audited
  RECORD reason (all six, C0 runs: 9135-c0-r1, 8383-c0-r1, 9eb1-c0-r2, 7fc7-c0-r1, 4133-c0-r1, 4133-c0-r2): "su_status: output mentions ['b01-00aa-c0-r1', 'b01-00aa-c0-r2', 'b01-2032-c0-r1']". 0 INVALID, so no -x2 rerun.
- session 2 end (2026-10-04T07:41:45Z): blocks 5-9 (seq 17-36) done; no run interrupted, no -x2. device_bash answered "Workspace still starting" a few times between runs (orchestrator only; retried, no run affected). 36 transcripts and 36 reports (.md/.json, each JSON names its own run); reports are the verbatim SubagentHandback text extracted from the transcript. Subagent tokens this session 2713853 (C0 1321578, C 1392275); stage 1 total 4785819. Nothing scored or opened by the orchestrator; hidden/ not read. The challenge folder holds case_4133. STAGE 1 COMPLETE: stopped after seq 36 as instructed. Next seq 37 (b02-3b69-c0-r1, stage 2) only when the user says so.
- Interim (2026-10-04, after seq 36, score_all.py --stage 1, script hash as frozen fb7baa79; scores_stage1.json):
  d by case P4 0, P5 -1, P6 -0.5, P8 0, P9 0, Q1 +1, Q3 -0.5, Q4 +0.5, Q7 +1; mean d = 0.056. Rule: mean d > 0,
  so the futility stop does not apply (CONTINUE). Classes C0: A 6, A* 3, Bn 6, C 3; C: A 9, A* 4, Bn 4, E 1. No
  claim is made at the interim. Not pre-registered, for the user's decision only: resampling the nine stage 2
  cases from the observed case differences (stage 1, or stage 1 pooled with study 01) gives a final p < 0.05 in
  about 2-8% of draws. Nothing is changed.
- 2026-10-04: user decision after the interim: study 02 is stopped after stage 1 (seq 1-36). The futility rule did not require it (mean d 0.056 > 0); the stop is the user's, on the low chance of a significant final test. The claim of section 1 is reported as not supported; stage 2 (seq 37-72) is not run. No stage 2 case was shown to any agent.

## Addendum 2026-10-19: F3 denominator (revision 1 of the F3 script)

An external review found that dev/baseline01/f3_system_vs_agent.py counted a run in the F3 denominator only when the
system warned or the agent overrode it. CRITERIA section 9 defines the denominator as the runs where the system
refused or warned, so a run in which the system refused and the agent followed the refusal was left out. Revision 1
(dev/baseline01/f3_system_vs_agent_rev1.py) also counts a run as refused when the system released no stack
(stack.completed not PASS). The first script and f3.json are kept unchanged; the revision writes f3_rev1.json.
Result: study 01, 0 of 7 (unchanged, no C run ended in a system refusal). Study 02 stage 1, 0 of 8 instead of
0 of 7; the added run is b02-4133-c-r1 (feasibility refused, the agent abstained). The numerator is 0 in both.
Both scores files were recomputed from the public repository and the data archive alone and were identical.
