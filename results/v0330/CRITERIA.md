# v0.33.0 criteria: land reflection window and gate frequency (Poland Line 001)

Written 2026-09-30 before any code. Not edited after the first formal run; anything found before it goes in an
addendum. No new MCP tool.

## Why (development, before this version)

v0.32 released Poland Line 001 with WARNs that were partly produced by marine defaults.

1. Reflection window. stack_cmp (N2, E2), the conditioning gate (injection windows), DMO and residual statics
   (mute, injection) and migrate_stack (M5, M8) start the reflection window at the last direct arrival, max
   offset / direct velocity. Without R1's direct wave the velocity is an ASSUMED 1492 m/s: on Poland (max offset
   3525 m) 2.363 s, below nearly all the reflections found at 0.4-2.3 s. E2 read 0.00 and M8 had one window.
   Measured on the data (dev/poland/v033_firstarrivals.py; S1-corrected traces, first sample above a quarter of
   the trace maximum, one robust straight-line fit per shot over 25-75% of the maximum offset, 84 shots): the first
   arrivals leave the spread at 1.467 s (p10-p90 1.429-1.479 s; intercept 0.178 s, 2739 m/s).
2. Gate frequency. Without R1's period the gates take the argmax of the mean amplitude spectrum of the QC gathers.
   A correlated sweep (8-95 Hz) has a flat spectrum and the argmax jumps between 13 and 45 Hz from gather to gather
   (dev/poland/v033_spec.py); the agent's bandpass gate injected at 13 Hz, so a land low-cut could not pass. A
   Ricker-equivalent peak from the spectrum's centroid (dev/poland/v033_gatefreq.py) gives 34-43 Hz on the same
   gathers (the stack's dominant frequency in v0.32 was 44 Hz) and recovers synthetic Rickers of 8.7, 25, 44 and
   60 Hz within 5% at moderate noise.
3. pick_velocity reported the S1 statics as "applied: false ... tstat recorded as already applied" after sort_cmp
   had applied them.
4. geometry_analyze predicts the arrival slope of a split-spread shot from channel-ordered distances, whose median
   step is near zero: a prediction of 2,012,280 m/s and receiver_spacing_consistent = FAIL on a line whose SPS
   geometry passed every check.

## Rules

**L0 (land).** A dataset is treated as land when S1 applied acquisition datum statics (verdict PASS). Nothing else
changes the marine behaviour; land data without datum statics keep the marine default, reported as ASSUMED.

**L1 (reflection window on land).** At sort_cmp, after S1 PASS, the first arrivals are measured on the corrected
gathers: per shot, first sample above a quarter of the trace maximum (search to min(record end, 0.75 x max offset /
1000 m/s + 0.5 s)), robust straight-line fit over 25-75% of the maximum offset (refit without residuals beyond 3
MAD), at least 10 picks and 10 shots. The reflection window starts at t_a = median over shots of (intercept + max
offset x slowness), MEASURED. Everything that used the last direct arrival uses t_a instead: N2, E2, the injection
windows and their moveout velocity (first-arrival velocity), DMO and residual-statics injection and mute, M5, M8,
and mute_direct (intercept + offset / velocity, available on land without R1). If the measurement fails, the marine
default stays, ASSUMED, and the reason is reported.

**G1 (gate frequency).** When R1 has no period, the frequency the gates inject (and whose period sets the
residual-statics and DMO limits) is the Ricker-equivalent peak: amplitude spectrum averaged over the QC traces,
smoothed over 5 Hz, noise floor (median above 0.8 Nyquist) removed, centroid over the part above 10% of the maximum,
times sqrt(pi)/2. R1's measured period still takes precedence.

**G3.** When the measured shot is split-spread (sources inside the receiver spread), the geometry slope cross-check
is NOT_APPLICABLE and no receiver_spacing_consistent verdict is written.

**R2.** When S1 applied the statics at sort_cmp, later steps report "applied at sort_cmp (S1), not applied again",
with the sort_cmp record, not "applied: false".

## Protocol P15 (Poland, fixed)

P14 unchanged except the re-pick after an accepted conditioning pass may take one refine on FAIL (as the first pick
does). dataset v033-poland. Agent run (v033-polagent): the v0.32 land instruction, unchanged.

## Evaluation

A. Regression: stack bytes Viking 200-CDP `181fc5ba`, v2n `7374cb63`, migrations `59730242`, `f8c90340`; their N2,
   E2, M5 and M8 values identical to v0.32 (L0 does not apply); unit tests pass (L1 on a synthetic line with known
   intercept and velocity, G1 on synthetic Rickers, G3 on a split spread, R2 message).
B. Poland, P15:
   1. S1 PASS as in v0.32 (0.1195 -> 0.0301 s).
   2. L1 MEASURED with t_a within 1.47 +/- 0.10 s; N2, E2 and M8 windows start there (not 2.363 s).
   3. Every gate that injects reports its frequency source; without R1 it is G1, between 30 and 48 Hz.
   4. pick_velocity reports S1 as applied at sort_cmp (R2); geometry_analyze on fldr 356 reports the slope
      cross-check NOT_APPLICABLE (G3).
   5. Recorded without prediction: velocity, stack reliability, DMO, residual statics, re-picks, migration gates,
      image.
C. Agent run recorded without prediction.

Failure of v0.33: a regression byte or QC value change; an L rule acting on a dataset without S1 statics; t_a outside
the band in B2; a gate injecting at an argmax frequency when R1 has none; a released product with a non-finite or
contradicted QC read as a pass; a budget overrun or false claim.

## Addendum (2026-09-30, before the first formal run; the criteria above are unchanged)

1. The robust refit in the development script rejected residuals by |r| instead of |r - median(r)|. The code (and
   the corrected script, dev/poland/v033_firstarrivals.py) use |r - median(r)| <= 3 x 1.4826 x MAD. Re-measured: t_a
   1.466 s (p10-p90 1.429-1.479 s, 2742 m/s), unchanged within the band.
2. The v0.33 code run outside MCP on the same development copy (all 251 shots, search to 3.0 s): L1 MEASURED, t_a
   1.463 s, intercept 0.178 s, 2744 m/s, p10-p90 1.428-1.481 s. G1 on the first 400 traces: 35.2 Hz.
3. Unit tests: 525 run, 0 failures (3 skipped).
4. P14 runs geometry_analyze with defaults, which measures no shot, so B4's G3 check cannot come from P15. It is run
   by the regression operator on a separate dataset (v033-polgeo: import, assign_external_geometry,
   geometry_analyze(measure_fldr=356, measure_tmin=0, measure_tmax=1.2), the agent's v0.32 call). P15 is otherwise
   P14 with new ids (the re-pick already allowed one refine in P14).
5. The deployment made the v0.33 code live without a server restart (su_status reports 0.33.0; the tool
   descriptions in server.py take effect at the next restart).
6. Infrastructure interruption (2026-09-30 about 00:05 UTC): the session running the operators was interrupted and
   the P15 (v033-poland) and agent (v033-polagent) operators stopped mid-run (P15 in its DMO pass, the agent in its
   second conditioning pass). Both runs are abandoned, not continued, and are not evaluated. They are repeated from
   the start on new ids, v033b-poland (P15, unchanged) and v033b-polagent (agent instruction, unchanged). What the
   abandoned runs had reached before the interruption (S1, L1 and stack 0) is recorded in RESULT.md as a
   consistency check only. The v033-poland DMO job was cancelled; the v033-polagent statics job was left to finish.
   The regression run and v033-polgeo completed before the interruption and stand.
