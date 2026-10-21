# Baseline study 01: run log

One line per run (seq, run, end UTC, subagent tokens, duration, model, notes), plus addenda.


- seq 1 | b01-4753-b-r1 | end ≤2026-09-30T08:20:44Z (logged on return; seq 1–3 ran concurrently) | subagent_tokens 365450 | 1016660 ms | tool_uses 94 | model not reported by Agent tool (session model claude-opus-5-5, no override) | ended normally
- seq 2 | b01-4753-c0-r1 | end ≤2026-09-30T08:20:44Z | subagent_tokens 134971 | 652558 ms | tool_uses 57 | model not reported | ended normally
- seq 3 | b01-4753-c-r1 | end ≤2026-09-30T08:20:44Z | subagent_tokens 162311 | 558974 ms | tool_uses 60 | model not reported | ended normally. UNUSUAL: agent reports dataset b01-4753-c-r1 already existed on the production server (imported 08:01:22 from the same case file, same sha256, no other steps), so its own dataset_import_segy was refused and it worked from that import. No earlier start of this run is recorded in this log; possibly the agent's own first import (timestamp near launch). Not investigated further; run treated as final per RUNBOOK.
  - check after seq 3 (08:22:01Z): dataset_list (names only) on seismic-unix and su-b01-c0 shows no formal-run dataset other than b01-4753-c-r1 / b01-4753-c0-r1 (plus the dry-run ids); no upcoming run name is pre-registered.
