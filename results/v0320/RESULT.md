# v0.32.0 result: acquisition statics (S1) on Poland Line 001

Evaluated 2026-09-29 against CRITERIA.md (unchanged). Three operator runs, no retries, no parameter changed after a
result was seen. Figure: qc/v0320/fig18_poland_s1.png.

## Verdict

v0.32 meets A and B; C is recorded. No failure condition occurred. S1 fixes the direction of the SPS statics, and
Poland Line 001 now reaches a validated velocity, a stack and a released time migration for the first time. The
section is still noise-limited: both products are WARN and the image shows one or two faint continuous events
(about 1.45 s and 1.8 s), not an interpretable section.

## A. Regression: met

| product | sha256 (first 12) | expected |
|---|---|---|
| results/v032-viking_stack.su | 181fc5ba826f | 181fc5ba |
| results/v032-viking_mig_phase_shift.su | 59730242142f | 59730242 |
| results/v032-v2n_stack.su (= v0320/stacks/v032-v2n_stack1.su) | 7374cb63a562 | 7374cb63 |
| results/v032-v2n_mig_phase_shift.su | f8c903409d23 | f8c90340 |

S1 on both: applied=false. Viking: "no source or receiver statics in headers; tstat = 11 ms is recorded as already
applied ... left alone". v2n: no statics. Q0 at sort_cmp: 0 corrupt on both. Unit tests (including S1 on synthetic
statics in both directions) passed before deployment.

## B. Poland, fixed protocol P14 (v032-poland): met

- Geometry (SPS/RPS/XPS) ACCEPTED, 70,782 data traces placed, 502 auxiliary excluded. Statics written: source -57..-41,
  receiver -58..-41, total -115..-82 ms.
- Feasibility fldr 356 PASS (4 candidates agreed by 3 branches, 0.11-1.61 s, 2250-3000 m/s). Direct wave FRAGILE,
  time_zero UNKNOWN.
- build_cmp 12.5 m, 1281 bins, median fold 70; crookedness rms 80 m, max 293 m.
- **S1 PASS**: median near-offset first-break intercept 0.1195 s -> 0.0301 s (251/251 shots). Development measurement
  was 119 -> 22 ms; the gate rule, not the number, is the criterion.
- kill_corrupt refused (nothing to remove), no-op.
- **Velocity**: first pick FAIL, 4 of 15 locations valid (11 failed on shallow support 0.24-1.44 s or null
  clearance); refine (supergather 5) PASS, 15/15, max gap 55 CDP; analyses 2 of 6.
  Against the criterion (v0.14 sign=+1: 1 of 5): 4 valid is more than 1, met. The v0.14 sign=-1 branch gave 3 of 5; as
  a fraction, the first pick here (4/15) is not better than that, and the gate opened through refine.
- Stack 0: reliability WARN. N2 ceiling 0.086, E2 measured fraction 0.00, lateral fraction 0.566, time_datum UNKNOWN.
  Both N2 and E2 were measured only in 2.363-3.002 s (see Findings 1).
- DMO rejected (preservation 0.606 < 0.9). Residual statics rejected (split-half 0.00 / -0.17; rms 1.7 ms against a
  6.1 ms materiality threshold). No re-pick, no stack 1/2. Passes 2 of 3.
- Migration phase_shift_smooth **released**, WARN: M1 0.864/0.721/0.672 (0 trace / 2 ms shift), M2 0.17/0.18, M3 0.42,
  M5 0.323 (no warning), M8 0.166 in the single window 2.363-3.0 s, f_dom 44 Hz, M7 0.32 s. Budgets respected.
- velF = vel0 (byte-identical; no pass accepted).

## C. Agent run (v032-polagent): recorded

Route: segy_inspect -> import -> inspect/assign SPS geometry -> geometry_analyze -> scan_coherence and
measure_apparent_velocity (about 3125 m/s) -> feasibility with band 10-90 Hz and water_velocity 3000 (PASS, 5
candidates) -> build_cmp (reference 2500 m/s) -> sort_cmp (S1 PASS, same 0.1195 -> 0.0301 s) -> bandpass [10,15,70,90]
+ AGC rejected (0.586/0.640) -> pick (band 12-70 Hz) 4/15 -> refine 15/15 -> stack WARN (ceiling 0.054, E2 0.00) ->
residual statics rejected (0.00/-0.07; 2.3 ms immaterial) -> DMO declined by choice (budget risk to the validated
velocity) -> phase_shift_smooth released WARN (M1 0.83/0.76/0.62, M8 0.18). Hand-over it proposes: CDP 281-1005,
0.3 to 1.5-2.0 s. The agent's stack differs from P14's (its pick band); the images are visually the same.

## Descriptive numbers (post hoc, not criteria)

Median trace-to-trace correlation of the stacks, CDP 281-1005, 10-40 Hz, lags 1/2/5 traces:

| stack | 0.3-1.0 s | 1.0-2.0 s | 2.0-2.5 s |
|---|---|---|---|
| v0.13 (no statics, v0.13 velocity) | 0.07/0.06/0.03 | 0.01/0.07/0.04 | 0.27/0.26/0.19 |
| v0.32 P14 stack 0 | 0.01/0.05/0.03 | 0.02/0.05/0.05 | 0.18/0.18/0.13 |
| v0.32 agent | 0.02/0.05/0.03 | 0.01/0.06/0.05 | 0.17/0.17/0.14 |

S1 does not raise the stack's lateral coherence measurably; the comparison also mixes a different velocity. What S1
changes is the time datum (near-offset intercept 30 ms instead of 120 ms, or 215 ms with the old sign) and the
velocity gate. The low coherence agrees with N2 and M2/M8.

## Findings (no change in this version)

1. **Land QC windows pinned to water.** stack_cmp, the conditioning gate and migrate_stack take the last direct arrival
   from an ASSUMED 1492 m/s, which on 3.5 km offsets is 2.363 s. N2, E2 and M8 are then measured only below the
   reflections at 0.4-2.3 s. E2 = 0.00 and M8 = one window are artefacts of that, and the WARNs are partly spurious
   (and could equally hide a real problem above 2.36 s).
2. **Injection gate frequency.** The conditioning gate injected a 13 Hz wavelet estimated from ground-roll-dominated
   gathers (stack f_dom 44 Hz), so a land low-cut near 13 Hz cannot pass by construction.
3. **Reporting defect.** pick_velocity reports acquisition_statics "applied: false ... tstat recorded as already
   applied ... left alone" after sort_cmp applied S1: true in substance (not applied again), contradictory in form.
   Not counted as a false claim (no product or gate depends on it); to be fixed.
4. geometry_analyze sets receiver_spacing_consistent = FAIL on a split-spread land shot (water-wave moveout model;
   6670 m/s vs a 2,012,280 m/s prediction). Harmless to gating, misleading in the manifest.
5. No shot/receiver-domain ground-roll attenuation; dip_filter per CMP is aliased at about 100 m offset steps on land.
6. Budget interaction: after an accepted DMO or residual-statics pass the plain re-pick cannot use supergathers, so on
   noisy land data any accepted pass risks losing the validated velocity.
7. Crookedness (rms 80 m) is reported but has no consequence.
8. From the regression run: v2n feasibility reported in-band energy 0.000058 (30-250 Hz, data about 9 Hz) and still
   in_band_verdict PASS, demoted=false: a missing gate.
9. Minor: measure_apparent_velocity returned exactly the 8 ms/channel cap with max_slope_ms=40; scan_coherence asks for
   fldr= on a single-shot file; sugethw output is not readable back through the tools.
