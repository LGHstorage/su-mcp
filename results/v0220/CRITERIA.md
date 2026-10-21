# v0.22.0 criteria: denser velocity analysis (written before any code)

Written 2026-09-28 after v0.21.0 met its failure conditions but left one silent wrong stack (C) in its
descriptive section. Not edited after the first run; anything found before the first run goes in an addendum.
No new MCP tool schema (37 tools): the evaluation runs without a server restart.

## What v0.21 left

1. H5 statics 16 ms + band noise 1.0x: residual statics raised the half-stack ceiling from 0.891 to 0.959, so W1
   switched off, but truth quality stayed 0.548 (< 0.560). The velocity was measured over 6% of the reflection
   window at the shallowest valid location; the rest was stacked on a velocity held constant.
2. Five analysis locations about 1 km apart. Most refine calls and refusals since v0.19 came from one location,
   usually the last one (cdp 1048): losing it turns interpolation into extrapolation and fails coverage.
3. E1 is the minimum supported depth over the valid locations. With more locations the minimum can only fall,
   so E1 as written would warn more the denser the analysis, whatever the section looks like.

## Rules

**D1 (density).** Without a caller cdp_list, pick_velocity analyses at least n_locations locations and at least one
per 500 m of the eligible span: n = max(n_locations, floor(span_m / 500) + 1), capped at 15. span_m is the eligible
cdp range times the bin size recorded by build_cmp. 500 m is the conventional 2D analysis interval, not a fitted
value. Marmousi2 (eligible cdp 637-1048 at 10 m): 9 locations. Viking (1021-1189 at 12.5 m): 5 locations, as before.

**K1 (valid count).** A model needs k valid locations, the smallest k >= 3 with P(Binomial(n, 0.05) >= k) no larger
than P(Binomial(5, 0.05) >= 3) = 0.00116, the chance with which five noise-only locations validate a model today
(0.05 is the per-location path-null alpha). n <= 5: k = min(3, n) as before; n = 6-10: k = 4; n = 11-15: k = 5.

**K2 (gap, dense mode only, n > 5).** No two adjacent valid locations may be further apart than a quarter of the
analysed span (the v0.21 location spacing). Denser analysis must never interpolate further than the sparse one did.
Coverage >= 80% of the analysed span stays.

**E2 (support by area).** measured_fraction is the mean over the stacked CMPs of the support fraction, with the
supported depth interpolated linearly in cdp between valid locations and held constant beyond them. PARTIAL if
< 0.5, as before. The shallowest supported depth is still reported (report only).

**W3.** WARN when E2's measured_fraction < 0.25, whatever the ceiling: when less than a quarter of the section rests
on a measured velocity, half-stack agreement says nothing about whether the velocity is right. W1 and W2 unchanged.

Everything else as v0.21 (T1, G1, G2, R3, S1, RS2, Bonferroni refine, budgets). refine_velocity inherits K1/K2
because it grades with the same function; its relocation step scales with the new spacing.

## Protocol P4 = P3 of v0.21 (unchanged)

import, geometry_analyze, feasibility (fldr 63; Viking cdp 1100), build_cmp (20 m; Viking 25 m), sort_cmp;
condition_gathers [datum_shift] (refusal = no-op); pick_velocity (defaults); refine_velocity once on FAIL;
apply_nmo, stack_cmp (stack 1, copied to results/v0220/stacks/); condition_gathers [residual_statics];
if accepted: pick_velocity, refine once on FAIL, apply_nmo, stack_cmp (stack 2, overwrite).

## Evaluation

A. Regression.
   - Viking, default path: stack bytes identical to `181fc5ba…` (D1 gives 5 locations).
   - v2 with cdp_list [637, 740, 843, 945, 1048]: bytes identical to `cbb46bd5…` (the sparse path is unchanged).
   - v2 default (9 locations): truth quality >= 0.612 (0.622 - 0.01), reliability OK.
   - Unit tests pass, data001 refusals included.
B. P4 on every v0.21 ladder level (18 levels, new ids, descriptive). Expected: C = 0 (the v0.21 C becomes Bn by W3
   or A), no level that was A in v0.21 becomes Bn or worse by more than one level's worth of false alarms in total.
C. Seventh held-out ladder, generated after the code is frozen, seeds 71-73, P4 on every level:

| level | prediction |
|---|---|
| statics 16 ms + band noise 1.0x | Bn (W3) or A; never C |
| band noise 0.8x | A or Bn |
| band noise 1.6x | Bn |
| white noise 1.0x | Bn (W2) |
| statics 14 ms | A after RS2 (A* if G1) |
| delay 90 ms | A (T1) |
| tail noise: white 2.0x on the shots of the last quarter of the line | A or Bn; the end is interpolated or scoped, not refused |
| statics 12 ms + white noise 0.6x | A or A* |

Failure of v0.22: any C in B or C, any false claim, a regression byte change, v2 default below 0.612, any budget
overrun, or K1/K2 validating a model on a noise-only gather in the unit tests.

## Addendum (before the first run)

1. K2 limit rounded up to a whole bin. Analysis locations sit on whole cdp numbers, so two location spacings can
   exceed a quarter of the span by one bin (Marmousi2: 740 -> 843 = 103 cdp against 411 / 4 = 102.75). The v0.21
   spacing itself was 102-103 cdp. The limit is ceil(span / 4). Found in the unit tests, before any MCP run.