- seq 4 | b01-4753-c-r2 | end ≤2026-09-30T08:38:45Z (logged on return; seq 4–6 ran concurrently) | subagent_tokens 132676 | 316876 ms | tool_uses 41 | model not reported | ended normally
- seq 5 | b01-4753-c0-r2 | end ≤2026-09-30T08:38:45Z | subagent_tokens 127397 | 818567 ms | tool_uses 58 | model not reported | ended normally
- seq 6 | b01-4753-b-r2 | end ≤2026-09-30T08:38:45Z | subagent_tokens 267575 | 936708 ms | tool_uses 109 | model not reported | ended normally
- seq 7 | b01-3cf3-c0-r1 | end ≤2026-09-30T08:54:43Z (logged on return; seq 7–9 ran concurrently) | subagent_tokens 131262 | 897245 ms | tool_uses 57 | model not reported | ended normally
- seq 8 | b01-3cf3-c-r1 | end ≤2026-09-30T08:54:43Z | subagent_tokens 136384 | 855916 ms | tool_uses 49 | model not reported | ended normally
- seq 9 | b01-3cf3-b-r1 | end ≤2026-09-30T08:54:43Z | subagent_tokens 248728 | 888045 ms | tool_uses 73 | model not reported | ended normally. UNUSUAL (for the user's review, not acted on): agent reports all 3 B conditioning passes were charged to pipelines (sufilter | sumute | susort) that failed on a susort key-argument error and wrote no conditioned gathers; if the B counter charges a pass for a failed pipeline that writes no file, that differs from CRITERIA 3.6 ("writes a new gather file") and may be a harness counting defect. Run treated as final.
- seq 10 | b01-3cf3-c0-r2 | end ≤2026-09-30T09:11:20Z (logged on return; seq 10–12 ran concurrently) | subagent_tokens 141088 | 807141 ms | tool_uses 62 | model not reported | ended normally
- seq 11 | b01-3cf3-b-r2 | end ≤2026-09-30T09:11:20Z | subagent_tokens 266671 | 667831 ms | tool_uses 70 | model not reported | ended normally
- seq 12 | b01-3cf3-c-r2 | end ≤2026-09-30T09:11:20Z | subagent_tokens 151238 | 923281 ms | tool_uses 49 | model not reported | ended normally
- session end (2026-09-30T09:11:20Z): case blocks 1-2 (seq 1-12) done, no interruptions, no -x2 reruns; subagent tokens total 2365801. Next seq 13 (block 3, case_580e).
  - correction to the session-end line above: subagent tokens total for seq 1-12 is 2265751 (not 2365801; arithmetic slip by the orchestrator).

## Addendum 1 (2026-09-30, after seq 1-12, before seq 13): B counter charged failed calls

- Defect (harness, CRITERIA section 11): evalsrv/b01core.py charge() ran before the programs and saved its counts
  whatever the result, so a call that failed (non-zero exit, no gather file written) still used a processing
  action, a conditioning pass or a velocity action. CRITERIA 3.6 counts a pass as a decision that "writes a new
  gather file" and a processing action as a call that "creates a new data product"; a failed call does neither.
  Found from the seq 9 report (three failed sufilter | sumute | susort pipelines charged as the three passes).
- Fix: caps are still checked before a call runs (a call that would exceed a cap if it succeeded is refused); the
  tool call is always counted; processing actions, conditioning passes and velocity actions are charged only when
  every program exits 0 and the output file, if any, is not empty. Refusals are now written to the run log
  ({"interface": "budget", "refused": ...}). Nothing else changed: caps, the pass rule (suwind subset is not a
  pass), velocity signatures, allowlists and tool texts are as frozen. b01core.py e04bfa6c -> 52962912;
  tests/test_b01_evalsrv.py gains test_failed_call_is_not_charged (14 tests pass). C0 and C are unaffected (their
  budgets are the production code's own). su-b01-b loads the fix at the next app restart (see below).
- Rerun rule, fixed here before the B run logs of seq 1-12 are replayed: the logged calls of each B run are
  counted twice, with the old rule (every call with an output file) and the corrected rule (only calls with exit
  0). A run is repeated from the start as <run>-x2 if, under the old rule, a capped budget (processing,
  velocity, conditioning) reached its cap while the corrected count for that budget stays below the cap: the
  defect then held the run at a spent budget (refused, or told nothing was left). Otherwise the run is final,
  because the failed calls changed only the displayed remainder. The original run stays in the record; only the
  run logs' call records (programs, exit codes) are read, not reports, artifacts or outcomes.
- Replay of the B run logs of seq 1-12 (calls with an output file; old rule / corrected rule; caps 60/6/3):
  - seq 1 b01-4753-b-r1: 5 failed calls with output; processing 20/15, velocity 1/1, passes 3/2 -> passes reached
    the cap only because of the defect: REPEAT as b01-4753-b-r1-x2.
  - seq 6 b01-4753-b-r2: 5 failed; processing 16/11, velocity 3/3, passes 2/2 -> final.
  - seq 9 b01-3cf3-b-r1: 7 failed; processing 18/11, velocity 1/1, passes 3/0 -> REPEAT as b01-3cf3-b-r1-x2.
  - seq 11 b01-3cf3-b-r2: 4 failed; processing 10/6, velocity 3/3, passes 1/1 -> final.
  The originals of seq 1 and 9 stay in reports/, runlogs/ and submitted/ but are not scored; the -x2 runs replace
  them. Their task texts are the frozen texts with the run name replaced by <run>-x2 (run_prompts_x2/reruns.json:
  paths, sha256 of each derived text and of its frozen source). Condition order within the blocks is unchanged;
  only the time of these two B runs moves.
- Next session: after the app restart, check that su-b01-b's budget(run) answers, then run b01-4753-b-r1-x2 and
  b01-3cf3-b-r1-x2 first (task text from run_prompts_x2/, sha256 checked against reruns.json), logged as seq 1-x2
  and seq 9-x2, then continue at seq 13 as RUNBOOK says.

## Session 2 (orchestrator), after Addendum 1

- pre-checks (2026-09-30T09:52:05Z): run_prompts_x2/reruns.json read; both -x2 texts match their sha256, their sources match runs.json, and each differs from its frozen text only in the run name; evalsrv/b01core.py on disk sha256 prefix 52962912; su-b01-b budget(run) answers. The session's link to the user's computer dropped once before these checks (no run was in progress).
- seq 1-x2 | b01-4753-b-r1-x2 | end ≤2026-09-30T09:52:05Z (logged on return; 1-x2 and 9-x2 ran concurrently) | subagent_tokens 304312 | 1091425 ms | tool_uses 112 | model not reported | ended normally
- seq 9-x2 | b01-3cf3-b-r1-x2 | end ≤2026-09-30T09:52:05Z | subagent_tokens 224406 | 769966 ms | tool_uses 70 | model not reported | ended normally
  - note: the time on the pre-checks line is when it was written (after 1-x2/9-x2 returned); the checks themselves ran just before the two launches, about 09:33Z.
- blocks 3-6 (seq 13-36) chosen by the user for this session; sha256 of seq 13-36 checked OK before seq 13.
- seq 13 | b01-580e-b-r1 | end ≤2026-09-30T10:13:47Z (logged on return; seq 13-15 ran concurrently) | subagent_tokens 315947 | 967295 ms | tool_uses 119 | model not reported | ended normally. Note: agent reports a B budget refusal (a further conditioning pass refused after the 3-pass cap was reached); recorded, not acted on.
- seq 14 | b01-580e-c0-r1 | end ≤2026-09-30T10:13:47Z | subagent_tokens 131217 | 911783 ms | tool_uses 59 | model not reported | ended normally
- seq 15 | b01-580e-c-r1 | end ≤2026-09-30T10:13:47Z | subagent_tokens 133571 | 994760 ms | tool_uses 41 | model not reported | ended normally
- seq 16 | b01-580e-c0-r2 | end ≤2026-09-30T10:39:45Z (logged on return; seq 16-18 ran concurrently) | subagent_tokens 162001 | 1144541 ms | tool_uses 77 | model not reported | ended normally
- seq 17 | b01-580e-b-r2 | end ≤2026-09-30T10:39:45Z | subagent_tokens 283364 | 943789 ms | tool_uses 114 | model not reported | ended normally
- seq 18 | b01-580e-c-r2 | end ≤2026-09-30T10:39:45Z | subagent_tokens 154828 | 1489210 ms | tool_uses 79 | model not reported | ended normally
- seq 19 | b01-f44e-c-r1 | end ≤2026-09-30T11:11:12Z (logged on return; seq 19-21 ran concurrently) | subagent_tokens 168583 | 1819531 ms | tool_uses 82 | model not reported | ended normally
- seq 20 | b01-f44e-b-r1 | end ≤2026-09-30T11:11:12Z | subagent_tokens 367697 | 1426796 ms | tool_uses 135 | model not reported | ended normally
- seq 21 | b01-f44e-c0-r1 | end ≤2026-09-30T11:11:12Z | subagent_tokens 164760 | 1707143 ms | tool_uses 93 | model not reported | ended normally
- seq 22 | b01-f44e-b-r2 | end ≤2026-09-30T11:46:22Z (logged on return; seq 22-24 ran concurrently) | subagent_tokens 401765 | 1782119 ms | tool_uses 144 | model not reported | ended normally
- seq 23 | b01-f44e-c-r2 | end ≤2026-09-30T11:46:22Z | subagent_tokens 207911 | 2026893 ms | tool_uses 94 | model not reported | ended normally
- seq 24 | b01-f44e-c0-r2 | end ≤2026-09-30T11:46:22Z | subagent_tokens 140684 | 1420058 ms | tool_uses 68 | model not reported | ended normally. Note (for the user's review, not acted on): as in seq 21, the agent reports that C0 refine_velocity returned a model with every function empty and that it was adopted as the current model before NMO. Whether an empty refinement being adopted is intended C0 behaviour (adoption ON for every product) or a harness defect is the user's call.
- seq 25 | b01-ac07-b-r1 | end ≤2026-09-30T12:06:39Z (logged on return; seq 25-27 ran concurrently) | subagent_tokens 353354 | 1044385 ms | tool_uses 74 | model not reported | ended normally. Note: agent reports it ran suvelan 5 times while budget() showed 2 velocity actions; recorded only (CRITERIA 3.6 counts one action per decision/parameterisation/input), not checked.
- seq 26 | b01-ac07-c0-r1 | end ≤2026-09-30T12:06:39Z | subagent_tokens 128650 | 892932 ms | tool_uses 58 | model not reported | ended normally
- seq 27 | b01-ac07-c-r1 | end ≤2026-09-30T12:06:39Z | subagent_tokens 140824 | 374634 ms | tool_uses 42 | model not reported | ended normally. (The user's machine workspace restarted once while these reports were being saved, after all three runs had returned; no run affected.)
- seq 28 | b01-ac07-c-r2 | end ≤2026-09-30T12:21:46Z (logged on return; seq 28-30 ran concurrently) | subagent_tokens 139646 | 315089 ms | tool_uses 41 | model not reported | ended normally
- seq 29 | b01-ac07-c0-r2 | end ≤2026-09-30T12:21:46Z | subagent_tokens 122141 | 420678 ms | tool_uses 46 | model not reported | ended normally
- seq 30 | b01-ac07-b-r2 | end ≤2026-09-30T12:21:46Z | subagent_tokens 270091 | 828386 ms | tool_uses 74 | model not reported | ended normally
- seq 31 | b01-689c-b-r1 | end ≤2026-09-30T12:34:22Z (logged on return; seq 31-33 ran concurrently) | subagent_tokens 232848 | 703349 ms | tool_uses 72 | model not reported | ended normally
- seq 32 | b01-689c-c0-r1 | end ≤2026-09-30T12:34:22Z | subagent_tokens 130243 | 609875 ms | tool_uses 63 | model not reported | ended normally
- seq 33 | b01-689c-c-r1 | end ≤2026-09-30T12:34:22Z | subagent_tokens 122654 | 289681 ms | tool_uses 36 | model not reported | ended normally
- seq 34 | b01-689c-c-r2 | end ≤2026-09-30T12:50:45Z (logged on return; seq 34-36 ran concurrently) | subagent_tokens 126990 | 295244 ms | tool_uses 37 | model not reported | ended normally
- seq 35 | b01-689c-c0-r2 | end ≤2026-09-30T12:50:45Z | subagent_tokens 132192 | 486625 ms | tool_uses 54 | model not reported | ended normally. Note: agent again reports C0 velocity functions returned empty (1400 m/s, zero semblance) at outer CDPs and adopted into the model before being replaced (cf. seq 21, 24).
- seq 36 | b01-689c-b-r2 | end ≤2026-09-30T12:50:45Z | subagent_tokens 275056 | 823637 ms | tool_uses 97 | model not reported | ended normally. Notes for the user's review, not acted on: (a) the agent states "the other files in the input directory each hold 12096 traces", i.e. it saw other challenge files through list_files of the input directory (CRITERIA 14.6 audits results/baseline01/, dev/baseline01/, test_dataset/Marm2_v2/; whether this counts is the user's call, the run log shows what was accessed); (b) the agent says budget() showed 3 conditioning passes used although it ran two mutes as conditioning, and attributes the third to linear-moveout QC runs; not checked.
- session 2 end (2026-09-30T12:50:45Z): seq 1-x2, 9-x2 and blocks 3-6 (seq 13-36) done; no run interrupted, no -x2/-x3 reruns needed this session. The user's machine workspace restarted twice between runs (after seq 25-27 and after seq 34-36 returned), no run affected. Next seq 37 (block 7, case_2032).
  - session 2 subagent tokens: seq 1-x2 + 9-x2 528718; seq 13-36 4807017; total 5335735 (B 3028840, C0 1111888, C 1195007).

## Addendum 2 (2026-10-01, after seq 36, before seq 37): isolation and pass counting

Written before any replay or transcript audit below; the rules decide, not the outcomes.

- Defect A (harness isolation, CRITERIA 3.7 and 14.6): B's list_files returned every file of the challenge folder
  with its size, and B could read any file there. No B run read another case file (all 14 formal B run logs
  checked: every input is the run's own case or its own run directory). File sizes are the same for ten cases
  (65854224 bytes); case_689c (16727568) and case_2032 (47039760) differ, so for those two the listing tells the
  agent its own line is shorter than its siblings. C and C0 have the same exposure through the production
  su_list_files (it lists test_dataset/ and results/), and su_log can return processing records of other runs
  (the C log is shared by all C runs, the C0 log by all C0 runs).
- Defect B (harness counting, CRITERIA 3.6): B charged a conditioning pass for a successful call that contained a
  conditioning program and no suwind, even when the pipeline ended in a program that writes no gather (for
  example sustatic | sumax, or ... | sustack). 3.6 counts a decision that "writes a new gather file".
- Fixes (evalsrv/b01core.py): (1) list_files shows only the run's own case file, and reads from the input folder
  are limited to that file (the case is the second field of the run name, b01-<case>-...); (2) a pass is charged
  only if the pipeline contains no program that writes something other than a gather: sumax, sustack, suvelan,
  surange, sugethw, suascii, sudoc, suresstat. Caps, the suwind rule and every tool text are unchanged.
- Prevention for all conditions (file placement only, no code): during a block, test_dataset/Baseline01_challenge/
  holds only that block's case file; the other eleven wait in _b01_hold/ at the project root, which no server
  can list or read. dev/baseline01/stage_case.py <case_id> moves the files and checks every sha256 against
  hidden/challenge_set.json. The orchestrator runs it before each block (and before a rerun of an earlier case).
- Rule 1 (exposure, B): every completed B run of case_689c (seq 31, 36) is repeated as <run>-x2; B runs of the
  ten equal-size cases are final, because the listing carried no information about their own case.
- Rule 2 (counting, B): each completed B run is replayed from its run log with the counter as it ran and with the
  counter of Addendum 1 + 2. A run is repeated as <run>-x2 if a capped budget reached its cap under the counter
  as it ran and stays below the cap under the corrected counter.
- Rule 3 (transcripts, all conditions): the orchestrating sessions copy every formal run's subagent transcript to
  results/baseline01/transcripts/ (now for seq 1-36 and the x2 runs, then at the end of each session). A run is
  invalid and repeated as <run>-x2 if a tool output it received contains (i) a processing record of another run
  (a dataset id or run name other than its own), (ii) data or headers of a test_dataset file other than its case
  file, (iii) the content of any file under results/baseline01/, dev/baseline01/ or test_dataset/Marm2_v2/, or
  (iv) for a case_689c or case_2032 run, a listing of the challenge folder with file sizes. A listing of file
  names alone is recorded, not invalidating. A run whose transcript is missing is recorded as unaudited.
- Implementation: evalsrv/b01core.py 52962912 -> 6b9e65df; tests/test_b01_evalsrv.py gains
  test_isolation_and_non_gather_pass (15 tests pass, runs renamed b01-tst-*); dev/baseline01/stage_case.py (0c5afe10);
  dev/baseline01/audit_transcripts.py (b3eae0b1, implements rule 3 mechanically; checked on a synthetic transcript).
  stage_case.py case_689c was run on 2026-10-01: the challenge folder holds only case_689c.sgy, eleven files in
  _b01_hold/, sha256 ok.
- Rule 2 replay (processing/velocity/passes, as ran -> corrected; refusals from the run log):
  - b01-580e-b-r1 (seq 13): 9/3/3 -> 9/3/1, a pass refusal was logged -> REPEAT as b01-580e-b-r1-x2.
  - b01-689c-b-r2 (seq 36): passes 5 -> 2 in the replay (the replay cannot see empty outputs; the agent saw 3) ->
    repeated anyway under rule 1.
  - b01-3cf3-b-r2 passes 1 -> 0, b01-f44e-b-r1/r2 3 -> 3, all others unchanged: final.
- Reruns from this addendum (task texts and sha256 in run_prompts_x2/reruns.json, entries with "addendum": 2):
  b01-580e-b-r1-x2 (seq 13), b01-689c-b-r1-x2 (seq 31), b01-689c-b-r2-x2 (seq 36). Rule 3 may add more.
- Procedure from now on (in addition to RUNBOOK): (1) before each block or rerun, python3
  dev/baseline01/stage_case.py <case_id> and check that it prints "staged"; (2) at the end of each session, copy
  every formal run's subagent transcript to results/baseline01/transcripts/<run>.jsonl and run
  dev/baseline01/audit_transcripts.py; a run it marks INVALID is repeated as <run>-x2 (logged; the user is told).

## Session 3 (orchestrator), after Addendum 2

- transcripts (2026-10-01T05:14:30Z): the orchestrating session's subagent store holds the transcripts of all 38 formal runs so far (seq 1-36 and b01-4753-b-r1-x2, b01-3cf3-b-r1-x2), identified by "Your run name is ..." in the first user message; copied verbatim to results/baseline01/transcripts/<run>.jsonl (sha256 checked against the source, 38/38). Unaudited: none.
- audit (2026-10-01T05:14:30Z): python3 dev/baseline01/audit_transcripts.py (b3eae0b1), 38 audited, audit.json sha256 prefix 02887cd914b3. INVALID: b01-689c-b-r1, b01-689c-b-r2, both (iv) list_files listed the challenge folder with sizes; both are already reruns under rule 1 (reruns.json entries seq 31 and 36, addendum 2), so no new entry was added. RECORD (listings only, not invalidating): 14 list_files and 14 su_status records over 25 runs. Clean: 11 runs. No run had a hidden-path read or another run's processing record.
- the five -x2 texts in run_prompts_x2/ match reruns.json sha256; the three Addendum 2 texts differ from their frozen texts only in the run name.
- stage_case.py case_689c: staged, sha256 ok; b01core.py on disk 6b9e65df. b01-689c-b-r1-x2 and b01-689c-b-r2-x2 launched together.
- seq 31-x2 | b01-689c-b-r1-x2 | end ≤2026-10-01T05:29:43Z (logged on return; ran concurrently with 36-x2) | subagent_tokens 266214 | 825441 ms | tool_uses 92 | model not reported | ended normally
- seq 36-x2 | b01-689c-b-r2-x2 | end ≤2026-10-01T05:29:43Z | subagent_tokens 254111 | 847309 ms | tool_uses 106 | model not reported | ended normally
- stage_case.py case_580e: staged, sha256 ok.
- seq 13-x2 | b01-580e-b-r1-x2 | end ≤2026-10-01T05:48:48Z | subagent_tokens 330444 | 1115099 ms | tool_uses 132 | model not reported | ended normally
- correction (2026-10-01T05:48:59Z): the session 2 end line above named the next block wrongly as "block 7, case_2032". runs.json gives block 7 = case_ddc7 (seq 37-42); case_2032 is block 10 (seq 55-60). stage_case.py case_2032 was run on the user's instruction (based on that wrong line), then stage_case.py case_ddc7 was run before any seq 37 launch; no run used the case_2032 staging.
- blocks 7-10 (seq 37-60) chosen by the user for this session; sha256 of seq 37-72 checked OK. From seq 37 on, reports/<run>.md is the verbatim SubagentHandback text extracted from the run's transcript (no retyping), and the transcript is copied to transcripts/ as each run returns.
- seq 37 | b01-ddc7-c0-r1 | end ≤2026-10-01T06:08:57Z (logged on return; seq 37-39 ran concurrently) | subagent_tokens 143713 | 1090716 ms | tool_uses 70 | model not reported | ended normally
- seq 38 | b01-ddc7-c-r1 | end ≤2026-10-01T06:08:57Z | subagent_tokens 148027 | 810088 ms | tool_uses 49 | model not reported | ended normally
- seq 39 | b01-ddc7-b-r1 | end ≤2026-10-01T06:08:57Z | subagent_tokens 341604 | 982599 ms | tool_uses 76 | model not reported | ended normally
- seq 40 | b01-ddc7-c0-r2 | end ≤2026-10-01T06:29:39Z (logged on return; seq 40-42 ran concurrently) | subagent_tokens 123215 | 1109331 ms | tool_uses 57 | model not reported | ended normally
- seq 41 | b01-ddc7-b-r2 | end ≤2026-10-01T06:29:39Z | subagent_tokens 290169 | 1194291 ms | tool_uses 112 | model not reported | ended normally
- seq 42 | b01-ddc7-c-r2 | end ≤2026-10-01T06:29:39Z | subagent_tokens 147578 | 1152909 ms | tool_uses 57 | model not reported | ended normally
- stage_case.py case_fadd: staged, sha256 ok (before seq 43).
- seq 43 | b01-fadd-c-r1 | end ≤2026-10-01T06:49:44Z (logged on return; seq 43-45 ran concurrently) | subagent_tokens 135616 | 665579 ms | tool_uses 38 | model not reported | ended normally
- seq 44 | b01-fadd-b-r1 | end ≤2026-10-01T06:49:44Z | subagent_tokens 362737 | 1162676 ms | tool_uses 171 | model not reported | ended normally
- seq 45 | b01-fadd-c0-r1 | end ≤2026-10-01T06:49:44Z | subagent_tokens 130077 | 1010943 ms | tool_uses 66 | model not reported | ended normally
- seq 46 | b01-fadd-b-r2 | end ≤2026-10-01T07:10:42Z (logged on return; seq 46-48 ran concurrently) | subagent_tokens 427604 | 944754 ms | tool_uses 84 | model not reported | ended normally
- seq 47 | b01-fadd-c-r2 | end ≤2026-10-01T07:10:42Z | subagent_tokens 166109 | 1217587 ms | tool_uses 68 | model not reported | ended normally
- seq 48 | b01-fadd-c0-r2 | end ≤2026-10-01T07:10:42Z | subagent_tokens 125798 | 995157 ms | tool_uses 58 | model not reported | ended normally
- stage_case.py case_b745: staged, sha256 ok (before seq 49).
- seq 49 | b01-b745-c-r1 | end ≤2026-10-01T07:30:33Z (logged on return; seq 49-51 ran concurrently) | subagent_tokens 157123 | 954332 ms | tool_uses 55 | model not reported | ended normally
- seq 50 | b01-b745-b-r1 | end ≤2026-10-01T07:30:33Z | subagent_tokens 454818 | 1125316 ms | tool_uses 107 | model not reported | ended normally
- seq 51 | b01-b745-c0-r1 | end ≤2026-10-01T07:30:33Z | subagent_tokens 132618 | 1140546 ms | tool_uses 62 | model not reported | ended normally
- seq 52 | b01-b745-b-r2 | end ≤2026-10-01T07:54:40Z (logged on return; seq 52-54 ran concurrently) | subagent_tokens 346690 | 886788 ms | tool_uses 91 | model not reported | ended normally. Note for the user's review, not acted on: the agent reports that all 3 conditioning passes went to failed attempts ("the first sort was piped and wrote a corrupt file, and the parameter-format retries also counted"), so no mute or filter could be applied. Whether the counter of Addendum 1+2 charged calls that wrote no valid gather is the user's call (rule 2 replay from the run log).
- seq 53 | b01-b745-c-r2 | end ≤2026-10-01T07:54:40Z | subagent_tokens 150667 | 1402857 ms | tool_uses 77 | model not reported | ended normally
- seq 54 | b01-b745-c0-r2 | end ≤2026-10-01T07:54:40Z | subagent_tokens 136407 | 910233 ms | tool_uses 58 | model not reported | ended normally
- stage_case.py case_2032: staged, sha256 ok (before seq 55).
- seq 55 | b01-2032-c0-r1 | end ≤2026-10-01T08:10:03Z (logged on return; seq 55-57 ran concurrently) | subagent_tokens 124846 | 890532 ms | tool_uses 51 | model not reported | ended normally
- seq 56 | b01-2032-c-r1 | end ≤2026-10-01T08:10:03Z | subagent_tokens 142060 | 876997 ms | tool_uses 47 | model not reported | ended normally
- seq 57 | b01-2032-b-r1 | end ≤2026-10-01T08:10:03Z | subagent_tokens 213432 | 748338 ms | tool_uses 102 | model not reported | ended normally
- seq 58 | b01-2032-c0-r2 | end ≤2026-10-01T08:28:56Z (logged on return; seq 58-60 ran concurrently) | subagent_tokens 129092 | 1053821 ms | tool_uses 67 | model not reported | ended normally
- seq 59 | b01-2032-b-r2 | end ≤2026-10-01T08:28:56Z | subagent_tokens 273911 | 918262 ms | tool_uses 112 | model not reported | ended normally
- seq 60 | b01-2032-c-r2 | end ≤2026-10-01T08:28:56Z | subagent_tokens 140597 | 825492 ms | tool_uses 44 | model not reported | ended normally
- report check (2026-10-01T08:29:18Z): every reports/<run>.md written by retyping in sessions 1-3 (seq 1-36, the five -x2 runs) was compared with the SubagentHandback text in its transcript: all 41 identical except a single trailing newline. From seq 37 on, reports are the extracted text itself.
- session-end transcripts (2026-10-01T08:29:18Z): 65 transcripts in transcripts/ (all formal runs so far: seq 1-60 and the five -x2 runs); none missing, none unaudited.
- session-end audit (2026-10-01T08:29:18Z): audit_transcripts.py (b3eae0b1), 65 audited, audit.json sha256 prefix ddaf69838cdf. INVALID: b01-689c-b-r1, b01-689c-b-r2 only (already repeated as -x2 this session). The 27 runs of this session: 19 clean, 8 RECORD (su_status output listing other runs' dataset names, names only, not invalidating), 0 INVALID. No new rerun.
- session 3 end (2026-10-01T08:29:18Z): reruns seq 31-x2, 36-x2, 13-x2 and blocks 7-10 (seq 37-60) done; no run interrupted. Subagent tokens: reruns 850769; seq 37-60 4944508; total 5795277 (B 3561734, C0 1045766, C 1187777). The challenge folder holds case_2032 (stage the next block's case before running it). Next seq 61 (block 11, case_00aa).
- Review of seq 52 (b01-b745-b-r2), 2026-10-02, from the run log's call records only: the three passes were
  charged to three calls that exited 0 and wrote a gather file with a conditioning program (sushw | sustatic ->
  shift.su twice, then sufilter | sumute | susort -> cmp.su); the three failed sufilter | sumute | susort calls
  (exit 13) were not charged; the fourth pass was refused at the cap. The counter followed CRITERIA 3.6 and
  Addenda 1-2. That the agent did not want two of the files it wrote is its own processing, a result (section
  11). No defect, no rerun; the run is final.

## Session 4 (orchestrator)

- start (2026-10-04T03:55:44Z): the user asked for seq 61-72 (blocks 11-12). sha256 of seq 61-72 task texts checked OK; b01core.py 6b9e65df, stage_case.py 0c5afe10, audit_transcripts.py b3eae0b1 unchanged. stage_case.py case_00aa: staged, sha256 ok.
- seq 61 | b01-00aa-c0-r1 | end ≤2026-10-04T04:09:29Z (logged on return; seq 61-63 ran concurrently) | subagent_tokens 121443 | 578254 ms | tool_uses 42 | model not reported | ended normally
- seq 62 | b01-00aa-c-r1 | end ≤2026-10-04T04:09:29Z | subagent_tokens 129633 | 391790 ms | tool_uses 31 | model not reported | ended normally
- seq 63 | b01-00aa-b-r1 | end ≤2026-10-04T04:09:29Z | subagent_tokens 234040 | 759294 ms | tool_uses 95 | model not reported | ended normally
- seq 64 | b01-00aa-c-r2 | end ≤2026-10-04T04:21:59Z (logged on return; seq 64-66 ran concurrently) | subagent_tokens 137061 | 466233 ms | tool_uses 33 | model not reported | ended normally
- seq 65 | b01-00aa-c0-r2 | end ≤2026-10-04T04:21:59Z | subagent_tokens 137628 | 524706 ms | tool_uses 45 | model not reported | ended normally
- seq 66 | b01-00aa-b-r2 | end ≤2026-10-04T04:21:59Z | subagent_tokens 211666 | 696800 ms | tool_uses 64 | model not reported | ended normally. Note for the user's review, not acted on: the agent reports that its 3 conditioning passes went to two linear-moveout diagnostics and a mute/sort pipeline that "wrote a corrupt file", after which sustatic was refused at the cap (same pattern as seq 52, which the user's review found to follow CRITERIA 3.6; a rule 2 replay from the run log would confirm).
- stage_case.py case_ee84: staged, sha256 ok (before seq 67).
- seq 67 | b01-ee84-c-r1 | end ≤2026-10-04T04:29:36Z (logged on return; seq 67-69 ran concurrently) | subagent_tokens 128744 | 339522 ms | tool_uses 28 | model not reported | ended normally
- seq 68 | b01-ee84-b-r1 | end ≤2026-10-04T04:29:36Z | subagent_tokens 172801 | 412265 ms | tool_uses 49 | model not reported | ended normally
- seq 69 | b01-ee84-c0-r1 | end ≤2026-10-04T04:29:36Z | subagent_tokens 128609 | 380215 ms | tool_uses 34 | model not reported | ended normally
- seq 70 | b01-ee84-b-r2 | end ≤2026-10-04T04:36:57Z (logged on return; seq 70-72 ran concurrently) | subagent_tokens 165200 | 400524 ms | tool_uses 47 | model not reported | ended normally
- seq 71 | b01-ee84-c-r2 | end ≤2026-10-04T04:36:57Z | subagent_tokens 135684 | 323299 ms | tool_uses 30 | model not reported | ended normally
- seq 72 | b01-ee84-c0-r2 | end ≤2026-10-04T04:36:57Z | subagent_tokens 125155 | 295696 ms | tool_uses 35 | model not reported | ended normally
- session-end transcripts (2026-10-04T04:37:09Z): 77 transcripts in transcripts/ = the 72 runs of runs.json and the five -x2 runs of reruns.json; none missing, none unaudited. 77 reports (.md and .json), each JSON block names its own run, no no_answer.
- session-end audit (2026-10-04T04:37:09Z): audit_transcripts.py (b3eae0b1), 77 audited, audit.json sha256 prefix 7f95c09fcbf4. INVALID: b01-689c-b-r1, b01-689c-b-r2 only (repeated as -x2 in session 3). The 12 runs of this session: 10 clean, 2 RECORD (b01-00aa-c0-r2, b01-ee84-c0-r1: su_status output listing other C0 dataset names, names only), 0 INVALID. No new rerun.
- session 4 end (2026-10-04T04:37:09Z): blocks 11-12 (seq 61-72) done; no run interrupted, no -x2/-x3. Subagent tokens this session 1827664 (B 783707, C0 512835, C 531122). All 72 formal runs and the five reruns (seq 1-x2, 9-x2, 13-x2, 31-x2, 36-x2) have now ended normally; subagent tokens over the four sessions 15224427 (2265751 + 5335735 + 5795277 + 1827664). Nothing has been scored or opened by the orchestrator. The challenge folder still holds case_ee84 only (eleven files in _b01_hold/). Open notes for the user's review remain as logged (seq 3, 21/24/35, 66).
- Review of seq 66 (b01-00aa-b-r2), 2026-10-04, call records only: the three passes went to three calls that
  exited 0 and wrote a gather file with a conditioning program (suchw | sustatic -> lmo.su twice, sumute | susort
  -> cmp_mute.su); two later conditioning calls were refused at the cap. Counted as CRITERIA 3.6 and Addenda 1-2
  say (a whole-file conditioning output is a pass; a diagnostic on a suwind subset is not). No defect; final.
- Run phase closed 2026-10-04: 72 formal runs + 5 reruns ended normally; 77 reports and 77 transcripts archived;
  final transcript audit: INVALID only b01-689c-b-r1 and b01-689c-b-r2 (both replaced by their -x2 runs). The
  scored set is runs.json with the five runs of run_prompts_x2/reruns.json replaced by their -x2 runs. Scoring
  starts after this line.
- 2026-10-04: primary scoring done (dev/baseline01/score_all.py ae92f730, scores.json 69704750); RESULT.md written. F1 holds: C rate 0 in C0 and C.
- 2026-10-06, F3 (CRITERIA section 9), dev/baseline01/f3_system_vs_agent.py -> results/baseline01/f3.json: of the 24
  C runs the system released 7 stacks with a WARN (none refused at the end); the agent reported all 7 as
  accept_with_warning, use restricted, with a category that maps to the system's reason. Override or ignore: 0 of
  7; F3 does not hold. In 15 runs system OK and agent accept; in 2 the system was OK and the agent restricted the
  stack on its own. Limits: the script reads the final manifest and report, so it tests the released stack; a
  conditioning pass rejected by its gate is not adopted by the system and cannot be used by the agent, so an
  override can only appear as an artifact that is not the system's stack (none). Written after scoring; no free
  parameter beyond the frozen WARN-to-category map. Same table for study 02 stage 1 (descriptive): 0 of 7.

## Addendum 2026-10-19: F3 denominator (revision 1 of the F3 script)

An external review found that dev/baseline01/f3_system_vs_agent.py counted a run in the F3 denominator only when the
system warned or the agent overrode it. CRITERIA section 9 defines the denominator as the runs where the system
refused or warned, so a run in which the system refused and the agent followed the refusal was left out. Revision 1
(dev/baseline01/f3_system_vs_agent_rev1.py) also counts a run as refused when the system released no stack
(stack.completed not PASS). The first script and f3.json are kept unchanged; the revision writes f3_rev1.json.
Result: study 01, 0 of 7 (unchanged, no C run ended in a system refusal). Study 02 stage 1, 0 of 8 instead of
0 of 7; the added run is b02-4133-c-r1 (feasibility refused, the agent abstained). The numerator is 0 in both.
Both scores files were recomputed from the public repository and the data archive alone and were identical.
