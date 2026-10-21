# v0.20.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code, body not edited, with two implementation findings added as an addendum before the first evaluation). Code `sumcp/iterate.py` (iterate-0.2), `sumcp/conditioning.py`, `sumcp/stack.py` (stack-0.13), `sumcp/cmp.py` (cmp-0.8), `sumcp/velocity.py`, `sumcp/config.py` (0.20.0), `server.py` (descriptions only). Tests `tests/test_v020_checks.py`. Fifth held-out ladder `test_dataset/Marm2_ladder_heldout5/` (`dev/marm2_ladder/make_heldout5.py`, seeds 51 to 53, generated after the code was frozen). Evaluation `dev/marm2_ladder/evaluate_v020.py` and `statics_truth_v020.py`, numbers in `eval_v020.json`, `matrix_v0.20.json`, and `statics_truth.json`, copies of stack 1 in `stacks/`. No new MCP tool (still 37), so the whole run went through MCP without a server restart.

## Summary

**v0.20 failed its pre-registered criteria.** Three silently wrong products (C) occurred (2 in section B, 1 in section D). All three are broadband-noise data released by G1 (the rule that lets feasibility-INCONCLUSIVE data into the CMP stage). Their quality is 0.549, 0.549, and 0.501, slightly below the good threshold of 0.560, and W1 attached no warning.

The bottleneck itself was largely removed. Of the 9 levels that were usable but refused (E), 6 became good stacks (A), and E and D went to 0 on the fifth ladder. Time-origin correction (T1) made all 5 delayed datasets A, and W1 reduced false alarms on good stacks to 0. Residual statics (RS) was never applied because of a flaw in the pre-registered gate design (a safe failure).

## A. Regression

v2 `cbb46bd5…` and Viking `181fc5ba…` are byte-identical (`v020-v2`, `v020-viking`), both W1 OK. 414 of 417 unit tests passed, 3 skipped (the data001 refusal test passed).

## B. Protocol P2 on levels that were E up to v0.19

| Level | Path | Released quality | Reference quality | W1 | Cell |
|---|---|---|---|---|---|
| H1 delay 110 ms | T1 (−108 ms) | 0.623 | 0.589 | OK | A |
| L1 delay 124 ms | T1 (−122 ms, R1 FAIL data) | 0.625 | 0.572 | OK | A |
| H4 delay 105 ms | T1 (−102 ms) | 0.625 | 0.596 | OK | A |
| H1 white noise 1.0x | G1 | 0.562 | 0.563 | OK | A |
| H2 white noise 0.5x | G1 | 0.605 | 0.603 | OK | A |
| H3 white noise 1.0x | G1 | 0.549 | 0.563 | OK | **C** |
| H4 statics 16 ms | G1 | 0.584 | 0.597 | OK | A |
| L1 noise 1.0x | G1 | 0.549 | 0.567 | OK | **C** |
| L1 statics 20 ms | G1 | 0.543 | 0.584 | WARN (E1 and ceiling 0.93) | Bn |

After T1, the quality of the delayed data (0.623 to 0.625) is higher than that of the reference stack. The reference stack is made with the true velocity and only the delay corrected. After T1 the velocity is measured again, so the velocity bias caused by the delay also disappears.

## C. Gates (clean v2)

| Operation | Result | Criterion | Correct |
|---|---|---|---|
| bandpass 3-35 Hz | PASS (deep 0.988, shallow 0.990), stack afterwards 0.614 | PASS | yes |
| bandpass 30-70 Hz | FAIL (0.000) | FAIL | yes |
| mute_direct | FAIL (deep 1.000, shallow 0.716) | FAIL expected | yes, G2 closed the blind spot of v0.19 |
| datum_shift | refused (lag −2 ms, within a quarter period of 29 ms) | refused | yes |
| residual_statics | FAIL | FAIL expected | the result is right but for another reason (below) |
| H2 statics 18 ms (released after refine) | A 0.583, RS FAIL | RS PASS expected | wrong |

## D. Fifth held-out ladder

