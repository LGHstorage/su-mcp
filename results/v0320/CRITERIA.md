# v0.32.0 criteria: acquisition statics in the right direction, before conditioning (Poland Line 001)

Written 2026-09-29 before any code. Not edited after the first formal run; anything found before it goes in an
addendum. No new MCP tool.

## Why (development, before this version)

Poland Line 001 (land vibroseis, SPS geometry) stopped at velocity in v0.13/v0.14. Its SPS files carry source and
receiver static corrections (-57..-41 and -58..-41 ms, totals -115..-82 ms), which assign_external_geometry writes
into sstat/gstat/tstat, and pick_velocity applies with SU `sustatic hdrs=1 sign=1`.

1. SU's sustatic resamples each trace at t + sign*tstat: with sign=1 an event at T appears at T - tstat. A SEG-Y/SPS
   static correction is the value added to the traveltime (T' = T + s; negative = earlier). With these negative
   statics, sign=1 moves every event about 100 ms LATER: the opposite of the correction.
2. Measured on the data (dev copy pol-dev32; first breaks at 50-400 m offset, one straight-line fit per shot, 251
   shots): median intercept raw 119 ms; with sign=1 215 ms; with sign=-1 22 ms. The datum correction should bring
   the near-offset intercept toward zero; only sign=-1 does.
3. v0.14 (recorded in results/poland_static_sign_experiment.json): sign=+1 validated 1 of 5 velocity locations,
   sign=-1 3 of 5.
4. Any file with sstat/gstat in its headers cannot be conditioned at all today: condition_gathers refuses because
   pick_velocity would apply the statics later.

## Rules

**S1 (acquisition statics).** Header source/receiver statics (sstat, gstat; tstat = sstat + gstat required, as
before) are applied once, at sort_cmp, in the SEG-Y sense T' = T + s (SU sustatic hdrs=1 sign=-1). The product
carries sstat = gstat = 0 and tstat = the applied total, so nothing applies them twice. Gate: the median near-offset
first-break intercept (first sample above a quarter of the trace maximum within the first second; 50-400 m offset;
one straight-line fit per shot) must move toward zero: |after| < |before|. If it does not, the statics are not
applied, the file is left uncorrected and the refusal says the file's sign convention contradicts SEG-Y. Files
without source/receiver statics are untouched (Viking: tstat 11 ms recorded as already applied, as before).

After S1, conditioning is available on such files like on any other.

## Protocol P14 (Poland, fixed)

import; assign_external_geometry (SPS/RPS/XPS); geometry_analyze; feasibility fldr 356; build_cmp (receiver spacing
25 m); sort_cmp (S1); kill_corrupt (refusal = no-op); pick_velocity (+ one refine on FAIL); stack 0; DMO (+ re-pick,
stack 1); residual statics (+ re-pick, stack 2); migrate phase_shift_smooth. dataset v032-poland.

Agent run (v032-polagent): the v0.29/v0.30 instruction, adapted to land (the agent may use the conditioning menu).

## Evaluation (no truth: completion, internal consistency, gates)

A. Regression: stack bytes Viking 200-CDP `181fc5ba…`, v2 (P7) `7374cb63…`, phase_shift migrations `59730242…`,
   `f8c90340…`; unit tests pass (including S1 on a synthetic with known statics, both directions).
B. Poland, P14: S1 PASS with the median intercept moving from about 119 ms toward zero; velocity: more valid
   locations than v0.14's sign=+1 branch (1 of 5), recorded against the D1 count; everything after that recorded
   without prediction (stack reliability, DMO, residual statics, migration gates, image).
C. The agent run is recorded without prediction: route, decisions, products.

Failure of v0.32: a regression byte change; S1 applying statics that move the intercept away from zero; a released
product with a non-finite or contradicted QC read as a pass; a budget overrun or false claim.
