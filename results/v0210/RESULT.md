# v0.21.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code, not edited). Code `sumcp/iterate.py` (iterate-0.3), `sumcp/conditioning.py`, `sumcp/stack.py` (stack-0.14), `sumcp/config.py` (0.21.0), `server.py` (descriptions only). Tests `tests/test_v021_checks.py`. Sixth held-out ladder `test_dataset/Marm2_ladder_heldout6/` (`dev/marm2_ladder/make_heldout6.py`, seeds 61 to 63, generated after the code was frozen). Evaluation `dev/marm2_ladder/evaluate_v021.py`, `statics_truth_v021.py`, and `matrix_v021.py`, numbers in `eval_v021.json`, `matrix_v0.21.json`, and `statics_truth.json`, copies of stack 1 in `stacks/`. No new MCP tool (still 37), so the whole run (21 datasets) went through MCP without a server restart.

## Summary

**v0.21 met none of the failure conditions of its pre-registered criteria.** No C in sections C and D, byte-identical regression, no budget overrun, no RS2 application on data without statics, and no case where RS2 lowered quality. All 9 predictions for the sixth ladder were correct.

**One new C occurred in the descriptive section (B).** At H5 statics 16 ms + band noise 1.0x, RS2 raised the stack from 0.530 to 0.548 and the half-stack bound from 0.891 to 0.959, so the W1 warning disappeared, while the quality stayed below good (0.560). It does not meet the wording of the failure condition ("C in sections C and D"), but it is a silently wrong product and is reported as such. At this level even the reference stack made with the true velocity is 0.502, so the data cannot reach good in the first place.

**Residual statics worked for the first time.** RS2 passed at all 10 levels with statics, and every stack improved (+0.018 to +0.137). At all 9 levels without statics it was refused (4 not significant, 5 with a solution of 0 or 0.2 ms).

## A. Regression

v2 `cbb46bd5…` and Viking `181fc5ba…` are byte-identical (`v021-v2`, `v021-viking`), both W1 and W2 OK. 419 of 422 unit tests passed, 3 skipped (run in the cloud with SU attached, including the data001 refusal test).

## B. RS2 (levels with known statics, descriptive)

| Level | Feasibility | Stack 1 | RS2 (estimated rms / true rms, reliability s/r) | Stack 2 | Reference | Reliability | Cell |
|---|---|---|---|---|---|---|---|
| H2 statics 18 | PASS | 0.583 (A) | PASS 21.0 / 18.1 ms, 0.995/0.993 | 0.631 | 0.602 | OK | A |
| H4 statics 16 | G1 | 0.584 (A*) | PASS 19.0 / 15.9, 0.997/0.993 | 0.605 (refine) | 0.597 | WARN (W2) | A* |
| L1 statics 20 | G1 | 0.543 (Bn) | PASS 23.3 / 20.2, 0.998/0.992 | 0.601 | 0.584 | WARN (W2) | A* |
| H5 statics 12 | PASS | 0.602 (A) | PASS 13.9 / 11.9, 0.996/0.987 | 0.633 | 0.602 | OK | A |
| H5 statics 24 | G1 | 0.424 (Bn, cdp 740–1048) | PASS 27.6 / 23.9, 0.996/0.987 | 0.561 (refine, full range) | 0.522 | WARN (W2) | A* |
| H5 statics 16 + band 1.0 | PASS | 0.530 (Bn) | PASS 18.2 / 15.9, 0.997/0.988 | 0.548 | 0.502 | OK | **C** |
| clean v2 (`v021-cl`) | PASS | 0.622 | FAIL significance, 6.0 ms < 8.4 ms | — | — | OK | A |

A* is a good stack with a warning (false alarm). The expectation of the criteria (RS2 PASS, stack 2 ≥ stack 1 − 0.01, more than half improve) is met in all 6. Stack 2 is higher than the reference stack because the reference stack is made with the true velocity but keeps the statics.

The correlation between estimated and true statics is 0.80 to 0.93 for sources and 0.90 to 0.96 for receivers (the same as in v0.20). The estimated rms is 2 to 4 ms larger than the true one. This agrees with the repeatable spurious component of about 6 ms on clean data being added in quadrature (√(18² + 6²) ≈ 19).

