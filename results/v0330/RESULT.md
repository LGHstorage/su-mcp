# v0.33.0 result: land reflection window (L1) and gate frequency (G1), Poland Line 001

Evaluated 2026-09-30 against CRITERIA.md (rules unchanged; addendum items 1-6 written before the runs they concern).
Runs: regression (v033-viking, v033-v2n, v033-polgeo), P15 (v033b-poland), agent (v033b-polagent). The first P15 and
agent runs (v033-poland, v033-polagent) were abandoned after an infrastructure interruption (addendum 6) and are not
evaluated. Figure: qc/v0330/fig19_poland_land_qc.png.

## Verdict

v0.33 meets A and B; C is recorded. No failure condition occurred. L1 moves the land reflection window from an
assumed water arrival (2.363 s) to the measured first arrivals (1.463 s), and G1 makes the gates inject at the
data's band (33-38 Hz instead of 13 Hz). The spurious E2 warning is gone, and a land low-cut now passes the injection
gate (preservation 0.995). The section itself is not better: the half-stack ceiling in 1.46-3.0 s is 0.20 (P15) and
0.17 (agent), both products remain WARN, and the P15 stack and migration are byte-identical to v0.32 because the
DMO and residual-statics gates still reject.

## A. Regression: met

| product | sha256 (first 12) | v0.32 |
|---|---|---|
| results/v033-viking_stack.su | 181fc5ba826f | same |
| results/v033-viking_mig_phase_shift.su | 59730242142f | same |
| results/v0330/stacks/v033-v2n_stack1.su | 7374cb63a562 | same |
| results/v033-v2n_mig_phase_shift.su | f8c903409d23 | same |

QC values identical to v0.32 (read from the manifests): Viking N2 r 0.952 / ceiling 0.988 / window 2.17-6.00 s, E2
0.979, lateral 0.845, M5 1.0, M8 0.282/0.056/-0.034/0.071; v2n N2 0.998/0.999/1.40-2.602 s, E2 0.806, lateral
0.691, M5 0.403, M8 0.864/0.929. S1 applied=false on both (L0 does not apply). Unit tests: 525, 0 failures.

## B. Poland, P15 (v033b-poland): met

1. S1 PASS, intercept 0.1195 -> 0.0301 s (251/251 shots), as in v0.32.
2. L1 MEASURED: t_a 1.4628 s (p10-p90 1.4288-1.481 s), intercept 0.1775 s, 2743 m/s, 251 shots; inside 1.47 +/-
   0.10 s. N2 window 1.463-3.002 s, E2 window from 1.463 s, M8 windows 1.463-2.463 and 2.463-3.0 s, M5 from 1.463 s,
   all with rule "v0.33 L1". (v0.32: 2.363 s.)
3. Gate frequencies, all G1: DMO injected 33.56 Hz (G1_RICKER_EQUIVALENT_FROM_DATA); residual statics quarter
   period 7.5 ms (33 Hz, G1); agent's injection gates 38.36 Hz (G1_RICKER_EQUIVALENT_FROM_QC_GATHERS). None at an
   argmax frequency.
4. R2: pick_velocity reports status APPLIED_AT_SORT_CMP ("not applied again", with the sort_cmp record). G3
   (v033-polgeo, fldr 356): velocity_cross_check NOT_APPLICABLE, geometry.receiver_spacing_consistent not written;
   the agent's own geometry_analyze on fldr 356 gave the same.
5. Recorded without prediction:
   - Velocity: first pick 4/15 FAIL, refine (supergather 5) 15/15 PASS, analyses 2 of 6 (as v0.32).
   - Stack 0: WARN, N2 r 0.02, ceiling 0.200 (v0.32: 0.086 in 2.36-3.0 s); E2 0.332 PARTIAL (v0.32: 0.00), no W3;
     lateral 0.566. Byte-identical to v0.32 stack 0.
   - DMO rejected, preservation 0.568 (v0.32: 0.606 with the injection at 2.52-2.84 s; now at 1.85-2.62 s, 33.6 Hz).
   - Residual statics rejected: reliability 0.00 / -0.02, rms 1.81 ms against a 2.18 ms materiality threshold (the
     threshold fell from 6.1 ms with the G1 period).
   - Migration phase_shift_smooth released, WARN: M1 0.864/0.721/0.672, M2 0.22/0.24, M8 0.227/0.170, M5 0.266.
     Byte-identical to v0.32.

