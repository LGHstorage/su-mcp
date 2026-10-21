# v0.27.0 result: smoothed migration velocity (M6) and lateral coverage (W4)

Run 2026-09-28 by four operator agents (protocol P9, fixed in CRITERIA.md before the ladder existed). Evaluation:
`dev/marm2_ladder/evaluate_v027.py` -> `results/v0270/eval_v027.json`. Figures: `qc/v0270/fig10_migration_m6.png`,
`qc/v0270/fig11_velocity_m6.png`. No rerun, no tuning. Verdict: **v0.27 passes** (no failure condition met).

## A. Regression

| dataset | check | result |
|---|---|---|
| v027-viking | stack `181fc5ba…`; phase_shift migration `59730242…` (v0.26) | identical |
| v027-v2n | stack-1 `7374cb63…`; phase_shift migration `f8c90340…` | identical |
| unit tests | 477 (3 skipped without SU) | pass |

Viking phase_shift_smooth (descriptive): 5 locations, so one migration with the location median; M1 PASS (focus
0.749 / 0.720 / 0.671 against 0.795 / 0.679 / 0.504 for phase_shift), M5 WARN as before.

## B. The v0.25 silent wrong stack (2.0 km crop)

v027-c027: valid locations 833-848, lateral fraction 0.08, **W4 WARN**. Stack 0.508: class C -> Bn. Met.

## C. Clean v2 with DMO

| migration | match | 0.7-1.4 s | 1.4-2.4 s |
|---|---|---|---|
| v0.25 path (no DMO, phase_shift) | 0.536 | 0.725 | 0.466 |
| v0.26 (DMO, phase_shift) | 0.562 | 0.791 | 0.499 |
| **v0.27 (DMO, phase_shift_smooth)** | **0.632** | 0.810 | **0.587** |
| development bound: true Vrms at the same 9 locations, blended (cloud) | 0.658 | 0.873 | 0.591 |

Criterion >= 0.59: met. The deep window is now at the level the true velocity reaches at the same nine locations.

## D. Twelfth held-out ladder (seeds 121-123)

| level | valid loc. | stack 0 -> 1 (DMO) | phase_shift (deep) | smooth (deep) | stack reliability | class |
|---|---|---|---|---|---|---|
| statics 10 ms + band 0.8x | 9 | 0.614 -> 0.649 | 0.556 (0.478) | **0.617 (0.577)** | OK | A |
| white 1.2x | 9 | 0.576 -> 0.612 | 0.497 (0.398) | **0.523 (0.494)** | WARN (N2 0.936) + CAUTION | A* |
| band 1.0x | 9 | 0.606 -> 0.659 | 0.560 (0.485) | **0.568 (0.498)** | OK | A |
| delay 50 ms | 9 | 0.639 -> 0.697 | 0.585 (0.487) | **0.616 (0.562)** | OK | A |
| crop 64 shots | 5 | 0.585 -> 0.658 | 0.469 (0.413) | 0.479 (0.410) | OK (M5 WARN on migration) | A |
| crop 32 shots | 5 | 0.522 -> 0.574 | 0.301 (0.227) | 0.345 (0.298) | WARN (W4 16%) | A* |

Predictions on the four levels with six or more valid locations: smooth >= phase_shift - 0.01 on all (gain +0.008 to
+0.061), higher on all four (needed three); mean deep-window gain +0.071 (needed > 0). No C among released stacks.
All met. DMO was accepted on all six levels (preservation 0.914-0.928) and raised every stack again (+0.035 to +0.073).

## Findings outside the criteria

1. W4 has a cost: the 2.2 km crop (0.574, just above the good threshold 0.560) is warned (A*). It is the same kind
   of line as the 2.0 km crop it was written for; the two differ by 0.07 in truth match.
2. With five or fewer locations, smooth is one migration with the location median, not the grid median phase_shift
   uses. On the 2.0 km crop it is lower (0.153 against 0.211), on the 2.2 and 3.5 km crops higher (0.345 / 0.301,
   0.479 / 0.469). The criteria covered only lines with six or more locations; short lines stay M5-warned.
3. The 3.5 km crop picks were 11.5% fast before DMO and 1.3% after (deep 15.2% -> 0.3%).
4. Holding v_rms below the last pick (the user's question) was left as it is: a constant interval velocity below
   the last pick changed nothing in the evaluated window (development, clean v2).
5. The smooth job result did not carry migration_velocity (only the evidence did). Fixed in v0.27.1 (payload only).
6. Evaluation harness: the 3.5 km crop stack has fully muted end traces; evaluate_v027 drops traces with no energy in
   either window before matching (the same live-trace filter evaluate_migration has used since v0.25).
7. The running server still shows the v0.26.0 docstrings (passes "2", default method "phase_shift") until restarted.
   Operators passed method explicitly; budgets were applied correctly.

## Budgets

No overrun. Largest: v027-h12-dl, 3 conditioning passes, 2 velocity analyses. No refine call anywhere.
