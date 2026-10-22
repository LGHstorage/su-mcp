# Second geological model: criteria

Written 2026-10-21, before the model, the shot records, the reference section, or the degraded copies exist. Not
edited after the first formal run. Anything found before that run goes in an addendum at the end.

## Purpose

All held-out ladders so far were made from one geological model (Marmousi2). This test runs the final system,
SU-MCP 0.33.3, without any change of code, threshold, or protocol, on a second synthetic line built from a different
geological model. It tests whether the outcome classes found on Marmousi2 carry over to new geology.

## Model B

Grid, acquisition, and modeling are those of the Marmousi2 line, so that only the geology changes: 801 x 351 cells of
10 m (8.0 km x 3.5 km), 2D constant-density acoustic, the same modeler (dev/marm2_oracle/acoustic_fd2d_v2.c, 8th order,
two-step sponge of 200 cells, S = 0.005), 10 Hz Ricker, recording from the wavelet peak, 126 shots 40 m apart,
96 receivers 20 m apart, offsets 200 to 2100 m, source depth 20 m, receiver depth 10 m, 1 ms modeling step, 2 ms
output, 2.6 s record. The trace headers are copied from the Marmousi2 v2 line.

Geology (written into dev/modelb/make_model.py before it is run):
- Water to 300 m depth, 1500 m/s.
- Three flat young layers above an undulating unconformity at about 800 m (1650, 1800, 1950 m/s).
- Below the unconformity, a sequence of eight layers from 2200 to 3900 m/s, with a thin 4000 m/s carbonate layer near
  2.1 km. The sequence is folded into an anticline centred at x = 2.5 km and truncated by the unconformity.
- A normal fault dipping 60 degrees to the right from x = 5.2 km at 600 m depth, with a throw of 200 m.
- A lateral velocity increase of 5 percent from the left to the right of the model in the layers below the
  unconformity.

## Reference and quality

The reference is the exploding-reflector zero-offset section of model B with the same half-derivative correction,
computed by dev/marm2_oracle/exploding_reflector.c as for Marmousi2. Quality is the measure of the paper (median trace
correlation at the best lag within 20 ms, 0.2 s gain, 0.7 to 2.4 s, CDP 640 to 1100).

Good threshold: 0.9 times the quality of the stack that the protocol releases on the clean model-B line. This is the
same definition as on Marmousi2 (0.9 of the clean quality), taken here from the final system because no earlier rule
set is run.

Usability: a level is usable when a reference stack reaches the good threshold. The reference stack applies the
velocity model picked by the system on the clean model-B line to the degraded data with the Seismic Unix sunmo and
sustack programs (dev/ablation/su_bin), after a recording delay is removed by its known lag. Other defects are kept.

## Degraded copies

Generated after this document, from the clean model-B line, with seeds 151 (band noise), 152 (statics), and 153
(white noise), by dev/modelb/make_ladder_b.py using the same functions as the Marmousi2 ladders (noise scaled to the
median reflection rms in 1.5 to 2.5 s, band 4 to 16 Hz, surface-consistent statics split equally between sources and
receivers).

| level | defect |
|---|---|
| clean | none |
| delay 60 | recording delay 60 ms |
| band 1.0 | band-limited noise 1.0 times the reflection rms |
| band 1.6 | band-limited noise 1.6 times |
| band 2.0 | band-limited noise 2.0 times |
| white 1.0 | white noise 1.0 times |
| statics 16 | surface-consistent statics 16 ms rms |
| statics 12 + band 1.0 | statics 12 ms rms and band-limited noise 1.0 times |

## Protocol (stack part of P13, unchanged)

import; geometry_analyze (trend_shots 20, water velocity 1500); assess_reflection_feasibility (fldr 63, water
velocity 1492, band 30 to 250 Hz, max_traces 400, run_sensitivity true); build_cmp (receiver spacing 20 m, reference
1800 m/s at 1.0 s, min fold 4); sort_cmp; condition_gathers [kill_corrupt] and [datum_shift] (a refusal is a no-op);
pick_velocity (the P13 arguments); refine_velocity once on FAIL; apply_nmo (smute 1.5); stack_cmp (stack 0);
condition_gathers [dmo]; if adopted, pick_velocity (refine once on FAIL), apply_nmo and stack_cmp (stack 1);
condition_gathers [residual_statics]; if adopted, pick_velocity (refine once on FAIL), apply_nmo and stack_cmp
(stack 2). The last released stack is scored. Migration is not part of this test.

## Classes

As in the paper. A material warning is a reliability WARN or a disclosed displacement of the time datum. A CAUTION
alone is not material. A good stack with no material warning is A, with one A*. A bad stack with a material warning
is Bn, without one C. A refusal is D when the level is not usable and E when it is.

## Predictions

| level | prediction |
|---|---|
| clean | A (defines the threshold) |
| delay 60 | lag disclosed and removed by datum_shift, then A |
| band 1.0 | A or A* |
| band 1.6 | A* or Bn |
| band 2.0 | Bn |
| white 1.0 | A or A* |
| statics 16 | residual statics adopted, A or A* |
| statics 12 + band 1.0 | A* or Bn |

## Failure

The test fails if any released stack is class C, if the clean line is refused or warned, if a usable level is
refused, or if the code, a threshold, or the protocol is changed after this document. Wrong predictions that do not
meet these conditions are reported and do not fail the test.

## Addendum 1 (2026-10-21, before the shot records were assembled and before any run)

- The reference stack for usability uses the first velocity model of the clean model-B run (exported as
  modelb-clean_vel0.json, picked before dip moveout), as the Marmousi2 reference used the first picks of the clean line.
  A recording delay is removed by the known delay.
- The export_product steps of P13 (vel0 after the first pick, vel1 after the re-pick, velF at the end) are kept, as in
  P13. They change no product.
- Dataset ids: modelb-clean, modelb-dl060, modelb-bn100, modelb-bn160, modelb-bn200, modelb-wn100, modelb-st16,
  modelb-st12bn.
