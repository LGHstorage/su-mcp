# v0.18.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code change, not edited). Code `sumcp/stack.py` (stack-0.11), `sumcp/config.py` (0.18.0), tests `tests/test_v018_checks.py`. Third held-out ladder `test_dataset/Marm2_ladder_heldout3/` (`dev/marm2_ladder/make_heldout3.py`), results in `results/marm2_ladder_heldout3/`.

## Summary

Silently wrong products (C) fell to 0 on the third held-out ladder (target met). However, the new warning (E1) is often attached to good stacks. On the third ladder both good stacks carried it, and over all good stacks with a known answer, 3 of 4 had a false alarm (only the v2 baseline had no warning). Wrong products are no longer released silently, but the warning switches on too easily and loses its value.

## Results by rule

**E1 (disclosure of velocity support depth).** If the measured velocity covers less than half of the reflection window, the result is PARTIAL.

| Stack | Support fraction | E1 | Quality | Verdict |
|---|---|---|---|---|
| v2 baseline | 0.70 | MEASURED | 0.622 | normal |
| Viking | 0.98 | MEASURED | — | normal |
| held-out band noise 1.5x | 0.07 | PARTIAL | 0.514 | noise (B-warn), formerly C |
| held-out 2 band noise 2.0x | 0.07 | PARTIAL | 0.494 | noise (B-warn), formerly C |
| held-out 2 band noise 1.0x | 0.17 | PARTIAL | 0.574 | **false alarm** (as predicted) |
| held-out 3 band noise 0.5x | 0.499 | PARTIAL | 0.606 | **false alarm** (0.001 from the 0.5 boundary) |
| held-out 3 band noise 1.25x | 0.499 | PARTIAL | 0.544 | noise (B-warn) |
| held-out 3 statics 8 ms | 0.23 | PARTIAL | 0.616 | **false alarm** |
| held-out 3 delay 45 ms | 0.77 | MEASURED | 0.613 after undoing | normal (B, disclosed by D1) |

The support depth moves strongly even with weak noise or small statics (2.24 s to 1.68 to 2.0 s). Stacks whose quality is almost unchanged therefore drop to PARTIAL. The velocity support depth says well how far the velocity can be trusted, but it is too sensitive as a criterion for whether a section is usable.

**N1 window change (to the end of the record).** It is now measured on noisy data too. Band noise 2.0x is NOISE_LIMITED (bound 0.87), 1.5x is CLEAR at 0.913, 1.25x is 0.938, 1.0x is 0.958, and 0.5x is 0.989. It moves monotonically with the noise level and gives no false alarm, but N1 alone does not catch 1.5x. Noise-free data are all above 0.99.

## Regression

v2 `cbb46bd5…`, Viking `181fc5ba…`, and the three band-noise stacks are all byte-identical to earlier runs. 367 of 370 unit tests passed, 3 skipped.

## Third held-out ladder

| Level | Verdict | Quality | Cell | Prediction |
|---|---|---|---|---|
| band noise 0.5x | released, E1 PARTIAL (0.499) | 0.606 | A, false alarm | predicted A (no warning), wrong |
| band noise 1.25x | released, E1 PARTIAL | 0.544 | B-warn | correct |
| band noise 1.75x | velocity FAIL (3/5) | — | D | one of the options, correct |
| band noise 2.25x | velocity FAIL (3/5) | — | D | correct |
| delay 45 ms | released, +42 ms DISPLACED | 0.395 (0.613 after undoing) | B | correct |
| statics 8 ms | released, E1 PARTIAL (0.23) | 0.616 | A, false alarm | predicted A (no warning), wrong |
| white noise 1.0x | feasibility INCONCLUSIVE | — | E | correct |

| | A | B | B-warn | C | D | E | False alarms |
|---|---|---|---|---|---|---|---|
| v0.15 (derived) | 2 | 0 | 0 | 2 | 2 | 1 | — |
| v0.17 (derived, no E1) | 2 | 1 | 0 | 1 | 2 | 1 | 0 |
| v0.18 | 2 | 1 | 1 | 0 | 2 | 1 | 2 |

## Assessment

- C = 0 was reached, but the false-alarm rate of E1 (3 of 4 good stacks with a known answer) is high. The E1 warning in its present form should be read only as possibly wrong and must not be used to judge quality. The number itself (support fraction) is worth reporting.
- The 0.5 threshold is not moved after seeing the results. Moving it requires writing the criteria first and testing on a new ladder.
- A good candidate is to look at N1 and E1 together, for example warning only when the N1 bound is below 0.95 and E1 is PARTIAL. On these data that gives the right answers, but the rule was made after seeing these results and must be tested on the next held-out ladder.