## C. Agent run (v033b-polagent): recorded

Route: segy_inspect -> import -> inspect/assign SPS geometry -> geometry_analyze (fldr 356; G3 NOT_APPLICABLE) ->
scan_coherence, measure_apparent_velocity (about 2300 m/s near offsets) -> feasibility (water_velocity 2300, 10-90
Hz; PASS, 5 candidates) -> build_cmp (reference 2500 m/s) -> sort_cmp (S1 PASS, L1 1.463 s) -> pass 1 bandpass
[6,10,70,90] + mute_direct (land L1 corridor) + AGC REJECTED (shallow 0.559, deep 0.796) -> pick 4/15 -> refine
13/15 PASS -> stack WARN (ceiling 0.173) -> pass 2 bandpass [10,18,70,90] ACCEPTED (0.995 / 0.995) -> re-pick 6/15
PASS (coverage 0.862, max gap 159) -> stack WARN (ceiling 0.167; previous stack kept as v1) -> pass 3 residual
statics REJECTED (reliability -0.008 / -0.003, immaterial) -> phase_shift_smooth released WARN (M1 0.77/0.77/0.87, M8
0.244/0.147) -> velF exported (the 6-location model). Hand-over it proposes: the stack above about 1.5 s, the
migration for geometry only.

## Findings (no change in this version)

1. **The window moved, the verdict did not.** With L1 the S/N and velocity windows sit on the reflections below 1.46
   s, and they confirm what the image shows: noise-limited (ceiling 0.17-0.20). The best-measured part, 0.3-1.46 s,
   is still unscored. The first arrivals at far offsets are mostly removed by the 1.5 stretch mute, so a window
   defined after NMO and mute could start earlier; that needs its own rule and test.
2. **G1 removed a gate artefact.** In v0.32 the bandpass was rejected because the gate injected at 13 Hz; at the
   G1 frequency (38 Hz) a 10-18-70-90 Hz bandpass keeps 0.995. It did not raise S/N (ceiling 0.173 -> 0.167, trace
   RMS -14%): low-frequency ground roll is not what limits 1.46-3.0 s. It visibly removes the shallow ground-roll
   cones (figure, top right).
3. **A weaker model replaced a stronger one.** After the accepted bandpass the agent's plain re-pick validated
   with 6 of 15 locations and replaced a 13-location refined model; nothing compares the two. Candidate rule: a
   re-pick after a pass reuses the strategy that validated the previous model (supergathers), or is compared with it.
4. **L1 extrapolates.** t_a is the line through 25-75% of the maximum offset, evaluated at the maximum offset. The
   agent found a faster arrival (about 4350 m/s at 0.85 s) in one shot; if a faster refractor arrives first at far
   offsets, the true last first arrival is earlier than 1.463 s and the window starts later than it needs to
   (conservative).
5. AGC cannot pass the injection gate (non-linear), and a top mute loses the shallow injected set at far offsets by
   construction. No trace balancing that can pass exists; sort_cmp's Q0 reported a clean-trace peak-to-median ratio
   of 2414 (67 dB).
6. Manifest: after a re-pick, velocity_model_unrefined and velocity_model point to the same file, and
   velocity_model_refined.json is not listed as an artifact.
7. Still marine-framed: geometry_analyze and survey_overview report the "water-wave" apparent-velocity check as an
   open question on land; feasibility and R1 model the direct wave through the origin (land: ABSENT or FRAGILE), so
   time_datum stays UNKNOWN.
8. The abandoned runs (v033-poland, v033-polagent) reached S1, L1 and stack 0 with the same numbers (t_a 1.4628 s,
   N2 ceiling 0.200, E2 0.332) before the interruption.
