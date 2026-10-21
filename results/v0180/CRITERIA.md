# v0.18.0 criteria (written before any code change)

Written 2026-09-23 against v0.17.0 (`results/v0170/RESULT.md`). Not edited after the first run.

Honesty note: the v0.17 run showed the supported depths of the two remaining C levels
(1.48 s) and of band noise 1.0x (1.60 s, a good stack). The threshold below was chosen
knowing those numbers; the first two ladders are therefore descriptive for v0.18, and
only the third held-out ladder (generated after this file) is a test.

## E1 velocity-support disclosure (report only)

`stack_cmp` attaches `velocity_support`: t_d = largest |offset| / direct-wave velocity
(R1's measured velocity, else 1492 m/s ASSUMED), T = record end, s = the shallowest
`supported_to_s` among the valid velocity locations. measured_fraction =
(s - t_d) / (T - t_d), clipped to 0-1: the share of the reflection window below the
last direct arrival whose velocity was measured rather than held constant.
Level PARTIAL when measured_fraction < 0.5 (less than half of that window rests on a
measured velocity; the same "most of" used by F1), else MEASURED. UNKNOWN when there is
no valid location or T <= t_d. Stack bytes unchanged.

## N1 window change

N1's lower window end becomes the record end T instead of s. Everything else in N1 is
unchanged (half-stack correlation, S/N = 2r/(1-r), ceiling < 0.9 -> NOISE_LIMITED).
The v0.17 window made N1 UNKNOWN exactly where noise shortened s.

## Matrix

A released stack that is not good, not corrected by its disclosed time_datum, but
carries N1 NOISE_LIMITED or E1 PARTIAL, is B-warn. A good released stack carrying
either warning is a false alarm (counted, not hidden).

## Predictions

| data | prediction |
|---|---|
| v2 0-2.6 s | stack `cbb46bd5...`; E1 MEASURED (s about 2.24 s, fraction about 0.7); N1 CLEAR |
| Viking | stack `181fc5ba...`; E1 MEASURED (s 5.92 s); N1 level uncertain (window now runs to 6.0 s) |
| held-out band noise 1.5x (C) | E1 PARTIAL (fraction about 0.07) -> B-warn |
| held-out 2 band noise 2.0x (C) | E1 PARTIAL -> B-warn |
| held-out 2 band noise 1.0x (A) | E1 PARTIAL (fraction about 0.17) -> a false alarm |

## Third held-out ladder (generated after this file)

`test_dataset/Marm2_ladder_heldout3/`, seeds 31 (band noise), 32 (statics), 33 (white):
band noise 0.5, 1.25, 1.75, 2.25 x; delay 45 ms; statics 8 ms; white noise 1.0 x.

| level | prediction |
|---|---|
| band noise 0.5x | released, good, no warning: A |
| band noise 1.25x | released; quality near 0.55; E1 PARTIAL likely; B-warn if not good, false alarm if good |
| band noise 1.75x | released or velocity-refused; if released, E1 PARTIAL: B-warn |
| band noise 2.25x | velocity-refused more likely (D); if released, B-warn |
| delay 45 ms | released, DISPLACED: B |
| statics 8 ms | released: A |
| white noise 1.0x | feasibility INCONCLUSIVE: E or D |

Targets: C = 0 on the third ladder. False alarms reported whatever they are.
