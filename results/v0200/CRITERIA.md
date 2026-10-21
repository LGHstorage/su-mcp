# v0.20.0 criteria: attacking the refusal bottlenecks (written before any code)

Written 2026-09-23 against v0.19.0. Not edited after the first run. User decision: do as much as
possible in this step because testing will not be possible for a while; think of several ways
through the bottleneck and add modules where needed.

Constraint chosen for that reason: no new MCP tool schema. Every change goes through the existing
37 tools (new conditioning operations, new refine strategies, changed gates), so the whole
evaluation can be run now without restarting the server.

## The bottlenecks (from v0.19)

1. One end analysis location fails and the line fails the 80% coverage rule (most refusals).
2. A late time axis biases shallow picks to the scan edge (delay 105-150 ms); R1 measures the lag
   but nothing uses it.
3. Feasibility INCONCLUSIVE stops usable data before any CMP-domain evidence is looked at
   (white noise 0.5-1.0x, statics 16 ms): the 30-250 Hz feasibility band holds < 0.01% of the energy.
4. Statics are only tolerated, never estimated.
5. Gate blind spots: the injection gate cannot see damage above the last direct arrival (mute).
6. E1 false alarms on good stacks.

## Methods considered

| method | decision | reason |
|---|---|---|
| denser default analysis locations | not now | changes every regression stack; n_locations is already a parameter |
| lower the 80% coverage threshold | rejected | tuning to pass |
| widen the velocity scan below 1400 m/s | rejected | hides the delay bias instead of removing it |
| relocation to independent data (R3) | adopted | v0.19 moved 1-2 CMPs, i.e. the same data |
| scoped release (S1) | adopted | release only the measured span instead of extrapolating |
| datum shift from R1 (T1) | adopted | the lag is measured; re-measured after correction |
| feasibility by CMP-domain evidence (G1) | adopted | velocity path-null test is itself a reflection detection |
| surface-consistent residual statics (RS, suresstat) | adopted | the classic iterative loop |
| two-window injection gate (G2) | adopted | closes the mute blind spot |
| combined warning rule (W1) | adopted | proposed in v0.18; seen since on more levels; tested on a new ladder |
| decon-aware gate | not now | needs a wavelet-shape model |

## Rules

**R3 relocation (refine strategy 2, replaces v0.19 rule).** Candidates at +-s/8 and +-s/4 of the
analysis spacing s (in bins), eligible CMPs only, never another analysis location; ordered by
distance, inward first on ties; at most 3, each a 5-CMP supergather.

**S1 scoped release (refine, after strategy 3).** If the model still fails only on coverage (at least
3 valid locations) and the valid locations cover at least 50% of the analysed span,
velocity.validated becomes PASS with scope = [first valid cdp, last valid cdp]. stack_cmp then
stacks only CMPs inside the scope, and the stack records the scope. No extrapolation beyond the
last measured location is released.

**T1 datum_shift (conditioning operation, alone in its pass).** Needs an R1 intercept (PASS or FAIL)
with |lag| > T/4 (D1 DISPLACED or R1 FAIL); refuses otherwise. Shifts every trace by -lag
(rounded to a sample). Gate: R1 re-measured on the same gather of the shifted data must give
|lag| <= T/4. On PASS acquisition.time_zero_consistent is re-set from the re-measurement, with the
applied shift recorded, and D1 discloses the shift on every later stack (late clock and causal
wavelet remain indistinguishable).

**RS residual_statics (conditioning operation, alone in its pass).** Needs velocity.validated PASS.
NMO with the current model, mute above the direct wave plus one period, suresstat (Ronen-Claerbout)
with shot = fldr rank and receiver station = ground-position rank, maximum shift half a period.
Gate (split-half reliability): statics are estimated separately from odd and even CMPs; the
Spearman-Brown reliability 2r/(1+r) of the source and of the receiver solutions must both be
>= 0.9 (the "good" fraction), and the full-solution rms must be <= T/4. On PASS the statics are
applied to the CMP gathers and velocity/NMO/stack are invalidated. Statics estimated on noise do
not repeat between halves, so clean or statics-free data should FAIL this gate and keep its stack.

**G1 feasibility INCONCLUSIVE.** build_cmp accepts reflection.processing_feasible UNKNOWN when its
recorded verdict is INCONCLUSIVE (FAIL and never-evaluated still refuse). The stack records
"feasibility not established before binning; reflections shown only by velocity analysis". This is
a disclosure, not a warning: in the matrix such a stack is judged like any other.

