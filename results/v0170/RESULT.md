# v0.17.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code change, not edited). Code `sumcp/velocity.py` (velocity-0.9, R2b), `sumcp/stack.py` (stack-0.10, N1), `sumcp/config.py` (0.17.0), tests `tests/test_v017_checks.py`. Second held-out ladder `test_dataset/Marm2_ladder_heldout2/` (`dev/marm2_ladder/make_heldout2.py`), results in `results/marm2_ladder_heldout2/`.

## Summary

Neither rule did what it was meant to do. There is no regression. The second held-out ladder has 1 C (silently wrong), short of the target of 0. Because of D1 of v0.16, C is 1 instead of 2 under v0.15.

## Results by rule

**R2b (exemption of scan-boundary picks in the direct-wave zone).** It never fired. On its target, held-out statics 15, R1 was UNKNOWN (a 15 ms static makes the direct wave FRAGILE or ABSENT at 30 to 250 Hz). R2b was designed to exempt only when R1 measured the direct wave, so the condition did not hold on the data that needed it most. Statics 15 stays E. The prediction (A) was wrong. It did not fire at other levels either, so it had no effect on the results.

**N1 (half-stack S/N disclosure).** It worked on noise-free data. v2 r = 0.998, delay 20/70 r = 0.998, statics 12 r = 0.943, and Viking r = 0.952 (assuming 1492 m/s), all CLEAR with no false alarm. On noisy data the window collapsed. Its lower end was set at the shallowest depth where velocity was measured. With noise in the signal band, that depth shrinks to 1.48 to 1.60 s, and the window (from 1.40 s) becomes shorter than 0.2 s. Band noise 1.0x, 1.5x (rerun of held-out 1), and 2.0x were all UNKNOWN. This is a design flaw, since the measurement cannot be made on the data that need the warning.

What this failure shows. On noisy data, `supported_to_s` is already a warning sign. The released stacks at 1.5x and 2.0x stacked everything below 1.5 s of the 2.6 s record with an extrapolated velocity. This fact is in the velocity report but not in the stack result.

## Regression (MCP path)

| Data | Prediction | Result |
|---|---|---|
| v2 0–2.6 s | same stack, N1 uncertain | Correct. `cbb46bd5…` identical, N1 CLEAR (r 0.998) |
| Viking | same stack, N1 assumes 1492 m/s | Correct. `181fc5ba…` identical, N1 CLEAR (r 0.952, window 2.17–5.92 s) |
| held-out statics 15 | A through R2b | **Wrong.** R1 UNKNOWN, so R2b did not act, E kept |
| held-out delay 110 | refusal kept | Correct. The 0.32 s pick is separate from the direct wave and is not exempt |
| held-out band noise 1.5x | N1 verdict uncertain | N1 UNKNOWN (window 1.40–1.48 s). Stack byte-identical, C kept |

Unit tests. 363 of 366 passed, 3 skipped.

## Second held-out ladder

| Level | Verdict | Released stack | Reference stack | Cell | Prediction |
|---|---|---|---|---|---|
| delay 20 | all PASS, +18 ms WITHIN, N1 CLEAR | 0.629 | 0.630 | A | correct |
| delay 70 | all PASS, +68 ms DISPLACED | −0.085 (0.628 after undoing) | 0.626 | B | correct |
| band noise 1.0x | all PASS, N1 UNKNOWN | 0.574 | 0.576 | A | correct |
| band noise 2.0x | all PASS, N1 UNKNOWN | **0.494** | 0.510 | **C** | B-noise if warned, otherwise C |
| band noise 2.5x | velocity FAIL (3/5, 50%) | — | 0.472 | D | correct |
| white noise 0.5x | feasibility INCONCLUSIVE (direct wave ABSENT) | — | 0.603 | E | wrong (predicted PASS and A) |
| white noise 2.0x | feasibility INCONCLUSIVE | — | 0.479 | D | correct |
| statics 12 | all PASS, R1 UNKNOWN, N1 CLEAR | 0.620 | 0.619 | A | correct |
| statics 18 | feasibility PASS, velocity FAIL (cdp 1048 supported only to 1.20 s) | — | 0.602 | E | predicted uncertain. Caused by support depth, not a boundary pick |

| | A | B | B-noise | C | D | E | False claims | False alarms |
|---|---|---|---|---|---|---|---|---|
| held-out 2, v0.15 (derived) | 3 | 0 | 0 | 2 | 2 | 2 | 0 | — |
| held-out 2, v0.17 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 0 |

## The three ladders together

| | Silently wrong (C) | False claims |
|---|---|---|
| v0.15 | 3 + 4 + 2 = 9 | 5 + 1 + 0 = 6 |
| v0.16/v0.17 | 0 + 1 + 1 = 2 | 0 |

Both remaining C are noise in the signal band (1.5x, 2.0x). In both, the released stack is only slightly below the reference stack (0.514 against 0.534, 0.494 against 0.510). The problem is that the data themselves are already below good. A signal that shows this exists in the system (a shallow `supported_to_s`), but it is not attached to the stack.

## Decisions

- R2b and N1 stay in the code. Neither adds refusals, and N1 is accurate on noise-free data. They are recorded in RESULT as not working on the data they were meant for.
- The N1 window is not changed on the basis of these results. Changing it in the next version requires writing the criteria first and testing on a new held-out ladder.

## v0.18 candidates (not implemented)

- **Disclosure of extrapolated depth.** Attach to the stack result that the section below X s was stacked with an extrapolated velocity (the ratio of the minimum `supported_to_s` to the record length). Both remaining C fit this condition (1.48 and 1.60 s < 2.6 s).
- **Redesign of the N1 window.** Put the lower end at the end of the record (or a disclosed window) instead of the velocity support depth, and report the extrapolated part separately.
- The problem that R1 becomes UNKNOWN with statics (direct-wave detection at 30 to 250 Hz) remains, separate from R2b.
