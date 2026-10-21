# v0.24.0 criteria: post-stack time migration behind a gate (written before any code)

Written 2026-09-28. Not edited after the first formal run; anything found before it goes in an addendum.
This version adds one MCP tool (`migrate_stack`, 38 tools), so the formal evaluation needs a server restart.
Everything up to stack_cmp is unchanged (no stack byte changes).

## Why

The user asked for migration after the stack pipeline stabilised. The stack is a zero-offset section with
diffractions and mispositioned dips; time migration collapses them. Migration is also the step where a wrong
velocity type (RMS given as interval), a wrong trace spacing or a wrong time origin produce a plausible-looking
image, so it gets a gate like every interpretive step before it.

## Tool

`migrate_stack(dataset_id, method, overwrite)`: post-stack phase-shift time migration (SU sumigps), reachable only
through this tool (sumigps becomes TRUSTED, never ALLOWED).

- Prerequisites: stack.completed PASS and velocity.validated PASS; the stack starts at t = 0.
- Velocity: v_rms(x, t) exactly as sunmo used it (linear in t between control points at each valid location,
  constant below the last; laterally linear in 1/v^2 between locations, constant beyond the ends), converted to
  interval velocity by Dix on the sample grid.
- method "phase_shift": one v_int(t), from the lateral median of v_rms(t).
- method "phase_shift_blend": one migration per valid location with that location's v_int(t); each output trace is
  the linear blend (in cdp) of the two bracketing locations' migrations, the nearest one beyond the ends.
- Trace spacing dx = bin size x median cdp step, from build_cmp's evidence. Side taper 10 traces, padding 50% of
  the trace count.

## Gates and disclosures

**M1 (impulse gate).** Three synthetic diffraction hyperbolae (Ricker at the stack's dominant frequency, apexes at
25/50/75% of the cdp range and 30/50/70% of the record time, curvature from v_rms at the apex) are migrated alone
with the same method and velocities. Each must focus: at least 50% of the migrated energy within +-2 traces and
+-12 samples of its peak, and the peak within 1 trace and a quarter period of the true apex. On a synthetic line
(v_int 1500-3500 m/s) the correct setting focused 0.59-0.89; RMS velocity given as interval focused 0.06-0.36 and a
doubled trace spacing 0.06-0.08, with apexes displaced. FAIL: migration.completed FAIL, product kept for audit only.
Migration is linear, so the injection-only test checks the same operator the data sees.

**M2 (velocity sensitivity, report).** The stack is also migrated with v x 0.95 and v x 1.05; the median per-trace
correlation of each with the base migration (below the last direct arrival) is reported: how much the image
depends on a 5% velocity error.

**M3 (lateral variation).** The spread (max - min) / median of v_rms across the valid locations, maximum over the
supported times, is reported. With method "phase_shift" and spread > 0.10 the product carries a quality WARN
("1D migration velocity for a laterally varying model").

**Inheritance.** The migrated product carries the stack's reliability verdict (its quality and provenance reasons)
plus M3; it never has less disclosure than the stack it came from.

## Evaluation (formal run via MCP after restart; protocol P6 = P5, then migrate_stack with each method)

Reference image: the exploding-reflector zero-offset section (the stack reference) migrated with the true
vertical-column v_rms at every 10th cdp, blended the same way, computed by the evaluation harness (its own code).
Q_mig = median per-trace AGC correlation (best lag +-20 ms, 0.7-2.4 s) of a migrated product with the reference
image; Q_unmig = the same for the unmigrated stack against the same reference image.

A. Regression: stack bytes Viking `181fc5ba…`, v2 default `7374cb63…`; unit tests pass.
B. Clean v2: M1 PASS for both methods; Q_mig > Q_unmig for both. The default method is the one with the higher Q_mig
   on clean v2 in a development run before the formal run (recorded in an addendum; clean v2 only).
C. Viking: M1 PASS; M2 and M3 reported (no truth).
D. Ninth held-out ladder, generated after the code is frozen, seeds 91-93: statics 15 ms, band noise 1.0x, white
   noise 1.0x, delay 80 ms, statics 15 ms + band noise 0.8x. Predictions: M1 PASS on every released stack;
   Q_mig > Q_unmig on every stack that is good (unmigrated quality >= 0.560); every migrated product carries at
   least its stack's warnings.

Failure of v0.24: M1 FAIL on clean v2 or on a good stack; Q_mig <= Q_unmig on clean v2 for the default method; a
regression byte change; a migrated product with less disclosure than its stack; any budget overrun or false claim.

## Addendum (before the formal run; from a development run of clean v2 in a cloud replica)

The cloud replica reproduced the device's v2 default stack sample for sample (only the byte order differs).

1. M1 windows scale with the dominant period. The clean v2 stack's dominant frequency is 5.8 Hz; the fixed
   +-12 samples / +-2 traces (written for 20 Hz) held only part of a correctly focused wavelet, and the correct
   operator scored 0.20-0.47. The windows are now +-T/2 in time and +-v_rms*T/4 laterally (identical to the old ones
   at 20 Hz, 2 ms, 10 m, 1800 m/s), searched over +-max(0.3 s, 2T) and +-max(40, 4x) traces; the peak tolerance is a
   quarter period and max(1, half the lateral window) traces. With them, on clean v2: correct setting 0.78-0.87 (PASS);
   RMS given as interval, dx x2, dx x0.5, v x0.8 and v x1.2 all FAIL (at least two apexes below 0.5 or displaced).
2. Default method: "phase_shift". Development Q_mig on clean v2 against the migrated reference: phase_shift 0.536,
   phase_shift_blend 0.468; unmigrated stack 0.222 (the unmigrated ideal ER section scores 0.264, so migration
   changes the image a lot). M3 is kept as written: on Marmousi2 the default therefore carries an M3 quality WARN
   (spread 0.41), although it is the better of the two.
