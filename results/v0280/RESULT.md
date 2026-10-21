# v0.28.0 result: depth imaging behind gates

Run 2026-09-28 by four operator agents (protocol P10, fixed in CRITERIA.md before the ladder existed). Evaluation:
`dev/marm2_ladder/evaluate_v028.py` -> `results/v0280/eval_v028.json`. Figures: `qc/v0280/fig12_depth_images.png`,
`qc/v0280/fig13_depth_error.png`. No rerun, no tuning. Verdict: **v0.28 passes** (no failure condition met).

## A. Regression

Viking stack `181fc5ba…` and phase_shift migration `59730242…`; v2 (P7) stack `7374cb63…` and phase_shift migration
`f8c90340…`: identical. Unit tests pass (Z1 fails RMS-as-interval, doubled trace spacing and doubled depth step).

## B. Clean v2 with DMO

| product | released | Z1 | Z2 | depth match 0.5-1.2 / 1.2-2.4 / 0.5-2.4 km |
|---|---|---|---|---|
| depth_convert | yes | (M1 of the time migration) | PASS | 0.610 / 0.308 / 0.237 |
| depth_pspi | yes | PASS (0.894 / 0.862 / 0.936) | PASS | 0.614 / 0.326 / 0.264 |
| bound: true vp (development) | | | | 0.863 / 0.706 / 0.722 |

C5 (depth within +-5%) **0.83** (132 of 159), median error +1.4%. Criterion >= 0.7: met.

## C. v2 without DMO (P7 path)

Both depth products carry **Z4 WARN**. C5 0.24, median +7.6% (reflectors deep); depth match 0.157 / 0.129.
Viking (no DMO) also carries Z4 on both depth products; Z1 PASS (0.801 / 0.805 / 0.761).

## D. Thirteenth held-out ladder (seeds 131-133)

| level | valid loc. | stack 0 -> 1 | C5 (median error) | depth match convert / pspi (0.5-2.4 km) | reliability | class |
|---|---|---|---|---|---|---|
| statics 8 ms + band 1.0x | 9 | 0.570 -> 0.640 | 0.818 (+1.1%) | 0.261 / 0.310 | OK | A |
| white 1.0x | 9 | 0.589 -> 0.639 | 0.829 (+0.9%) | 0.310 / 0.319 | CAUTION | A~ |
| band 0.6x | 9 | 0.623 -> 0.673 | 0.833 (+0.9%) | 0.242 / 0.263 | OK | A |
| delay 40 ms | 9 | 0.639 -> 0.697 | 0.762 (+1.2%) | 0.248 / 0.252 | OK | A |
| crop 90 shots | 6 | 0.612 -> 0.642 | 0.750 (+0.7%) | 0.195 / 0.195 | OK | A |

Predictions: Z1 PASS on every depth_pspi (5/5); C5 >= 0.6 on every qualifying level (0.75-0.83); pooled C5 0.801
(>= 0.7); no C. All met. DMO accepted on all five levels and raised every stack again (+0.03 to +0.07).

## Findings outside the criteria

1. Depth is placed, not imaged sharply. 75-83% of the measured depths are within +-5%, but the depth match is 0.2-0.3
   against 0.72 with the true velocity: +-5% at 2 km is +-100 m, beyond the +-40 m lag of the match. The honest
   product is a depth section with a stated tolerance, which is what Z3 reports.
2. depth_pspi beat depth_convert on 5 of 6 Marmousi2 datasets (mean +0.03 over 0.5-2.4 km, +0.04 deep).
3. DMO is what makes depth usable: without it C5 is 0.24 and reflectors sit 7.6% deep; Z4 catches this.
4. The time migration of the 90-shot crop carried M5 WARN (0.502), but its depth products did not (their rule was
   stack reliability + Z4). Fixed in v0.28.1: depth products carry M5 too (warning only, no effect on released
   samples).
5. The v0.27 diagnoses (short lines lose to acquisition, not velocity; the deep CDP 843 pick is the right stacking
   velocity and the wrong migration velocity) are recorded in CRITERIA.md; no rule changed for them.

## Budgets

No overrun. Largest: v028-h13-dl, 3 conditioning passes (datum shift, DMO, rejected residual statics), 2 velocity
analyses. No refine call anywhere.