How the C arose. Stack 1 was WARN because of N1 NOISE_LIMITED (correlation 0.659, bound 0.891) and E1 PARTIAL. Correcting the statics raised the half-stack correlation to 0.851 and the bound to 0.959, outside the W1 condition (bound < 0.95). E1 is still PARTIAL (6% of the reflection window measured), but W1 warns only together with the bound. Feasibility is PASS, so there is no W2 either.

## C. W2 (the three C of v0.20)

| Level | Released quality | Reference | RS2 | Reliability | Cell |
|---|---|---|---|---|---|
| H3 white noise 1.0x | 0.549 | 0.563 | FAIL (all solutions 0) | WARN (W2) | Bn |
| L1 noise 1.0x | 0.549 | 0.567 | FAIL (significance 5.6 ms, receiver reliability 0.85) | WARN (W2) | Bn |
| H5 white noise 1.5x | 0.501 | 0.517 | FAIL (all solutions 0) | WARN (W2) | Bn |

All three went from C to Bn. Criterion met.

## D. Sixth held-out ladder

| Level | Path | Stack 1 | Released quality | Reference | Reliability | Cell | Prediction | Correct |
|---|---|---|---|---|---|---|---|---|
| statics 10 ms | G1, RS2 PASS (12.2 / 10.0 ms) | 0.594 | 0.613 | 0.616 | WARN (W2) | A* | A, RS2 PASS or significance FAIL | yes |
| statics 18 ms | G1, RS2 PASS (20.1 / 18.0) | 0.586 | 0.617 | 0.586 | WARN (W2) | A* | A after RS2 | yes |
| statics 28 ms | G1, RS2 PASS (30.3 / 28.0), refine, S1 cdp 753–1048 | 0.469 | 0.550 | 0.499 | WARN (W2) | Bn | G1, RS2 PASS, A or Bn | yes |
| white noise 0.7x | G1, RS2 FAIL | 0.593 | 0.593 | 0.594 | WARN (W2) | A* | A false alarm or Bn | yes |
| white noise 1.2x | G1, RS2 FAIL | 0.532 | 0.532 | 0.549 | WARN (W2) | Bn | Bn | yes |
| white noise 1.7x | G1, RS2 FAIL | 0.489 | 0.489 | 0.504 | WARN (W1 and W2) | Bn | Bn or D | yes |
| band noise 1.0x | standard, RS2 FAIL (significance 4.3 ms) | 0.560 | 0.560 | 0.567 | OK | A | A or Bn | yes (borderline, 0.5600 against 0.5598) |
| delay 60 ms | T1 (−58 ms), RS2 FAIL (significance 6.1 ms) | 0.625 | 0.625 | 0.623 | OK | A | A | yes |
| statics 14 + white 0.8x | G1, RS2 PASS (13.5 / 14.0) | 0.533 | 0.558 | 0.546 | WARN (W2) | Bn | Bn or A | yes |

Totals A 2, A* 3, Bn 4, C 0, D 0, E 0. Budget, at most 4 velocity analyses (H5 statics 24, within the limit) and at most 2 preprocessing passes.

## Interpretation

1. **RS2 worked as designed.** With random CMP halves, receiver comparison became possible (329 stations). At levels with statics the reliability was 0.97 to 0.998, and at levels without statics the solution was not significant or zero. The 8.4 ms significance line blocked the spurious statics of clean data (about 6 ms) and let the 10 ms level pass.
2. **Why the suresstat solution is exactly zero on white-noise data is not yet known.** The refusal is right, but the mechanism was not confirmed. At statics 14 ms + white noise 0.8x the estimation was normal (correlation 0.83/0.87).
3. **The cost of W2 is false alarms.** Six good stacks (3 in B, 3 in D) carried the feasibility warning. The warning text states that the only evidence for reflections is the velocity analysis, which is not untrue, but read as a quality warning it is excessive.
4. **The new C arises because the warning rule looks only at the state after the statics correction.** The correction raises the agreement of the half-stacks, but the band noise and the poor velocity support (6%) remain. Next candidate (needs pre-registration and a test on a new held-out ladder, because it was made after seeing these results): warn regardless of the bound when the E1 measured fraction is very low (for example below 25%). On these data it would add a warning to band noise 1.0x (0.199, quality at the 0.560 boundary).
5. **State of the bottleneck.** E and D are 0 on the sixth ladder. Refusals have disappeared, and the weight of the judgment has moved to release with a warning.
