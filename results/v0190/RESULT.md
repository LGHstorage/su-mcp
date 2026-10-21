# v0.19.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code, not edited). Code `sumcp/iterate.py` (iterate-0.1, new), `sumcp/conditioning.py` (new), `sumcp/stack.py` (stack-0.12), `sumcp/tools.py`, `server.py`, `sumcp/config.py` (0.19.0), tests `tests/test_v019_checks.py`. Fourth held-out ladder `test_dataset/Marm2_ladder_heldout4/` (`dev/marm2_ladder/make_heldout4.py`, seeds 41 to 43, generated after the code was frozen). Evaluation `dev/marm2_ladder/evaluate_v019.py`, numbers in `eval_B.json`, `eval_C.json`, `eval_D.json`.

## Summary

None of the failure conditions of v0.19 (a new C, an attempt beyond budget, a byte change in a regression stack) occurred. Velocity re-analysis (refine_velocity) turned 6 of the 9 previously blocked levels into releases. Two of them (statics) are good stacks against the truth (E to A), and 4 (band noise) are data that were not usable in the first place, released with noise and velocity warnings (Bn). Data with a shifted time origin were refused even after all three steps. The preprocessing QC gate separated an in-band filter from an out-of-band filter correctly, but the limits of the gate design showed for direct-wave muting and deconvolution.

## A. Regression

v2 `cbb46bd5…` and Viking `181fc5ba…` are both byte-identical to v0.18 (`v019-v2`, `v019-viking`). No change in the pick_velocity output. 385 of 388 unit tests passed, 3 skipped (cloud build).

## B. Protocol P on levels previously refused at the velocity step

| Level | Cause of the first pick failure | refine result | Attempts | Released quality | Reference quality | Cell |
|---|---|---|---|---|---|---|
| H1 statics 15 ms | edge pick at 0.04 s at cdp 1048 (coverage 75%) | 5-CMP supergather failed, shift by 1 CMP (1047) passed | 3 | 0.590 | 0.602 | A (E1 PARTIAL false alarm) |
| H2 statics 18 ms | cdp 1048 supported to 1.20 s | 5-CMP supergather passed | 2 | 0.583 | 0.602 | A (E1 PARTIAL false alarm) |
| H1 band noise 3.0x | cdp 1048 supported to 1.24 s | 5-CMP supergather passed | 2 | 0.428 | 0.426 | Bn (N1 and E1) |
| H2 band noise 2.5x | cdp 945/1048 supported to 0.72/1.28 s | 5-CMP supergather passed | 2 | 0.480 | 0.472 | Bn (N1 and E1) |
| H3 band noise 1.75x | cdp 945/1048 | 5-CMP supergather passed | 2 | 0.513 | 0.509 | Bn (N1 and E1) |
| H3 band noise 2.25x | cdp 945/1048 | 5-CMP supergather passed | 2 | 0.471 | 0.474 | Bn (N1 and E1) |
| H1 delay 110 ms | edge picks at 0.32 s at all 5 locations | all three steps failed | 4 | refused | 0.589 | E (as predicted) |
| L1 delay 124 ms | R1 FAIL | re-analysis itself refused | 1 | refused | — | as predicted |
| L1 delay 150 ms | R1 FAIL | re-analysis itself refused | 1 | refused | — | as predicted |

Most refusals came from one analysis location at the right end of the line (cdp 1048). If a middle location drops out, interpolation covers it. If an end location drops out, the part beyond it becomes extrapolation and fails the 80% coverage rule. The released quality of the band-noise levels equals that of the reference stack made with the true velocity (within ±0.01), so the loss of quality comes from the noise in the data and not from the velocity.

For H1 statics 15 ms, the cdp 1046 to 1050 supergather failed and the neighboring 1045 to 1049 supergather passed. This is a marginal pass, and the 3 attempts are recorded with the stack.

## C. Preprocessing QC (clean v2)

| Operation | Preservation (median) | Verdict | Stack quality afterwards | Against the criteria |
|---|---|---|---|---|
| bandpass 3-5-25-35 Hz | 0.988 | PASS (required PASS) | 0.614 | correct, good stack kept |
| bandpass 30-35-60-70 Hz | 0.0001 | FAIL (required FAIL) | not used | correct |
| mute_direct (extra 0.1 s) | 1.000 | PASS (required PASS) | 0.581 | correct, but see the limit below |
| predictive_decon (gap 24 ms, 0.2 s) | 0.583 | FAIL | not used | report only |
| dip_filter (removes ≤1600 m/s) | 0.997 | PASS | 0.624 | report only |

