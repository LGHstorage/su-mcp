# v0.27.0 criteria: a smoothed migration velocity, and lateral coverage (written before any code)

Written 2026-09-28. Not edited after the first formal run; anything found before it goes in an addendum.
No new MCP tool (38). migrate_stack gains a method and a new default; the running server shows the new docstring only
after a restart, but the worker picks up the code.

## Why

v0.26 (DMO) raised the migration match on clean v2 from 0.536 to 0.562, and in the deep window (1.4-2.4 s) from 0.466
to 0.499. A development diagnosis on the cloud replica of clean v2 (the DMO stack of v0.26, not held-out), migration
match against the migrated reference, whole window / 1.4-2.4 s:

| migration velocity | match | deep |
|---|---|---|
| picked, lateral median (v0.24 default) | 0.579 | 0.536 |
| picked, per location, blended (phase_shift_blend) | 0.517 | 0.450 |
| same, CDP 843 replaced by the true vertical Vrms | 0.588 | 0.499 |
| same, constant interval velocity below each last pick | 0.517 | 0.450 |
| true vertical Vrms at the 9 analysis locations, blended | 0.658 | 0.591 |

1. The velocity, not the operator, limits the deep image: the true Vrms at the same nine locations gives 0.658.
2. One location dominates: the deepest pick at CDP 843 (2750 m/s where the truth is 2150) costs 0.07 in the blend.
   Per-location blending propagates a single bad pick; the lateral median hides it but also removes the real
   lateral trend.
3. The user's question (the pick curve drops vertically below the last pick): v_rms is held constant below each
   location's deepest supported pick (since v0.15). A constant interval velocity below the last pick instead changes
   nothing inside the evaluated window (last picks at 2.24-2.52 s of a 2.6 s record, window to 2.4 s). Holding v_rms
   is kept: below the last pick nothing is measured, both are assumptions, and the held one is the disclosed one
   (E1/E2). This is recorded, not changed.

Candidate smoothers tried on the same stack (development selection, disclosed): running median over 3 locations
0.584; over 5 locations, window truncated at the ends 0.643; each location clipped to within 5% of the lateral median
0.623; within 10% 0.584. The rule below is the 5-location median with the window shifted inside the line at the ends
(so every location sees five): 0.632 (deep 0.587); on the v0.24 stack without DMO 0.553 against 0.513 for the
lateral median. It was chosen on clean v2 only; the held-out ladder decides.

v0.25 left one silent wrong stack outside its criteria: the 2.0 km crop, whose five velocity locations sat within 15
CDPs of a 200-CDP line (stack 0.508, reliability OK).

## Rules

**M6 (migration velocity).** New migrate_stack method "phase_shift_smooth", the new default. At each analysis location
the migration v_rms(t) is the median, sample by sample in time, of the v_rms(t) of the five analysis locations nearest
in order (the window is shifted to stay inside the line at the ends; all locations when there are five or fewer).
Each smoothed function goes through Dix to sumigps, and output traces are blended linearly in cdp between the two
bracketing locations, as phase_shift_blend does. With five or fewer locations there is one migration with the common
function. M1 (impulse focus with the same smoothed velocities), M2, M3 and M5 are applied unchanged. The stacking
velocity is not changed: smoothing is for migration only. phase_shift and phase_shift_blend are unchanged.

**W4 (lateral coverage).** Stack quality WARN when fewer than a quarter of the stacked CMPs lie between the outermost
valid velocity locations: the rest of the section was stacked on a velocity held constant sideways. The lateral
analogue of W3, with W3's fraction (0.25), not a fitted value. Reported as velocity_support.lateral_fraction.

## Protocol P9

P8 of v0.26, steps 1-11 unchanged (import ... DMO ... residual statics), then migrate_stack twice: method
"phase_shift" and method "phase_shift_smooth" (run_as_job=true).

## Evaluation

A. Regression: stack bytes Viking `181fc5ba…`, v2 (P7 path, no DMO) `7374cb63…`; phase_shift migration of that v2 stack
   `f8c90340…` (v0.26); unit tests pass. Viking phase_shift_smooth: descriptive.
B. The v0.25 2.0 km crop (test_dataset/Marm2_ladder_heldout10/crop_027shots.sgy, not held-out) through P7 stack:
   W4 WARN.
C. Clean v2 with DMO (P9): Q_mig(phase_shift_smooth) >= 0.59.
D. Twelfth held-out ladder, generated after the code is frozen, seeds 121-123: statics 10 ms + band noise 0.8x, white
   noise 1.2x, band noise 1.0x, delay 50 ms, clean line cropped to 64 shots (about 3.5 km) and to 32 shots (about
   2.2 km), all centred on shot 63. P9 on every level. Predictions: on every level with six or more valid locations
   Q_mig(smooth) >= Q_mig(phase_shift) - 0.01, and higher on at least three of them; the mean gain in the 1.4-2.4 s
   window over those levels is positive; no C among the released stacks.

Failure of v0.27: any C in B or D; phase_shift_smooth lower than phase_shift by more than 0.01 on a level with six or
more valid locations; C below 0.59; a regression byte change; any budget overrun or false claim.
