# Baseline study 01: result (primary analysis, 2026-10-04)

Criteria: CRITERIA.md (frozen 2026-09-30T07:52:09Z). Runs: 72 scored runs (runs.json, with the five runs of
run_prompts_x2/reruns.json replaced by their -x2 runs; LOG.md addenda 1-2). Scores: scores.json, written by
dev/baseline01/score_all.py (classification and aggregation only; per-artifact scoring is the frozen
evaluate_run.py). Nothing was scored before the 72 runs and the transcript audit were complete.

## Verdict

The claim of CRITERIA section 1 is NOT supported. Failure condition F1 holds: the primary endpoint (C rate, C0
minus C) is 0.

| | B | C0 | C |
|---|---|---|---|
| C runs (silent wrong) of 24 | 2 | 0 | 0 |
| cases with any C of 12 | 2 | 0 | 0 |
| mean case C rate | 0.083 | 0 | 0 |

Primary test (C0 - C): mean d = 0 (every case 0), one-sided sign-flip p = 1.0, bootstrap 95% interval [0, 0].
H1 fails (F1: mean d < 1/12 and p >= 0.05). Evidence governance did not lower the silent-wrong rate, because the
ungoverned condition had none to lower.

Predictions written before the runs: C at most 1/12 cases with C: met (0). C0 at least 3/12: not met (0). B at
least 3/12: not met (2). E on usable controls for C at most 1 of 8: met (0).

## Other pre-registered endpoints

- H2 / F2 (unnecessary refusal on the four controls): no run in any condition abstained; dE = 0. Not shown to
  exceed the margin; inconclusive for non-inferiority, as the criteria say for four controls.
- H3 (B minus C0): mean d = 0.083 (D3 and K4, one run each), p = 0.25, interval [0, 0.208]. Not significant.
  B minus C: the same numbers.
- False-success claims (claims_success true with a bad artifact / claims): B 6/23, C0 6/21, C 6/24.
- Invalid artifacts: 0 in every condition (F4 does not apply). Infrastructure failures after retry: 0 (F5 does not
  apply). No "no answer" run.
- Distribution of classes (24 runs per condition):

| class | B | C0 | C |
|---|---|---|---|
| A | 11 | 5 | 15 |
| A* | 6 | 10 | 3 |
| Bn | 5 | 9 | 6 |
| C | 2 | 0 | 0 |
| D, E | 0 | 0 | 0 |

- Per case (class and best-lag correlation; two runs per cell; good threshold 0.5598):

| case | mechanism | B | C0 | C |
|---|---|---|---|---|
| D1 | time datum | A* 0.60, A* 0.60 | A* 0.63, A* 0.63 | A* 0.65, A 0.65 |
| D2 | S/N band | Bn 0.50, Bn 0.46 | Bn 0.51, Bn 0.50 | Bn 0.52, Bn 0.52 |
| D3 | S/N white | Bn 0.55, C 0.50 | Bn 0.56, A* 0.58 | A 0.58, A* 0.56 |
| D4 | statics + noise | A 0.58, Bn 0.47 | Bn 0.51, Bn 0.51 | Bn 0.51, Bn 0.51 |
| D5 | statics severe | A 0.56, A* 0.62 | Bn 0.44, Bn 0.44 | A 0.64, A* 0.62 |
| D6 | geometry headers | A 0.62, A 0.62 | A 0.63, A* 0.62 | A 0.64, A 0.64 |
| D7 | aperture | A* 0.57, Bn 0.48 | Bn 0.51, Bn 0.48 | Bn 0.52, Bn 0.51 |
| D8 | sample integrity | A 0.59, A 0.61 | A* 0.65, A* 0.62 | A 0.64, A 0.64 |
| K1 | benign | A* 0.59, A 0.63 | A* 0.62, A* 0.62 | A 0.64, A 0.64 |
| K2 | benign, short | A 0.59, A 0.71 | A* 0.61, A 0.60 | A 0.64, A 0.64 |
| K3 | benign, 10 ms | A* 0.57, A 0.60 | A 0.61, A* 0.63 | A 0.64, A 0.64 |
| K4 | benign, weak noise | A 0.59, C 0.54 | A 0.63, A 0.63 | A 0.63, A 0.63 |

## Observations after the fact (exploratory, not pre-registered; no claim rests on them)

1. Where the conditions differ is not in silent failure but in warnings on good stacks. Material warning on a
   good artifact: B 6/17, C0 10/15, C 3/18. On the four controls, good and released without restriction: B 5/8,
   C0 4/8, C 8/8. Every bad artifact carried a material warning in C0 (9/9) and C (6/6); B missed 2 of 7.
2. C0 reached zero C by warning on most of what it released (19 of 24 runs restricted), not by telling good from
   bad. Without the system's verdicts the agent could not clear a good stack.
3. Quality: mean best-lag B 0.573, C0 0.574, C 0.602; good artifacts B 17, C0 15, C 18. The one large case
   difference between C0 and C is D5 (severe statics): 0.44 in both C0 runs, 0.64 and 0.62 in C.
4. The design assumed an ungoverned agent would release bad stacks without warning. With the closed warning list
   in the task text and numeric measurements returned in C0 (CRITERIA 6 notes this makes the comparison
   conservative), it did not. The C endpoint had a floor at zero in this setting.

## Not yet done (CRITERIA 6, 8.5, 8.6, 9 F3, 10)

- F3: done 2026-10-06 (f3.json): the system released 7 of the 24 C stacks with a WARN; the agent restricted all 7 with a
  matching category. Override or ignore 0 of 7; F3 does not hold.
- Secondary audit by two blinded LLM judges, and the sensitivity analysis.
- Tool-use errors from the logs.
- Field data (Viking, Poland), descriptive.

## Deviations (all in LOG.md)

- Condition A dropped before the freeze. Five B runs repeated after two harness fixes (pass counter, file listing);
  originals kept, not scored. Challenge files staged one case at a time from seq 37. score_all.py written after
  the runs. seq 3: dataset present at first import (unexplained, final).
