# v0.28.0 criteria: depth imaging, and two diagnoses that change nothing (written before any code)

Written 2026-09-28. Not edited after the first formal run; anything found before it goes in an addendum.
No new MCP tool (38): depth imaging arrives as two new migrate_stack methods, so the worker picks it up without a
restart (the running server's docstring lists them only after a restart).

## Diagnoses carried over from v0.27 (development, cloud replica of clean v2; no rule change)

1. Short lines. The full-line stack scores 0.624 over the CDPs of the 2.0 km crop; the crop's own stack 0.508; the
   crop stacked with the full line's velocity model 0.526. Inside and outside the crop's analysed span score alike
   (0.517 / 0.504). The loss is acquisition (fold and illumination at the line ends), not velocity, so no velocity
   rule can recover it. W4 stays as it is. M6 with five or fewer locations stays as it is (mixed evidence in v0.27).
2. Deep picks. Smoothing the stacking velocity like the migration velocity (M6) lowers the DMO stack of clean v2 from
   0.696 to 0.651, and around CDP 843 from 0.618 to 0.606: the 2750 m/s deep pick at CDP 843 is the velocity that
   stacks best there, and the wrong one to migrate with. Stacking and migration velocities differ in the faulted
   centre; v0.27 already migrates with the smoothed field. The picking is not changed.

## Depth imaging: development numbers (clean v2, DMO stack of v0.26/0.27, cloud)

Reference: the exploding-reflector section migrated in depth by SU sumigpspi with the true vp(x, z) (10 m).
Match = median per-trace AGC correlation, best lag within +-40 m, CDP 640-1100.

| depth image | 0.5-1.2 km | 1.2-2.4 km | 0.5-2.4 km |
|---|---|---|---|
| M6 time migration, depth-converted with the M6 interval velocity | 0.619 | 0.304 | 0.262 |
| sumigpspi with the M6 interval velocity v(x, z) | 0.625 | 0.314 | 0.242 |
| sumigpspi with the true vp(x, z) (bound) | 0.863 | 0.706 | 0.722 |

Depth is far less forgiving than time: a 3% velocity error moves a reflector at 2 km by 60 m, beyond the lag
window. What the picked velocity supports is depth to within a stated tolerance. Depth of the zero-offset time t,
z(t) from the M6 interval velocity, against the true vertical-column depth, 0.7 s to each location's supported
depth, 0.1 s steps: with DMO, median +1.4%, 83% within +-5%, 58% within +-3%; without DMO (v0.25 path), median
+7.6%, 24% within +-5% (stacking velocities on dipping events exceed migration velocities, reflectors go deep).

## Rules

**Methods.** migrate_stack gains "depth_convert" and "depth_pspi". Both use the M6 velocity (smoothed v_rms per
location, 1/v^2 linear in cdp), Dix to interval velocity on the time grid, z(t) = sum(v_int dt / 2) per trace, and a
5 m depth step. Output results/<id>_mig_<method>.su with ns = nz, d1 = dz (m) and the dt field = dz in mm.
- depth_convert stretches the released M6 time migration (artifact migration_phase_shift_smooth; refused without
  it) trace by trace to depth. It inherits M1 from that migration.
- depth_pspi migrates the stack with SU sumigpspi (TRUSTED only) and the interval velocity v(x, z).

**Z1 (depth impulse gate, depth_pspi).** Three diffractions (the M1 apexes) built in time with the lateral median
v_rms, depth-migrated with the lateral median v_int(z) by the same program, must focus as M1 requires, in depth: at
least half the energy within half a wavelet length (v T / 2) of depth and v T / 4 laterally of the peak, the peak
within a quarter wavelet length of z(t0) and half the lateral window of the apex. Otherwise the product is kept for
audit and not released. RMS read as interval, a wrong trace spacing or a wrong depth step fails it.

**Z2 (interval velocity).** Refused when any interval velocity between the last direct arrival and a location's
supported depth lies outside 1000-7000 m/s (slower than any water-saturated sediment, faster than any crustal rock):
Dix has blown up and depth would be fiction.

**Z3 (depth tolerance, report).** Every depth product states its depth tolerance: +-5% of depth (the M2 velocity
scale), within the supported window, and deeper than that only as extrapolated.

**Z4 (warning).** Quality WARN on a depth product when no DMO pass was accepted on the dataset: without DMO the
depth of dipping reflectors is biased deep (development: median +7.6%).

Time-migration methods are unchanged.

## Protocol P10

P9 of v0.27 (import ... DMO ... residual statics, then migrate phase_shift_smooth), then migrate_stack
"depth_convert" and "depth_pspi". Viking and the no-DMO v2 path (P7) also run both depth methods.

## Evaluation

Depth coverage C5 = share of (valid location, t) pairs, t from 0.7 s to the location's supported depth in 0.1 s
steps, whose z(t) is within +-5% of the true vertical-column depth (evaluation only).

A. Regression: stack bytes Viking `181fc5ba…`, v2 (P7) `7374cb63…`; phase_shift migration of that stack `f8c90340…`;
   unit tests pass, including Z1 failing RMS-as-interval and doubled trace spacing on a synthetic.
B. Clean v2 with DMO: both depth products released (Z1 PASS, Z2 PASS); C5 >= 0.7; depth match reported.
C. v2 without DMO (P7 path): both depth products carry Z4 WARN.
D. Thirteenth held-out ladder, generated after the code is frozen, seeds 131-133: statics 8 ms + band noise 1.0x,
   white noise 1.0x, band noise 0.6x, delay 40 ms, clean line cropped to 90 shots. P10 on every level. Predictions:
   Z1 PASS everywhere; on every level with DMO accepted and six or more valid locations, C5 >= 0.6; pooled over those
   levels C5 >= 0.7; no C among the released stacks.

Failure of v0.28: a C in D; C5 below 0.7 in B or pooled in D, or below 0.6 on a qualifying level; Z1 FAIL on a
correct setting or PASS on a wrong one in the unit tests; a missing Z4 in C; a regression byte change; any budget
overrun or false claim.

## Addendum (before the first formal run)

1. P10 ends with export_product(velocity_model, output_name "<id>_velF.json"): C5 is computed from the model the depth
   products were made with (the last validated one), and the evaluation needs it outside work/.
2. Production code on the cloud replica of clean v2 (DMO): depth_convert and depth_pspi released, Z1 foci 0.894 /
   0.862 / 0.936, Z2 PASS; depth match 0.5-2.4 km 0.237 (convert) and 0.264 (pspi) against the development 0.262 /
   0.242 (5 m product resampled to the 10 m reference). The depth reference is saved as
   results/migration_reference/er_depth_true_pspi.npz (cdp0 400, dz 10 m, nz 300).
