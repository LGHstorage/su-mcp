# v0.16.0 criteria (written before any code change)

Written 2026-09-23 against v0.15.0 and the Marmousi2 v2 degradation ladder
(`results/marm2_ladder/RESULT.md`). Not edited after the first v0.16 run; results
that differ are recorded as they are.

## Principle (unchanged from v0.15)

Nothing that is FAIL or UNKNOWN in v0.15 becomes PASS in v0.16. No gate is loosened
and no threshold is moved. v0.16 changes what the system says, not where it refuses.

## Why the time datum is disclosed and not gated

The ladder released stacks whose time axis was 50-100 ms late. The obvious fix, a
stricter R1 tolerance, is not available: the direct wave cannot tell a late clock
from a causal source wavelet whose energy peaks late. A correctly timed field record
with a minimum-phase airgun signature shows the same direct-wave lag as a zero-phase
record with a late clock, and a quarter-period refusal would refuse the first. That
is why R1 tolerates one period (a velocity-bias gate). What the system can do is
state the measured lag on the product, so the displacement is known, quantified and
correctable, instead of silent.

## D1 time-datum disclosure (report only)

`stack_cmp` reads `acquisition.time_zero_consistent` and attaches `time_datum` to its
result and to the `stack.completed` evidence:
- measured (R1 PASS or FAIL with an intercept): the direct-wave peak lag in ms, the
  dominant period, the lag in periods, and a level: WITHIN_RESOLUTION when
  |lag| <= a quarter of the dominant period (the vertical resolution, lambda/4), else
  DISPLACED, with a statement that events sit that much later than a zero-phase,
  shot-anchored reference and that a late clock and a causal wavelet cannot be told
  apart from the data;
- otherwise UNKNOWN, with the reason (R1 not measured, or direct wave not ROBUST).
`stack.completed` stays PASS in every case. Stack bytes do not change.

## F1 band-limited absence (feasibility)

`assess` measures the fraction of the gather's energy (mean removed, DC excluded)
inside the analysis band [band_low, band_high] and reports it as `analysis_band`.
When the verdict would be FAIL and less than half of the gather's energy lies in the
band, the verdict becomes INCONCLUSIVE: the absence was tested on a minority of the
record, so it is not evidence of absence in the record. The reason names the
fraction and keeps the in-band finding as a clause. 0.5 is "most of the record", not
a value chosen to separate any case. A FAIL -> INCONCLUSIVE change keeps the
manifest status non-PASS (UNKNOWN), so `build_cmp` still refuses.

## Regression predictions (new dataset ids `v016-*`; frozen results untouched)

| data | v0.15 | v0.16 prediction |
|---|---|---|
| Marm2 v2 0-2.6 s | PASS, stack `cbb46bd5...` | stack byte-identical; time_datum measured, -2 ms, WITHIN_RESOLUTION |
| Viking cdp1000-1199 | stack `181fc5ba...` | stack byte-identical; time_datum UNKNOWN (direct wave ABSENT) |
| Marm2 v1 as delivered 0-2.6 s | R1 FAIL, no stack | unchanged |
| old ladder delay 50/76/100 | released silently | released, byte-identical to v0.15, time_datum DISPLACED (+48/+74/+98 ms) |
| old ladder noise 1x/2x/4x, statics 20/40 | feasibility FAIL | INCONCLUSIVE (band fraction about 0.0001 < 0.5), still refused |
| A03 NOISE_ONLY, B02 L3 ABSENT (Viking spectrum, 4 ms) | FAIL | uncertain: depends on the Viking band fraction in 30-125 Hz. If it is < 0.5 these negative controls become INCONCLUSIVE (still refused) and that loss of negative evidence is reported, not tuned away |
| data001 tracf=1 | FAIL | uncertain for the same reason; reported either way |

A regression failure is any byte change in a released stack, any PASS that was not
PASS in v0.15, or any unit-test failure.

## Held-out ladder (generated after this file, never tuned on)

Source v2 0-2.6 s, protocol identical to the first ladder (feasibility fldr 63,
build_cmp 20 m, 5 locations, smute 1.5).
- delay 12, 30, 40, 60, 90, 110 ms
- band noise, exactly 4-16 Hz (generated at the record length, circular, no
  truncation), seed 11: 0.75, 1.5, 3 x reflection RMS
- white noise, flat to Nyquist, seed 13: 1, 4 x reflection RMS (full-band RMS)
- surface-consistent statics, seed 12: 5, 15, 30 ms total RMS

## Judgement matrix (defined here; applied to both ladders)

Quality = the truth match used in the ladder (median correlation with the ER
section, AGC, 0.7-2.4 s, best lag within 20 ms, CMP 640-1100). Good = at least 0.9
of the clean baseline (0.9 x 0.622 = 0.560). A level's data are usable when the
reference stack (clean-baseline picks on the degraded data, shifted back by the
disclosed or measured lag where one exists) is good.

| cell | meaning |
|---|---|
| A released, correct | released stack is good |
| B released, wrong, disclosed | released stack is not good, but shifting it by its own disclosed time_datum makes it good |
| C released, wrong, silent | released stack is not good and nothing the system reported corrects it |
| D refused, data not usable | a correct refusal |
| E refused, data usable | a conservative refusal |

Separately: **false claims** = feasibility FAIL on a ladder level (every level
contains reflections by construction, so a FAIL asserting informative absence is
false). The threshold 0.9 was fixed after the first ladder had been seen, so the
first ladder's matrix is descriptive; the held-out ladder's is a test.

## Held-out predictions (v0.16)

| level | prediction | cell |
|---|---|---|
| delay 12 | all PASS, released, WITHIN_RESOLUTION | A |
| delay 30 | all PASS, released; lag about 28 ms against lambda/4 about 29 ms, level uncertain | A or B |
| delay 40, 60, 90 | all PASS, released, DISPLACED | B |
| delay 110 | R1 PASS (about +108 < 114.5 ms); R2 uncertain; if released, DISPLACED | B, or refused (E) |
| band noise 0.75x | all PASS, released | A |
| band noise 1.5x | feasibility PASS (no added energy in 30-250 Hz); velocity PASS; reference about 0.52 | A or C |
| band noise 3x | feasibility PASS; velocity uncertain; reference about 0.43 (not usable). If released: the expected new blind spot | C, or D if velocity refuses |
| white noise 1x | feasibility not PASS, INCONCLUSIVE by F1; reference usable (about 5% of white-noise energy falls in 4-16 Hz) | E, honest |
| white noise 4x | feasibility not PASS; F1 outcome uncertain (added in-band energy may push the fraction over 0.5, leaving a FAIL); reference usable | E; false claim if FAIL |
| statics 5 | all PASS, released | A |
| statics 15 | feasibility uncertain (10 passed, 20 failed in ladder 1); if not PASS, INCONCLUSIVE; reference usable | A or E |
| statics 30 | refused at feasibility, INCONCLUSIVE; reference about 0.48 | D |

Predicted counts: C at most 1 (band noise 3x), false claims at most 1 (white 4x).
