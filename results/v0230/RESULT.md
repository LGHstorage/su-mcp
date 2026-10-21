# v0.23.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-28. Criteria in `CRITERIA.md` (written before the code, no edits or addenda). Code `sumcp/stack.py` (stack-0.16), `sumcp/provenance.py`, `sumcp/config.py` (0.23.0), `server.py` (descriptions only). Tests `tests/test_v023_checks.py` (6), and two v0.21/v0.22 tests updated to the new grade names. Eighth held-out ladder `test_dataset/Marm2_ladder_heldout8/` (`make_heldout8.py`, seeds 81 to 83, generated after the code was deployed). Evaluation `dev/marm2_ladder/evaluate_v023.py` and `matrix_v023.py`, numbers in `eval_v023.json` and `matrix_v0.23.json`. No new MCP tool (37), no server restart. Two operators ran P5 in parallel, with no infrastructure error or retry (after the log-locking retry L1).

## Summary

**v0.23 failed its pre-registered criteria, because of false alarms.** At the 8 held-out levels there was no silently wrong stack (C), and no new below-threshold release with only a caution and no warning (Bc). However, 4 good stacks carried a quality warning (N2), above the limit of at most 2 A*. All four had bounds of 0.933 to 0.949, just below the 0.95 threshold.

The safety side worked as expected. New data in the same range as the C of v0.22 (band noise 1.6x, bound 0.912), namely band 2.0x (0.881) and white 1.5x (0.919), were all warned. Good stacks on the G1 path now carry only a provenance caution and not a quality warning.

## A. Regression

Viking `181fc5ba…`, v2 cdp_list-5 `cbb46bd5…`, and v2 default `7374cb63…` are all byte-identical, reliability OK. Quality of the v2 default is 0.640. 440 of 443 unit tests passed, 3 skipped (cloud SU).

## B. Retrospective application (descriptive, v0.23 rules applied to the recorded bounds, E2, and feasibility)

| Set | A | A~ | A* | Bn | Bc | C |
|---|---|---|---|---|---|---|
| 26 released stacks of v0.22 | 8 | 14 | 1 | 3 | 0 | 0 |
| 18 released stacks of v0.21 | 3 | 6 | 1 | 4 | 4 | 0 |

In v0.22 (dense analysis) there was 1 quality-warning false alarm (white 1.2x, bound 0.944), and the 15 W2 false alarms moved to cautions. Applied to v0.21 (sparse analysis), 4 Bc appear (H3 white 1.0, L1 noise 1.0, H6 statics 28, H6 statics 14 + white 0.8, with quality 0.549 to 0.558 and bounds of 0.95 or more). **The relation that a high bound means good quality held only after dense velocity analysis.** After sparse analysis, velocity error lowers quality independently of the bound. The measured fraction in the v0.21 records is a minimum, so the W3 verdict there is approximate.

## C. Eighth held-out ladder

| Level | Path | Stack 1 | Released quality | Reference | Bound | Reliability | Cell | Prediction | Correct |
|---|---|---|---|---|---|---|---|---|---|
| band noise 1.2x | standard | 0.576 | 0.576 | 0.562 | 0.949 | WARN (N2) | A* | A or Bn | no (false alarm) |
| band noise 1.4x | standard | 0.560 | 0.560 | 0.543 | 0.933 | WARN (N2) | A* | Bn | no (false alarm, borderline) |
| band noise 2.0x | standard | 0.510 | 0.510 | 0.501 | 0.881 | WARN (N2) | Bn | Bn | yes |
| white noise 1.3x | G1 | 0.569 | 0.569 | 0.539 | 0.938 | WARN (N2) and caution | A* | Bn or Bc | no (false alarm) |
| white noise 1.5x | G1 | 0.550 | 0.550 | 0.522 | 0.919 | WARN (N2) and caution | Bn | Bn | yes |
| statics 20 + band 1.2x | G1, RS2 PASS | 0.463 | 0.573 | 0.470 | 0.945 | WARN (N2) and caution | A* | A~ or Bn | no (false alarm) |
| statics 18 + white 1.0x | G1, RS2 PASS | 0.501 | 0.588 | 0.482 | 0.957 | caution | A~ | A~ or Bn | yes |
| delay 120 + band 0.8x | T1 (−118 ms) | 0.632 | 0.632 | 0.536 | 0.976 | OK | A | A or Bn | yes |

Totals A 1, A~ 1, A* 4, Bn 2, Bc 0, C 0. No refine, no budget overrun.

## Interpretation

1. **After dense analysis, the bound that separates quality lies near 0.92 to 0.93.** Of the 34 released stacks of v0.22 and v0.23, the 5 bad ones had bounds of 0.881 to 0.919, and the 29 good ones 0.933 or more. 0.95 is safe but conservative. This boundary was also found after seeing the results, so moving the threshold needs a new held-out ladder.
2. **The bound measures only the noise loss.** Quality is roughly the clean quality times the bound times the remaining losses. The remaining losses (velocity and statics residuals) are 0.93 to 0.99 after dense analysis and larger after sparse analysis. Rather than keep adjusting the threshold, a predictive rule that measures velocity uncertainty separately and multiplies the two terms is the principled choice (next candidate).
3. **Delay 120 ms + band noise was much better than its reference stack (0.632 against 0.536),** because the velocity was measured again after T1 restored the time axis.
4. **Display rounding.** A bound of 0.949 was printed as "0.95 < 0.95". The verdict is right and only the text is wrong (three decimals in the next version).
