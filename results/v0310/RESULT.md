# v0.31.0 result: migration velocity the picks can carry (M7), stability by window (M8), depth step (Z5), bookkeeping (B1)

Run 2026-09-29 by four operators (P13) on the full Viking line, clean Marmousi2 v2, the fourteenth held-out ladder
and the regression sets. Evaluation: `dev/marm2_ladder/evaluate_v031.py` -> `results/v0310/eval_v031.json`. Figure:
`qc/v0310/fig17_viking_m7.png`. No rerun, no tuning.

**Verdict: v0.31 fails on one prediction** (C: depth_pspi Z1 PASS on the full Viking line with Z5's step; it failed).
Every other prediction was met, and the problem that motivated the version (the full-line migration below 2.5 s)
is solved.

## A. Regression

Viking 200-CDP stack `181fc5ba…` and phase_shift migration `59730242…`; v2 (P7) stack `7374cb63…` and phase_shift
migration `f8c90340…`: identical. 504 unit tests pass. New: M8 now warns on the 200-CDP Viking phase_shift migration
(stability 0.28 in 2.2-3.2 s), which already carried M5 WARN.

## B. Clean Marmousi2 v2 (DMO)

phase_shift_smooth: Q_mig **0.628** (>= 0.61), 1.4-2.4 s **0.599** (>= 0.58); v0.27-v0.30: 0.632 / 0.587. No M8
warning (stability 0.87 / 0.95). Met.

## C. Full Viking line (v031-vikfull)

| | phase_shift | phase_shift_smooth (M6 + M7) | depth_pspi |
|---|---|---|---|
| released | no (M1 0.582 / 0.501 / 0.470) | **yes** (M1 0.695 / 0.571 / 0.781) | no (Z1 FAIL) |
| M2 (x0.95 / x1.05) | 0.091 / 0.065 | **0.831 / 0.831** | - |
| M8 by 1 s window from 2.17 s | 0.12 / 0.02 / 0.02 / 0.05, WARN below 2.2 s | **0.85 / 0.76 / 0.62 / 0.57**, no warning | - |
| reliability | WARN (M8) | OK | - |

- The released section keeps the reflectors to 5.5 s without the crossing noise and banding of v0.30 (fig 17).
  M7 smoothed each location over 0.64 s (its control-point spacing).
- The criterion named the windows 2.5-3.5 and 3.5-4.5 s; M8's windows start at the last direct arrival (2.17 s).
  Every M8 window overlapping 2.5-4.5 s scored >= 0.62. Recorded as met, with this mismatch disclosed.
- **depth_pspi missed:** Z5 set dz = 4 m (v_min 2050 m/s, 52.8 Hz). Z1 failed at the deepest apex: focus 0.788
  (fine) but the peak 8 m (two samples) from the predicted depth, against a tolerance of a quarter wavelet length,
  about 6 m at 53 Hz. The depth gate is too tight to be met with a 4 m step at this frequency, or the depth error of
  the lateral-median velocity is real at this scale; the run cannot tell which. Not changed after the run.
- B1: migration.completed stayed PASS with the rejected phase_shift listed under attempts; the pre-DMO stack was kept
  as results/v031-vikfull_stack.v1.su. Q0 at sort_cmp named CDP 713 before any processing; kill_corrupt as in v0.30.

## D. Fourteenth held-out ladder (seeds 141-143)

| level | stack 0 -> 1 | Q_mig phase_shift (deep) | Q_mig smooth (deep) | M8 | class |
|---|---|---|---|---|---|
| statics 6 ms + band 0.8x | 0.615 -> 0.670 | 0.547 (0.452) | **0.627 (0.578)** | no warning | A |
| white 0.6x | 0.632 -> 0.674 | 0.520 (0.441) | **0.573 (0.559)** | no warning | A~ |
| band 1.4x | 0.551 -> 0.638 | 0.578 (0.451) | **0.622 (0.568)** | no warning | A |
| delay 30 ms | 0.637 -> 0.635 | 0.506 (0.413) | **0.542 (0.539)** | no warning | A |

Smooth >= phase_shift - 0.01 on all four and higher on all four (+0.04 to +0.08; deep +0.09 to +0.13). No M8 warning
on any Marmousi dataset. No C. Met.

## Findings

1. Depth imaging of high-frequency field data needs a second look at Z1 (tolerance vs depth step) before any rule
   change; the time-migrated section is the product for Viking.
2. The 30 ms delay was not corrected: R1 measured +28 ms, inside a quarter period (29 ms), so datum_shift refused.
   That is the rule as written; DMO then did not raise the stack (0.637 -> 0.635).
3. depth_pspi reports neither M2, M8 nor M5 in its result.
