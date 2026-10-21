# v0.29 criteria: the full Viking Graben line (written before any run)

Written 2026-09-29. No code change: the system is v0.28.1 as deployed (sumcp/config.py VERSION 0.28.1), frozen for
this run. Not edited after the first formal run; anything found before it goes in an addendum.

## Why

Every field result so far comes from 200 CMPs of the Viking Graben line (cdp1000_1199.segy, 2.5 km). The whole line
(test_dataset/VikingGraben/paracdp.segy: 120,120 traces, about 2000 CMPs x 60 fold, 6 s at 4 ms, 750 MB) has never
been processed. It tests three things the 200-CMP window cannot: scale (every step on 120k traces), lateral
variation over some 25 km, and migration aperture on a line long enough for M5 to pass. There is no truth for field
data, so this run is judged by completion, internal consistency and the system's own QC, and the image is shown as
it comes out.

## Two runs

**R1, fixed protocol P11** (dataset v029-vikfull). P10 in its Viking form: import, geometry_analyze, feasibility at
cdp 1100, build_cmp (25 m), sort_cmp; no datum shift (no direct wave on this line, as before); pick_velocity (+ one
refine on FAIL); export vel0; NMO, stack (stack 0); DMO; re-pick, export vel1, NMO, stack (stack 1); no residual
statics (marine, as before); migrate phase_shift, phase_shift_smooth and depth_pspi; export velF. Every call as a job.

**R2, agent-operated** (dataset v029-vikagent). One operator agent with the same tools and one instruction: produce
the most defensible time-migrated section of this line, using the system's own QC to decide what to do (conditioning
menu, DMO, residual statics, refine), within the budgets the system enforces, without any reference image or
external velocity. It must record, before every conditioning or re-pick decision, what QC it read and why it chose.
It may not repeat a step to get a better number (the system's budgets and dataset ids forbid it anyway).

## Checks (predictions)

F1 scale: every step of R1 completes as a job within the 3600 s step limit; at most one infrastructure retry per step.
F2 velocity: D1 analyses 15 locations (the cap); the model validates with K1 (5 of 15) and K2.
F3 consistency: over CDP 1000-1199 the R1 stack 0 matches the frozen 200-CMP control stack (`181fc5ba…`, same traces,
   different velocity model) at a median per-trace correlation >= 0.8.
F4 aperture: M5 OK on the R1 migrations (edge fraction <= 0.5).
F5 DMO: accepted on R1 (D1 >= 0.9, trace order kept).
F6 recorded without prediction: M1 on phase_shift_smooth after DMO (on the 200-CMP window it failed after DMO), Z1 on
   depth_pspi, stack reliability, the R2 decisions and how R2's section compares with R1's.

Failure of v0.29: a step that cannot complete at this scale (a real limit, not an infrastructure hiccup); a released
product without its evidence record; F3 below 0.6 with no warning on the stack; a budget overrun; a false claim.
Missing F2, F4 or F5 is a result to explain, not a failure.
