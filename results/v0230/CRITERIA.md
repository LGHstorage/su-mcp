# v0.23.0 criteria: a quality warning and a provenance caution (written before any code)

Written 2026-09-28 after v0.22.0 failed its criteria with one silent wrong stack (held-out band noise 1.6x: quality
0.549, half-stack ceiling 0.912, E2 0.58, reliability OK). Not edited after the first run; anything found before the
first run goes in an addendum. No new MCP tool schema (37 tools): no server restart.

## What v0.22 left

1. N1 warns below a half-stack ceiling of 0.9, but a stack reaches "good" (0.9 of the clean quality) only if the
   ceiling is well above 0.9, because velocity and other losses multiply on top of noise. On the 26 released v0.22
   stacks the three bad ones had ceilings 0.897-0.916 and the 23 good ones 0.944 or more. That split was seen after
   the run; it is a hypothesis for this version, tested on a new held-out ladder.
2. W2 (feasibility not established before binning) warned 15 of the 23 good v0.22 stacks. It says something true
   about provenance, not about quality, and one flag for both makes the flag uninformative.
3. Parallel runs: one tool call failed with PermissionError appending to logs/processing.jsonl (Windows file lock).

## Rules

**N2 (quality).** A stack is quality-WARN when its half-stack ceiling is below 0.95 (the existing W1 constant; no new
number). This replaces N1 NOISE_LIMITED and "E1 PARTIAL with ceiling < 0.95" in the warning, both of which it implies.
W3 (E2 measured fraction < 0.25) stays a quality warning. N1 and E1 are still reported.

**T2 (tiers).** reliability.level is WARN when any quality reason holds; otherwise CAUTION when only the provenance
reason W2 holds; otherwise OK. Both lists are reported separately (quality_reasons, provenance_reasons). W2 itself is
unchanged: every G1 stack still carries it. Nothing is released with less disclosure than in v0.22.

**L1 (log).** Appending to the processing log retries on PermissionError (up to 8 tries, 0.1-0.8 s back-off) before
failing. Stack evidence also records the dataset's velocity analyses used so far.

Everything else as v0.22 (D1, K1, K2, E2, W3, T1, G1, G2, R3, S1, RS2, budgets). No processing step changes, so no stack
byte changes.

## Protocol P5 = P4 of v0.22 (unchanged).

## Judgement matrix for this version

good = truth best-lag >= 0.560 (unchanged). A: good, OK. A~: good, CAUTION only. A*: good, WARN (quality false alarm).
Bn: not good, WARN. Bc: not good, CAUTION only. C: not good, OK. Bc is disclosed but not quality-warned; it is counted
and reported separately, and it is the category N2 is meant to empty.

## Evaluation

A. Regression. Stack bytes: Viking `181fc5ba…`, v2 cdp_list-5 `cbb46bd5…`, v2 default `7374cb63…` (v0.22). Viking and
   v2 reliability OK. Unit tests pass, data001 refusals included.
B. Retrospective (descriptive, evaluation harness only): the v0.23 rule applied to the recorded evidence (ceiling, E2,
   feasibility) of the released v0.21 and v0.22 stacks. Counts per category reported; not a test.
C. Eighth held-out ladder, generated after the code is frozen, seeds 81-83, P5 on every level. It aims at the zone
   between 0.9 and 0.95 ceiling:

| level | prediction |
|---|---|
| band noise 1.2x | A or Bn |
| band noise 1.4x | Bn |
| band noise 2.0x | Bn |
| white noise 1.3x | Bn or Bc; not C |
| white noise 1.5x | Bn |
| statics 20 ms + band noise 1.2x | A~ or Bn |
| statics 18 ms + white noise 1.0x | A~ or Bn |
| delay 120 ms + band noise 0.8x | A (T1) or Bn |

Failure of v0.23: any C in C; a regression byte change; more than two good stacks in C with a quality WARN (A*);
any budget overrun or false claim.
