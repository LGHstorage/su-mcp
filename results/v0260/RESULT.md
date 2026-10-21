# v0.26.0 result: DMO behind a gate

Run 2026-09-28 by three operator agents (protocol P8, fixed in CRITERIA.md before the ladder existed). Evaluation:
`dev/marm2_ladder/evaluate_v026.py` -> `results/v0260/eval_v026.json`. Figures: `qc/v0260/fig8_velocity_dmo.png`,
`qc/v0260/fig9_migration_dmo.png`. No rerun, no tuning. Verdict: **v0.26 passes** (no failure condition met).

## A. Regression (no DMO, P7 path)

| dataset | check | result |
|---|---|---|
| v026-viking | stack sha256 `181fc5ba…` | identical |
| v026-v2n | stack-1 sha256 `7374cb63…` | identical (also the v026-v2 stack0) |
| unit tests | 467 (3 skipped without SU) | pass (cloud with SU; device subset without SU) |

## B. Clean v2 with DMO (v026-v2)

| quantity | criterion | before DMO | after DMO |
|---|---|---|---|
| D1 preservation | >= 0.9 | | 0.912, order kept, accepted |
| stack truth match | >= 0.66 | 0.640 | **0.696** |
| median signed pick error, 0.7 s to supported depth | < 4% | +7.6% | **+2.1%** |
| same, deeper than 1.6 s | report | +9.2% | +3.8% |
| Q_mig (phase shift) | >= 0.55 | 0.536 (v026-v2n) | **0.562** |
| Q_mig 1.4-2.4 s | report | 0.466 | 0.499 |
| reliability / M1 / M5 | report | OK / PASS / 0.40 | OK / PASS / 0.38 |

Half-stack agreement falls after DMO (r 0.998 -> 0.949, ceiling 0.999 -> 0.987): sudmofk adds operator noise that
the half-stack test sees; the truth match rises. Residual statics were rejected on v2 (immaterial, 3.7 ms).

Viking with DMO (descriptive): DMO accepted (0.948, noffmix 2, dxcdp 12.5 m), re-pick 5/5 valid, stack reliability OK
(ceiling 0.988 -> 0.980). The migration of the DMO stack was **refused by M1** (focus 0.737 / 0.487 / 0.398 at
1.8 / 3.0 / 4.2 s; without DMO 0.795 / 0.679 / 0.504, PASS). The gate did its job: after DMO the deep Viking picks are
lower, and the impulse test with that velocity no longer focuses. No truth exists for Viking, so whether the lower
velocity is closer to the truth is unknown; the refusal is the recorded outcome.

## C. Eleventh held-out ladder (seeds 111-113)

| level | DMO (D1) | stack before -> after | pick error before -> after (deep) | Q_mig (g) | reliability | class |
|---|---|---|---|---|---|---|
| statics 12 ms + band 0.6x | 0.915 acc | 0.601 -> 0.646 | +4.1% -> +0.9% (3.9 -> 2.3) | 0.572 (+0.38) | CAUTION (feasibility INCONCLUSIVE) | A~ |
| white 0.8x | 0.919 acc | 0.609 -> 0.655 | +7.6% -> +2.3% (8.9 -> 4.0) | 0.517 (+0.33) | CAUTION (same) | A~ |
| band 1.2x | 0.914 acc | 0.589 -> 0.663 | +6.1% -> +1.7% (6.1 -> 3.2) | 0.541 (+0.35) | OK (stack0 was WARN N2 0.945) | A |
| delay 70 ms | 0.914 acc | 0.640 -> 0.696 | +7.5% -> +2.1% (9.2 -> 4.2) | 0.599 (+0.39) | OK | A |
| crop 102 shots | 0.905 acc | 0.646 -> 0.672 | +7.4% -> +1.6% (9.7 -> 3.2) | 0.529 (+0.34) | OK | A |

Predictions: DMO accepted on every level (5/5); stack after >= before - 0.01 on every level and higher on at least
three (higher on 5/5, +0.026 to +0.074); |pick error| smaller on at least four (5/5); no C (0). All met.

## Findings outside the criteria

1. D1 margins are small (0.905-0.919 on Marmousi2). The threshold is the menu's 0.9 and was not changed.
2. Deep migration is better, not solved: Q_mig 1.4-2.4 s is 0.50 against 0.73-0.79 shallower. Fig 8 shows why: at
   CDP 843 (the faulted centre) the deepest pick stays at 2750 m/s after DMO against a true 2150 m/s, and at CDP
   945/997 the picks fall 7% below the truth. DMO removes the dip bias; it does not fix picks on crossing events.
3. Below the deepest supported pick the RMS velocity is held constant (since v0.15). It is disclosed (E1/E2), but it
   implies a falling interval velocity under the last pick, which is not what the geology does. Candidate for v0.27:
   constant interval velocity below the last pick (the Dix velocity of the last layer), under a pre-registered check.
4. Stale tool documentation: condition_gathers said "at most 2 passes" and refine_velocity "at most 4 velocity
   analyses" after the budgets became 3 and 6. Fixed in v0.26.1 (docstrings only, no logic change; shows after a
   server restart). The budgets themselves were applied correctly (passes_left 2 -> 1 -> 0 on the delay level).
5. DMO job results carry no elapsed time; wall clock was about 1-6 min per dataset.

## Budgets

No overrun. Largest use: v026-h11-dl, 3 conditioning passes (datum shift, DMO, rejected residual statics), 2 velocity
analyses. No refine_velocity call was needed anywhere.
