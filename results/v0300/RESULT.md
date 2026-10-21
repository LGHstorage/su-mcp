# v0.30.0 result: corrupt samples and non-finite measurements

Run 2026-09-29: fixed protocol P12 (v030-vikfull), the agent-operated run (v030-vikagent) and a regression run
(v030-viking, v030-v2n). Figures: `qc/v0300/fig15_viking_full_migration.png`, `qc/v0300/fig16_viking_zoom.png`.
Verdict: **v0.30 passes** (no failure condition met). A new problem is recorded below: the released full-line
migration is worse than the stack below about 2.5 s, and no rule said so.

## A. Regression

Viking 200-CDP stack `181fc5ba…`, its phase_shift migration `59730242…`; v2 (P7) stack `7374cb63…`, phase_shift
migration `f8c90340…`: identical. Reliability rule now "v0.30 N0+Q0+N2+W3+W4 / W2", both OK. Unit tests: 498 pass
(3 skipped without SU).

## B. Q0 on existing data

No corrupt trace on clean Marmousi2 v2, the 200-CDP Viking window or any of the five thirteenth-ladder levels. The
largest clean sample was 19x (Marmousi2) and 969x (Viking, raw SEG-Y) the median trace RMS, against the 10^6 limit.

## C. Full Viking line, P12

| item | v0.29 | v0.30 |
|---|---|---|
| Q0 | (none) | 1 corrupt trace, CDP 713, 3.4028e38; limit 4.9e11 (median RMS 4.9e5) |
| kill_corrupt | - | accepted: 1 trace (8e-6 of the file), all others byte-identical |
| stack 0 N1 | NaN read as CLEAR | r 0.929, S/N 26.4, ceiling 0.982 |
| DMO (D1) | NaN, refused | 0.939, accepted |
| stack 1 (after DMO) | - | r 0.881, ceiling 0.968, reliability OK |
| F3 vs 200-CDP control | 0.803 | stack 0 0.803 (stack 1 0.751) |
| phase_shift | M1 FAIL | M1 FAIL (0.582 / 0.501 / 0.470) |
| phase_shift_smooth | M1 FAIL | **released**: M1 0.849 / 0.654 / 0.503, M5 0.20, reliability OK |
| depth_pspi | Z2 refused | Z2 PASS; Z1 FAIL (third apex: focus 0.822 but peak 10 m off, tolerance 6 m) |

All C items met. Wall clock about 1 h 45 min, of which phase_shift_smooth 45 min and depth_pspi about 28 min.

## The agent-operated run

The agent stacked first, read the new Q0 warning on the stack ("1 corrupt trace at CDP 713 ... run kill_corrupt"),
killed it, re-picked, restacked (OK, r 0.929), chose DMO for the dip-dependent deep picks (accepted, 0.939), and
released phase_shift_smooth, arguing from M3 (lateral spread 0.57) that one median function would not do; its
phase_shift reference run failed M1, as it did in the fixed run. Its stack and migration are sample-for-sample the
same as the fixed run's (median trace correlation 1.000). In v0.29 the same agent needed four implausible numbers and
a hunt with 100% clip displays to find the sample; in v0.30 the stack's warning named it.

## New findings (not covered by any rule yet)

1. **The released full-line migration is worse than the stack below about 2.5 s.** Crossing migration noise fills
   2.5-5 s and horizontal banding appears at 5-5.5 s (fig 15, 16). M1 passed at 0.503 against 0.5, M2 is 0.11 / 0.15
   (the image changes almost completely for +-5% velocity; Marmousi2 0.87) and no rule turns that into a warning.
   Likely causes, to be tested: the deep picks of 3000-3400 m/s (the same ones that made Z2 refuse the depth image
   in v0.29) giving interval-velocity spikes that sumigps also uses; migration of multiples and deep noise; 53 Hz
   data on 12.5 m traces (steep noise aliases).
2. **The depth step is fixed at 5 m.** Right for Marmousi2 (6 Hz), too coarse for Viking (53 Hz: a quarter wavelet
   is about 6 m), which is why Z1 failed at the deepest apex. It should scale with the wavelength.
3. **Last writer wins.** A rejected migration run after a released one sets migration.completed to FAIL although the
   released product remains; stack_cmp overwrites the stack, so the pre-DMO stack disappears unless copied.
4. Q0 fires at stack time; nothing at import or sort looks at sample values.
5. The DMO gate tests preservation of flat events, not benefit; on this line DMO lowered half-stack r (0.93 -> 0.88)
   and the match to the 200-CDP control (0.80 -> 0.75) while reducing the lateral spread of deep picks.