The v2 reference stack is 0.622.

## D. Fourth held-out ladder

| Level | Result | Released quality | Reference quality | Cell | Prediction | Correct |
|---|---|---|---|---|---|---|
| band noise 0.3x | first pick passed, no warning | 0.609 | 0.620 | A | A | yes |
| band noise 1.6x | first pick passed, E1 PARTIAL (0.30), N1 CLEAR (bound 0.903) | 0.505 | 0.519 | Bn | B-warn or A | yes |
| band noise 2.2x | first pick passed (predicted FAIL), N1 and E1 warnings | 0.471 | 0.479 | Bn | warning if released | warning correct, velocity FAIL prediction wrong |
| band noise 2.8x | first pick passed (predicted FAIL), N1 and E1 warnings | 0.425 | 0.435 | Bn | D | wrong (outcome safe) |
| statics 16 ms | feasibility INCONCLUSIVE (F1) | refused | 0.597 | E | A | wrong |
| statics 22 ms | feasibility INCONCLUSIVE (F1) | refused | 0.557 | D | E | wrong (0.003 from the 0.560 threshold) |
| delay 105 ms | 3/5 failed, refine 3 steps, 2 locations recovered, cdp 1048 failed (coverage 75%) | refused | 0.596 | E | E | yes |

| | A | B | Bn | C | D | E | False alarms |
|---|---|---|---|---|---|---|---|
| fourth ladder, v0.19 | 1 | 0 | 3 | 0 | 1 | 2 | 0 |

## Budget

In the 9 refine_velocity calls, the number of velocity analyses was 2 per dataset in every case (limit 4), and attempts reached at most 3 steps (velocity_attempts at most 4, limit 1 + 3). Preprocessing was at most 2 per dataset (limit 2). No attempt exceeded the budget.

## Assessment

1. **Re-analysis released usable data that had been blocked.** In B, 2 E became A. The 2 E of D (statics 16 ms, delay 105 ms) were not released. One was blocked before the velocity step (feasibility), and one at an end location.
2. **The largest bottleneck is that one end location can block everything.** Almost every refusal came from cdp 1048. The 5 analysis locations are about 1 km apart, sparser than common practice. More locations, or a rule that cuts the end section and releases only the measured part, are the next candidates.
3. **On delayed data, supergather analysis removed some edge picks.** At delay 105 ms, cdp 740 and 843 passed with a 5-CMP supergather. This time the data were refused because of the end location, but with more locations they could be released with a biased velocity. If released, D1 discloses DISPLACED, so the outcome is B, but this must be tested together with any change to the location rule.
4. **The preservation gate checks only whether the signal survives.** Therefore
   - for direct-wave muting, the injected reflections all lie below the last direct arrival, so the result is always 1.0. The gate did not see the effect of the mute removing shallow far-offset reflections (stack 0.622 to 0.581).
   - for deconvolution, whose purpose is to change the wavelet, the correlation with the injected Ricker drops and the result is FAIL (0.58). The gate cannot tell improvement from damage.
   Both limits come from applying the gate as written in the criteria document, and the rule was not changed.
5. **The N1 threshold (0.9) missed band noise 1.6x (bound 0.903).** E1 caught it.
6. Band noise 2.2x and 2.8x passed at the first pick, unlike similar levels on the third ladder (1.75x, 2.25x). Whether velocity fails is not monotonic in the noise level and depends on the noise realization (seed).

## Notes

- The criteria document says 32 to 35 tools. In fact the MCP tools went from 34 to 37 (including the job tools). The criteria document was not changed.
- The draft code used an injection amplitude of 0.2 × RMS. It was set to the 0.5 × RMS of the criteria document before the runs.
- The reference quality of delay levels was judged on the delay-corrected value (R1 lag or the actual delay). The first run of the evaluation script read the uncorrected value (0.128) by mistake. This was fixed and recomputed. The cells use the corrected values.
- condition_gathers refuses data that still carry header statics (sstat/gstat) (a v0.19 limit).
