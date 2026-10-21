# v0.16.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-23. Criteria in `CRITERIA.md` (written before the code change, not edited afterwards). Code `sumcp/reflection.py` (reflection-0.8), `sumcp/stack.py` (stack-0.9), `sumcp/tools.py`, `sumcp/config.py` (0.16.0), tests `tests/test_v016_checks.py`. Evaluation `dev/marm2_ladder/{evaluate,make_heldout,make_matrix_figure}.py`. Figure `qc/marm2_ladder/judgement_matrix.png`.

## What changed (two rules, neither lifts a refusal)

- **D1 time-datum disclosure (report only).** `stack_cmp` attaches the direct-wave peak delay measured by R1 to its result and to the `stack.completed` evidence as `time_datum`. If |delay| ≤ a quarter period (vertical resolution), it is WITHIN_RESOLUTION. Otherwise it is DISPLACED, and the shift that would undo it is stated. A late clock and a causal wavelet cannot be told apart on the direct wave, so the stack is not refused.
- **F1 band-limited absence.** Feasibility reports the fraction of gather energy inside the analysis band as `analysis_band`. If the verdict is FAIL and the fraction is below 0.5, it becomes INCONCLUSIVE. The in-band verdict stays in the reason text. INCONCLUSIVE is UNKNOWN in the manifest, so `build_cmp` still refuses.

One thing was fixed during the run. The last sentence of the F1 note, "Choose a band that holds the record's energy", was advice that contradicted the v0.15 diagnosis (at 5 to 90 Hz even the clean baseline fails), so it was changed to say that a lower band is not a solution in itself. The decision logic did not change. Results run before the change (5 reruns of ladder 1 and data001) contain the old sentence.

## Unit tests

In the cloud workspace (CWP/SU built with XDR), 354 of 357 passed and 3 were skipped (A03 fixture missing, as in v0.15). 10 v0.16 tests were added.

## Regression (MCP path)

| Data | Prediction | Result |
|---|---|---|
| Marm2 v2 0–2.6 s (`v016-v2`) | same stack, datum −2 ms WITHIN | Correct. `cbb46bd5…` identical, −2 ms WITHIN_RESOLUTION |
| Viking cdp1000–1199 (`v016-viking`) | same stack, datum UNKNOWN | Correct. `181fc5ba…` identical, UNKNOWN (direct wave ABSENT) |
| ladder 1 delay 50/76/100 (`v016-delay*`) | same stacks, DISPLACED +48/+74/+98 | Correct. All three stacks byte-identical to `lad-delay*` |
| ladder 1 noise 1/2/4x, statics 20/40 | INCONCLUSIVE (F1) | Correct. Band fractions 0.016%, 0.042%, 0.091%, 0.0052%, 0.0049% |
| A03 NOISE_ONLY cdp 1100 | uncertain | FAIL kept (band fraction 94%) |
| B02 L3 ABSENT cdp 1100 | uncertain | FAIL kept (band fraction 95%) |
| data001 tracf=1 | uncertain | **FAIL → INCONCLUSIVE** (band fraction 38%). Still refused, but it loses its status as evidence of absence for the negative control |
| Marm2 v1 original | no change | Not rerun. The R1 code (timezero-0.1) did not change |

data001 is the cost of F1. The energy fraction does not separate signal from noise, so a legitimate FAIL is also downgraded on records with much low-frequency noise (swell and similar) below 30 Hz. It is recorded without correction (see the v0.17 candidates).

## Held-out ladder (generated after the criteria were written, no tuning)

`test_dataset/Marm2_ladder_heldout/`, results in `results/marm2_ladder_heldout/` (gate records, metrics, matrix). Good threshold = 0.9 × 0.622 = 0.560 (correlation with the exploding-reflector truth, best lag within 20 ms).