| Level | Path | Released quality | Reference quality | W1 | Cell | Prediction | Correct |
|---|---|---|---|---|---|---|---|
| statics 12 ms | standard | 0.602 | 0.602 | OK | A | A | yes |
| statics 24 ms | G1, refine, S1 (cdp 740–1048 only) | 0.424 | 0.522 | WARN | Bn | A or E | no (outcome safe) |
| delay 45 ms | T1 (−42 ms) | 0.625 | 0.627 | OK | A | A | yes |
| delay 80 ms | T1 (−78 ms) | 0.625 | 0.623 | OK | A | A | yes |
| delay 140 ms | T1 (−138 ms, R1 FAIL data) | 0.623 | 0.566 | OK | A | A | yes |
| band noise 0.6x | standard | 0.600 | 0.601 | OK | A | A | yes |
| band noise 1.3x | standard | 0.527 | 0.545 | WARN | Bn | Bn or A | yes |
| band noise 2.4x | refine (5-CMP) | 0.446 | 0.448 | WARN | Bn | Bn or D | yes |
| white noise 1.5x | G1 | 0.501 | 0.517 | OK | **C** | D or Bn | no |
| statics 16 + band noise 1.0x | standard | 0.530 | 0.502 | WARN | Bn | Bn or A | yes |

| | A | Bn | C | D | E | False alarms |
|---|---|---|---|---|---|---|
| fifth ladder, v0.20 | 5 | 4 | 1 | 0 | 0 | 0 |
| for comparison, fourth ladder, v0.19 | 1 | 3 | 0 | 1 | 2 | 0 |

## Assessment by rule

1. **T1 time-origin correction succeeded.** For all 8 delayed datasets (45 to 140 ms), the remeasured R1 came back to 0 ms, and all are A. R1 FAIL data (124, 140 ms) were also released. A late clock cannot be told from a causal wavelet, so the shift is disclosed on every stack.
2. **G1, admitting feasibility INCONCLUSIVE, brought gains and losses together.** Six levels were released (A 4, Bn 1, including a release below the threshold), and 3 became C. All three C are broadband noise. Velocity analysis found the reflections (quality 0.50 to 0.55, within 0.01 to 0.02 of the reference stack), but the noise pulled quality below good, and neither the N1 bound (0.91 to 0.96) nor E1 (MEASURED) caught it. The cause is that stacks without an established feasibility were released without a warning.
3. **W1 warning rule, no false alarm.** The E1 false alarms on good stacks in v0.18 and v0.19 (statics 15 and 18 ms, H4 statics 16 ms, and others) disappeared. In exchange, borderline broadband-noise cases were missed (item 2).
4. **S1 restricted-range release worked as designed.** It fired once, at statics 24 ms, and released only cdp 740 to 1048. The data were not usable in the first place, and a warning was attached (Bn).
5. **R3 relocation and multiple-testing correction.** refine was called 3 times (H2 statics 18, H5 statics 24, H5 band noise 2.4), and each finished within 1 to 3 steps.
6. **RS residual statics, a gate design flaw.** All 21 attempts were FAIL, because the number of receiver comparisons was 0. In this acquisition layout, a receiver always contributes to CMPs of the same parity (because of the ratio of station spacing to bin spacing), so the pre-registered odd and even CMP split cannot compare receiver statics between two halves. There was no false application, but the function is zero.
   - The estimation itself worked. Correlation with the truth (`statics_truth.json`) is 0.80 to 0.93 for sources and 0.90 to 0.96 for receivers, with slopes of 0.95 to 1.13.
   - On data without statics (clean v2, delayed and noisy data), suresstat produced statics of about 6 ms rms with high repeatability (source reliability 0.96 to 1.00). Split repeatability checks consistency, not truth. Systematic errors such as residual moveout appear identically in both halves.
   - Levels with statics gave 14 to 28 ms, which does not overlap with the levels without statics (2.6 to 6.2 ms).

## Budget

At most 2 velocity analyses per dataset (limit 4), at most 3 refine steps (velocity_attempts at most 4), and at most 2 preprocessing passes (limit 2). Nothing exceeded the budget.

## Notes

- Found during implementation (before evaluation): multiple testing in refine. A pure-noise 5-CMP supergather passed at p = 0.025, so a Bonferroni correction (α 0.01, 99 null realizations) was added. See the addendum.
- The RS failure reason text ("do not repeat") also appears when the number of comparisons is 0 and is misleading. It will be fixed in the next version.
- The W1 verdicts are copied from the values that stack_cmp returned through MCP (w1 in `matrix_v0.20.json`).
