# v0.31.0 criteria: a migration velocity the picks can carry, stability by window, depth step, bookkeeping

Written 2026-09-29 before any code. Not edited after the first formal run; anything found before it goes in an
addendum. No new MCP tool (the worker picks up the code; docstrings show after a restart).

## Why (development, cloud, not held-out)

The v0.30 full-line Viking migration was worse than the stack below about 2.5 s (crossing noise, banding at 5-5.5 s)
while M1 passed at 0.503. On the stack of CDP 250-1100 (cloud copy of v030-vikfull stack 1, its final model):

| migration velocity | M2 stability (x0.95 / x1.05), 0.6-2.5 / 2.5-4 / 4-5 / 5-6 s |
|---|---|
| M6 as released | 0.98 / 0.07 / 0.00 / 0.04 |
| M6, then v_rms smoothed over 0.5 s in time before Dix | 0.98 / 0.79 / 0.55 / 0.40 |
| M6, frequencies above 30-40 Hz removed | 1.00 / 0.55 / 0.08 / 0.09 |

The image with the time-smoothed velocity keeps the reflectors and loses the crossing noise (fig in the addendum when
produced). The M6 interval velocities reach 5000-6300 m/s at 5.3-5.9 s (CDP 692-1141): Dix of a piecewise-linear
v_rms turns every kink between control points into an interval-velocity step, and at 53 Hz those steps scramble the
image. A velocity picked at control points 0.3-0.6 s apart carries no interval information finer than that spacing.

On clean Marmousi2 v2 with its true reference, smoothing v_rms over each location's control-point spacing (0.28 s)
before Dix: DMO stack 0.632 -> 0.628 (deep 0.587 -> 0.599); the no-DMO stack 0.553 -> 0.528.

## Rules

**M7 (migration interval velocity).** For phase_shift_smooth, depth_convert and depth_pspi, each location's (M6)
v_rms is smoothed in time with a boxcar as long as the median spacing of that location's control points before Dix.
phase_shift and phase_shift_blend are unchanged.

**M8 (stability by window, quality).** M2's two extra migrations are scored in 1 s windows from the last direct
arrival; a migration carries quality WARN "M8 image unstable to +-5% velocity below t s" when the median correlation
in a window (the lower of x0.95 and x1.05) is below 0.5, naming the first such window. Reported for every window.

**Z5 (depth step).** dz = min(5 m, floor(v_min / (8 f_dom))) and at least 1 m, v_min the smallest M7 interval
velocity below the last direct arrival and f_dom the stack's dominant frequency (a quarter of the shortest wavelet
length in depth, Z1's own tolerance). Marmousi2 (6 Hz) keeps 5 m.

**B1 (bookkeeping).** A rejected migration or depth run no longer turns migration.completed / depth.completed from
PASS to FAIL when a released product of another method exists; the attempt is appended to the capability's
"attempts" list. stack_cmp with overwrite keeps the previous stack as results/<id>_stack.v<k>.su.

**Q0 earlier.** sort_cmp runs the Q0 sample check on its output and returns and records it (no refusal there).

## Protocol P13

P12 of v0.30 (import ... kill_corrupt ... DMO ... re-pick), then migrate phase_shift, phase_shift_smooth, depth_pspi.
Marmousi levels: the P10 path (datum shift, DMO, residual statics) with the same three migrations.

## Evaluation

A. Regression: stack bytes Viking 200-CDP `181fc5ba…`, v2 (P7) `7374cb63…`; phase_shift migrations `59730242…`
   (Viking) and `f8c90340…` (v2); unit tests pass.
B. Clean v2 with DMO (P13): Q_mig(phase_shift_smooth) >= 0.61 and >= 0.58 in 1.4-2.4 s; no M8 warning.
C. Full Viking line (P13, v031-vikfull): phase_shift_smooth released; its M8 stability in the 2.5-3.5 and 3.5-4.5 s
   windows >= 0.5; depth_pspi Z1 PASS with Z5's step. Recorded: which windows M8 warns on; the image.
D. Fourteenth held-out ladder, generated after the code is frozen, seeds 141-143: statics 6 ms + band noise 0.8x,
   white noise 0.6x, band noise 1.4x, delay 30 ms. P13. Predictions: Q_mig(phase_shift_smooth) >= Q_mig(phase_shift)
   - 0.01 on every level with DMO accepted and six or more valid locations, higher on at least three; no M8 warning on
   any Marmousi level; no C among released stacks.

Failure of v0.31: a regression byte change; B, C or D missed; a C; a budget overrun or false claim.