| Level | v0.16 verdict | Released stack | Reference stack | Cell | Prediction |
|---|---|---|---|---|---|
| delay 12 | all PASS, +10 ms WITHIN | 0.629 | 0.628 | A | A, correct |
| delay 30 | all PASS, +28 ms WITHIN (resolution 28.6 ms) | 0.615 | 0.631 | A | A or B, correct |
| delay 40 | all PASS, +38 ms DISPLACED | 0.470 (0.624 after undoing) | 0.630 | B | correct |
| delay 60 | all PASS, +58 ms DISPLACED | −0.014 (0.627) | 0.624 | B | correct |
| delay 90 | all PASS, +88 ms DISPLACED | −0.037 (0.607) | 0.612 | B | correct |
| delay 110 | R1 PASS (+108), **refused by R2 alone** (0.32 s, 5/5) | — | 0.589 | E | one of the options, correct |
| band noise 0.75x | all PASS | 0.577 | 0.593 | A | correct |
| band noise 1.5x | all PASS | **0.514** | 0.534 | **C** | A or C |
| band noise 3x | feasibility PASS, velocity FAIL (4/5, 75%) | — | 0.426 | D | C or D |
| white noise 1x | INCONCLUSIVE (general path, direct wave ABSENT, detection limit 0.8x) | — | 0.563 | E | E correct, but the path was not F1 |
| white noise 4x | INCONCLUSIVE (same path) | — | 0.345 | D | predicted E, wrong (data not usable) |
| statics 5 | all PASS | 0.624 | 0.621 | A | correct |
| statics 15 | feasibility PASS, velocity FAIL (0.04 s scan-boundary pick at cdp 1048) | — | 0.602 | E | A or E, correct |
| statics 30 | INCONCLUSIVE (F1, band fraction 0.0074%) | — | 0.492 | D | correct |

Predicted counts. At most 1 C gave 1 (but at 1.5x, not 3x). At most 1 false claim gave 0.

## Judgment matrix

| | A | B | C | D | E | False claims |
|---|---|---|---|---|---|---|
| ladder 1, v0.15 | 3 | 0 | 3 | 4 | 3 | 5 |
| ladder 1, v0.16 | 3 | 3 | 0 | 4 | 3 | 0 |
| held-out, v0.15 (derived) | 4 | 0 | 4 | 3 | 3 | 1 |
| held-out, v0.16 | 4 | 3 | 1 | 3 | 3 | 0 |

Ladder 1 is descriptive, because the 0.560 threshold was set after its results were seen. The held-out ladder is the pre-registered test. The v0.15 row of the held-out ladder was derived and not run. D1 and F1 only add a disclosure or turn FAIL into INCONCLUSIVE, and v0.16 records the in-band verdict, so removing both gives v0.15. The derivation is in `gate_outcomes_v015equiv.json`.

## Interpretation

1. **Silently wrong products (C) fell from 7 to 1 (both ladders together).** The 6 removed are all time-datum errors. The stacks are unchanged, and undoing the disclosed delay brings all of them back to 0.607 to 0.627.
2. **False claims fell from 6 to 0.** The refusals are in the same places, and only their reasons now match the facts. The cost is that the data001 negative control weakened from FAIL to INCONCLUSIVE.
3. **The remaining C is noise inside the signal band.** Band noise 1.5x passed every gate. The released stack is 0.514, and even the reference stack is 0.534. Feasibility looks at 30 to 250 Hz and does not see 4 to 16 Hz noise, and the velocity gate passed 5/5 at 1.5x (it refuses only at 3x). No gate measures the loss of quality caused by noise. This is the next blind spot.
4. **E (usable but refused) did not decrease (3 on each ladder).** On ladder 1 these are delay 124 (R1 and R2), and noise 1x and statics 20 (feasibility band). On the held-out ladder they are delay 110 (R2), white noise 1x (feasibility band), and statics 15 (0.04 s boundary pick). They are in the conservative direction and come second in priority.

## v0.17 candidates (not implemented)

- Compute the F1 fraction from the direct-wave (flattened stack) spectrum instead of the whole gather. It is a source spectrum, less affected by noise, and could keep a legitimate FAIL on records with strong low-frequency noise such as data001. Without a direct wave, use the whole record as now.
- Disclosure of signal-band noise (report only, like D1). Attach an estimate of reflection-band S/N to the stack result (for example, the correlation of even and odd fold half-stacks). The aim is to move a C such as band noise 1.5x to B.
- Check the case where a 0.04 s boundary pick of R2 (above the seafloor, no reflections) invalidates a whole location (the E of statics 15).