**G2 two-window injection.** The conditioning injection gate adds a shallow set (t0 at 25/50/75% of
the window from the record start to the last direct arrival, same velocity factors). PASS needs both
sets >= 0.9. Operations whose purpose is a time shift (T1, RS) use their own gates.

**W1 reliability warning.** stack.completed carries reliability WARN when N1 is NOISE_LIMITED, or
when E1 is PARTIAL and the N1 correlation ceiling is < 0.95; otherwise OK. N1 and E1 stay reported.
From v0.20 the matrix counts a stack as warned only on W1.

Budgets unchanged: 4 velocity analyses, 1 refine per model (3 strategies + S1), 2 conditioning passes.

## Protocol P2 (fixed for every level)

1. import, geometry_analyze, assess_reflection_feasibility (fldr 63), build_cmp (20 m), sort_cmp.
2. If R1 measured a lag with |lag| > T/4: condition_gathers [datum_shift].
3. pick_velocity; on a location-level FAIL, refine_velocity once.
4. If validated: apply_nmo, stack_cmp (stack 1, copied aside for evaluation).
5. If stack 1 was released and conditioning budget remains: condition_gathers [residual_statics];
   if accepted: pick_velocity (refine once on FAIL), apply_nmo, stack_cmp (stack 2).
   The released product is stack 2 if it exists, else stack 1.

## Evaluation

A. Regression: v2 and Viking stacks byte-identical under the standard pipeline; W1 OK on both.
   Unit tests pass, including the data001 refusal tests.
B. P2 on every level still in E after v0.19 (descriptive; predictions):

| level | v0.19 | expected under P2 |
|---|---|---|
| H1 delay 110 | E (R2 edge) | T1 shifts ~108 ms, release; A or B |
| L1 delay 124 | E (R1 FAIL) | T1, release; A or B |
| H4 delay 105 | E (coverage) | T1, release; A or B |
| H1 white noise 1.0x | E (F1) | G1, velocity decides; A, Bn or D |
| H2 white noise 0.5x | E (F1) | G1; A likely |
| H3 white noise 1.0x | E (F1) | G1; A, Bn or D |
| H4 statics 16 ms | E (F1) | G1, then RS; A |
| L1 noise 1.0x, statics 20 ms | E | reported as they fall |

C. Gates on clean v2: bandpass 3-35 must still PASS (both windows); bandpass 30-70 must FAIL;
   mute_direct expected to FAIL under G2 (it removes shallow far-offset reflections, stack
   0.622 -> 0.581 in v0.19); datum_shift on v2 must be refused (lag -2 ms); residual_statics on v2
   expected to FAIL (no statics to repeat between halves).
   RS on a statics level (H2 statics 18 ms): expected PASS, and the estimated statics are compared
   with the true ones from the ladder provenance (evaluation only).
D. Fifth held-out ladder, generated after the code is frozen, seeds 51-53, P2 on every level:

| level | prediction |
|---|---|
| statics 12 ms | A (RS may or may not pass) |
| statics 24 ms | F1 INCONCLUSIVE -> G1; velocity may fail; if released, RS PASS; A or E |
| delay 45 ms | D1 DISPLACED -> T1; A |
| delay 80 ms | T1; A |
| delay 140 ms | R1 FAIL -> T1; A |
| band noise 0.6x | A |
| band noise 1.3x | released with W1 WARN (Bn) or A |
| band noise 2.4x | Bn or D |
| white noise 1.5x | G1; D or Bn |
| statics 16 ms + band noise 1.0x | Bn or A |

Failure of v0.20: any C in B or D, any false claim, a regression byte change, any budget overrun,
or data001 no longer refused.

## Addendum written during implementation, before any evaluation run

The body above is unchanged. Two things were found in the cloud smoke test (synthetic data,
not an evaluation) and are recorded here before the first evaluation run:

1. **Multiple testing in refine_velocity.** A failed location can now be tested up to five times
   (5-CMP supergather, three relocations on independent traces, 9-CMP supergather). In the smoke
   test a 5-CMP supergather of pure noise passed the path-null test at p = 0.025, the smallest p
   that 39 trials can give. Each refine test therefore uses 99 null trials and alpha = 0.05/5 =
   0.01 (Bonferroni over the five tests), so that noise passes a location's whole ladder with
   about the same probability as one first pick. The time-local support envelope still uses the
   first 39 trials, so "measured to" keeps its meaning. On 100 fresh noise supergathers with the
   first-pick settings 1 had p <= 0.05; the smoke-test realisation was a rare one, and it still
   passes at p = 0.01 (it beats all 99 nulls). This is disclosed rather than tuned away.
2. residual_statics on data with no statics returns all-zero statics; the gate reports that
   directly ("found no residual statics") instead of a reliability of zero.
