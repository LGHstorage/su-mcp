# v0.22.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-28. Criteria in `CRITERIA.md` (written before the code, with one addendum before the first run that rounds the K2 limit up to whole bins). Code `sumcp/stack.py` (stack-0.15), `sumcp/config.py` (0.22.0), `server.py` (descriptions only). Tests `tests/test_v022_checks.py` (15). Seventh held-out ladder `test_dataset/Marm2_ladder_heldout7/` (`dev/marm2_ladder/make_heldout7.py`, seeds 71 to 73, generated after the code was frozen and deployed). Evaluation `dev/marm2_ladder/evaluate_v022.py` and `matrix_v022.py`, numbers in `eval_v022.json` and `matrix_v0.22.json`, copies of stack 1 in `stacks/`. No new MCP tool (37), so 29 datasets were run through MCP without a server restart (three operators ran P4 in parallel).

## Summary

**v0.22 failed its pre-registered criteria.** One silently wrong stack occurred on the held-out ladder (section C), band noise 1.6x, quality 0.549 (threshold 0.560), reliability OK. The prediction was Bn.

**The density of velocity analysis (D1) raised quality substantially.**
- Clean v2 went from 0.622 to 0.640.
- Rerunning the 18 levels of v0.21 increased the good stacks from 10 to 16, with no C. The C of v0.21 (H5 statics 16 + band 1.0) went from 0.548 to 0.602 (A).
- refine was needed for only 1 of 29 datasets (v0.21, 5 of 21).
- There were no refusals.

## A. Regression

| Item | Result | Criterion | Correct |
|---|---|---|---|
| Viking default path (D1, 5 locations) | `181fc5ba…` | byte-identical | yes |
| v2, cdp_list with 5 locations | `cbb46bd5…` | byte-identical | yes |
| v2 default path (9 locations, all valid) | 0.640, OK | ≥ 0.612, OK | yes |
| Unit tests | 434 of 437 passed, 3 skipped (cloud SU) | pass | yes |

RS2 on the v2 default path was refused as not significant (3.0 ms).

## B. The 18 levels of the v0.21 ladders (descriptive)

| Level | v0.21 final | v0.22 stack 1 | v0.22 final | Reference | RS2 | Cell |
|---|---|---|---|---|---|---|
| H2 statics 18 | 0.631 A | 0.620 | 0.629 | 0.602 | PASS | A |
| H4 statics 16 | 0.605 A* | 0.607 | 0.632 | 0.597 | PASS | A* |
| L1 statics 20 | 0.601 A* | 0.565 | 0.631 | 0.584 | PASS | A* |
| H5 statics 12 | 0.633 A | 0.637 | 0.659 | 0.602 | PASS | A |
| H5 statics 24 | 0.561 A* | 0.501 (refine) | 0.661 | 0.522 | PASS | A* |
| H5 statics 16 + band 1.0 | 0.548 **C** | 0.548 | 0.602 | 0.502 | PASS | A |
| H3 white 1.0 | 0.549 Bn | 0.583 | 0.583 | 0.563 | solution 0 | A* |
| L1 noise 1.0 | 0.549 Bn | 0.602 | 0.602 | 0.567 | not significant | A* |
| H5 white 1.5 | 0.501 Bn | 0.540 | 0.540 | 0.517 | solution 0 | Bn |
| H6 statics 10 | 0.613 A* | 0.631 | 0.640 | 0.616 | PASS | A* |
| H6 statics 18 | 0.617 A* | 0.622 | 0.637 | 0.586 | PASS | A* |
| H6 statics 28 | 0.550 Bn (scope) | 0.491 | 0.622 (full range) | 0.499 | PASS | A* |
| H6 white 0.7 | 0.593 A* | 0.615 | 0.615 | 0.594 | not significant | A* |
| H6 white 1.2 | 0.532 Bn | 0.567 | 0.567 | 0.549 | solution 0 | A* |
| H6 white 1.7 | 0.489 Bn | 0.531 | 0.531 | 0.504 | solution 0 | Bn |
| H6 band 1.0 | 0.560 A | 0.590 | 0.590 | 0.567 | not significant | A |
| H6 delay 60 | 0.625 A | 0.640 (T1 −58 ms) | 0.640 | 0.623 | not significant | A |
| H6 statics 14 + white 0.8 | 0.558 Bn | 0.571 | 0.603 | 0.546 | PASS | A* |

Totals A 5, A* 11, Bn 2, C 0. 17 of 18 improved over v0.21 (+0.015 to +0.100), and only H2 statics 18 changed by −0.002. Expectation met. As for v2, most released stacks are higher than the reference stack (true velocity with the defect left in), because the measured velocity adapts to the defect.

## C. Seventh held-out ladder

| Level | Path | Stack 1 | Released quality | Reference | Reliability | Cell | Prediction | Correct |
|---|---|---|---|---|---|---|---|---|
| statics 16 + band 1.0 | G1, RS2 PASS | 0.527 | 0.579 | 0.523 | WARN (W2) | A* | Bn or A, not C | yes |
| band noise 0.8x | standard | 0.601 | 0.601 | 0.581 | OK | A | A or Bn | yes |
| band noise 1.6x | standard, 8/9 locations | 0.549 | 0.549 | 0.522 | OK | **C** | Bn | **no** |
| white noise 1.0x | G1 | 0.587 | 0.587 | 0.565 | WARN (W2) | A* | Bn | no (safe side) |
| statics 14 ms | G1, RS2 PASS | 0.621 | 0.645 | 0.605 | WARN (W2) | A* | A* | yes |
| delay 90 ms | T1 (−88 ms) | 0.640 | 0.640 | 0.612 | OK | A | A | yes |
| tail noise 2.0x (last quarter of shots) | standard, 9/9 | 0.602 | 0.602 | 0.569 | OK | A | A or Bn | yes |
| statics 12 + white 0.6x | G1, RS2 PASS | 0.598 | 0.625 | 0.579 | WARN (W2) | A* | A or A* | yes |

Totals A 3, A* 4, C 1. No budget overrun (at most 3 velocity analyses).

## Interpretation

1. **How the C arose.** For band noise 1.6x, the half-stack bound was 0.912, above the N1 threshold (0.9), and E2 was MEASURED at 0.58. W1 and W3 were therefore both silent. The quality of 0.549 is slightly below the clean quality times the bound (0.640 × 0.912 ≈ 0.58), and the difference is explained by other losses such as velocity error. To reach good (0.9 of clean), the bound has to be comfortably above 0.9, but N1 cuts at 0.9.
2. **After dense velocity analysis, the bound alone separated good from bad.** Of the 26 final stacks, the 3 bad ones had bounds of 0.897 to 0.916, and the 23 good ones 0.944 or more. This observation was made after seeing the results, so using it as a rule requires a test on a new held-out ladder.
3. **W2 false alarms grew.** 15 of the 23 good stacks were released with the feasibility warning. With better velocity analysis, most stacks on the G1 path became good. The reason W2 was introduced in v0.21 (3 G1 stacks were C) belongs to the time of sparse analysis.
4. **The zero solution of suresstat occurs only on data dominated by white noise** (all 5 are white-noise cases). With statics plus white noise the estimation is normal.
5. **One infrastructure error during the parallel run.** A PermissionError occurred while writing to `logs/processing.jsonl` concurrently (file locking on the Windows drive). A retry solved it, but it has to be prevented in the code.
