# v0.17.0 criteria (written before any code change)

Written 2026-09-23 against v0.16.0 (`results/v0160/RESULT.md`). Not edited after the
first v0.17 run.

## Scope note: data001

data001 is the frozen negative control (fixed receiver array, fold 1; its manifest was
closed at v0.9.2 and it is refused at geometry/CMP as well as at feasibility). v0.16
recorded that F1 turns its tracf=1 feasibility FAIL into INCONCLUSIVE. That stays a
recorded observation. No v0.17 rule is designed around data001, and the v0.16 candidate
"compute F1 on the direct-wave spectrum to protect data001" is withdrawn: its only
motivation was data001. data001 is not re-run for v0.17.

## N1 signal-band S/N disclosure (report only)

`stack_cmp` measures the stack's own signal-to-noise from two half-stacks: within each
CMP of the NMO-corrected file, traces sorted by |offset| are dealt alternately into two
halves, each half is stacked, and the two half-stack traces are correlated over a window
from t_a to t_b.
- t_a = largest |offset| / direct-wave velocity: below it the direct wave has left every
  offset. The velocity is R1's measured direct-wave velocity when R1 measured one,
  otherwise 1492 m/s, marked ASSUMED.
- t_b = the shallowest `supported_to_s` among the valid velocity locations: below it the
  velocity is extrapolated.
- CMPs with fewer than 8 traces are skipped. r = median correlation.
- Stack S/N (power) = 2r / (1 - r). Correlation ceiling = sqrt(SNR / (1 + SNR)): the best
  correlation any reference could have with this stack, whatever the velocity.
- Level NOISE_LIMITED when the ceiling is below 0.9, else CLEAR. 0.9 is the same
  fraction that defines "good" in the judgement matrix; it is not fitted to any stack.
- UNKNOWN when the window is shorter than 0.2 s or fewer than 10 CMPs qualify.
Stack bytes do not change. `stack.completed` stays PASS.

## R2b scan-edge picks in the direct-wave zone (a loosening, stated as one)

v0.15 R2 invalidates a location for any supported pick on the edge of the velocity scan.
At t0 = 0.04 s with 200-2100 m offsets the hyperbola at 1400 m/s never separates from the
direct wave by more than one period; such a pick measures the direct wave, not a
reflection velocity, and cannot be "censored" in R2's sense. v0.17 exempts a supported
scan-edge pick from R2 when R1 measured the direct wave (velocity v_d, dominant period T)
and the pick's hyperbola is further than T from the direct wave at fewer than 65% of the
gather's offsets. Both quantities are the ones feasibility already uses
(`SEPARATION_FRACTION`, one period). Exempt picks are reported as `direct_wave_zone` and
do not invalidate. Without an R1 measurement (direct wave not ROBUST) nothing is exempt.
This can turn a FAIL into a PASS, which v0.15/v0.16 excluded; it is allowed here only for
this one reason, and every location still has to pass every other check.

## Judgement matrix, extended

As in v0.16, plus: a released stack that is not good, cannot be corrected by its
disclosed time_datum, but carries N1 level NOISE_LIMITED, is **B-noise (released, wrong,
warned)**. C stays "released, wrong, and nothing the system reported says so". A released
good stack that carries NOISE_LIMITED is a **false alarm**, counted separately.

## Regression predictions (new ids `v017-*`)

| data | prediction |
|---|---|
| Marm2 v2 0-2.6 s | stack `cbb46bd5...` identical; N1 level uncertain (the clean synthetic has no added noise, but residual moveout and stretch lower the half-stack coherence; if flagged it is a false alarm and reported) |
| Viking cdp1000-1199 | stack `181fc5ba...` identical (R1 UNKNOWN, so R2b cannot act); N1 reported with ASSUMED 1492 m/s |
| held-out statics 15 (`ho-statics15` data) | R2b exempts cdp 1048's 0.04 s pick; velocity PASS 5/5; released; reference 0.602, so cell A (was E) |
| held-out delay 110 | unchanged refusal: the 0.32 s / 1400 m/s pick separates from the direct wave at every offset |
| held-out band noise 1.5x (the remaining C) | N1 uncertain; B-noise if ceiling < 0.9 |

## Second held-out ladder (generated after this file)

`test_dataset/Marm2_ladder_heldout2/`, source v2 0-2.6 s, same protocol, new seeds
(band noise 21, statics 22, white noise 23):
delay 20, 70 ms; band noise (exact 4-16 Hz) 1.0, 2.0, 2.5 x; white noise 0.5, 2.0 x;
statics 12, 18 ms.

| level | prediction |
|---|---|
| delay 20 | released, WITHIN_RESOLUTION, A |
| delay 70 | released, DISPLACED, B |
| band noise 1.0x | released; N1 CLEAR or NOISE_LIMITED; A if good |
| band noise 2.0x | released or velocity-refused; reference about 0.49 (not usable); if released, B-noise if N1 flags it, else C |
| band noise 2.5x | as 2.0x, more likely velocity-refused (D) |
| white noise 0.5x | feasibility probably PASS; released; A |
| white noise 2.0x | feasibility INCONCLUSIVE; reference uncertain |
| statics 12 | released, A |
| statics 18 | feasibility uncertain; if it passes and the only velocity problem is a 0.04 s edge pick, R2b releases it |

Target: C = 0 on the second held-out ladder, false alarms reported whatever they are.
