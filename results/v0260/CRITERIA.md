# v0.26.0 criteria: dip moveout (DMO) behind a gate (written before any code)

Written 2026-09-28. Not edited after the first formal run; anything found before it goes in an addendum.
No new MCP tool (38): DMO is a new conditioning operation, so the worker picks it up without a restart.

## Why

The v0.24/v0.25 figures show the picked stacking velocities 10-15% above the vertical-column Vrms over the dipping
centre of Marmousi2, and deep picks that jump to 2650-2850 m/s where the truth is about 2150 m/s. For a dipping
reflector the NMO velocity is v/cos(dip), so a stacking velocity is not a migration velocity until the dip effect is
removed; the migration then over-migrates at depth. Dip moveout (DMO) removes the dip dependence of the moveout, the
textbook step between NMO and stack.

A development run on clean v2 (cloud replica, not held-out): NMO -> SU sudmofk -> inverse NMO, then the unchanged
velocity analysis, NMO, stack and migration. Median signed pick error against vertical Vrms (0.7 s to the supported
depth) 8.3% -> 2.1% (deeper than 1.6 s: 10.4% -> 4.5%); stack truth match 0.640 -> 0.695; phase-shift migration
against the migrated reference 0.536 -> 0.568.

On the user's question about the deepest pick: below a location's deepest supported pick the RMS velocity is held
constant (since v0.15), so the pick curve drops vertically. That is a disclosed assumption, not a measurement; holding
the RMS velocity implies an interval velocity that falls below the last pick. It is not changed in this version (the
supported depth reaches 2.24-2.52 s of a 2.6 s record on clean v2); it is reported (E1/E2) as before.

## Rule

**DMO (condition_gathers operation "dmo", solo, no parameters).**
- Needs velocity.validated PASS; uses that model.
- Chain: sunmo (the model, smute 1.5) -> susort offset cdp -> sudmofk -> susort cdp offset -> sunmo invert=1 (same model).
- sudmofk: cdpmin/cdpmax from the file; dxcdp = bin size x median cdp step (build_cmp evidence); noffmix = round(median
  shot spacing / bin size), at least 1; tdmo/vdmo = the lateral median RMS velocity every 0.1 s.
- Gate D1: laterally continuous flat reflections (every CMP; three t0 at 25/50/75% of the window below the last direct
  arrival; moveout from the model's v_rms at each CMP; 0.5 x RMS) are run through the chain with and without; the
  processed injection must correlate >= 0.9 with the injection (the preservation threshold of every menu operation).
  Flat events have no dip, so DMO must leave them unchanged; a wrong sort, spacing, velocity or inverse NMO does not.
- Accepted: the DMO gathers replace cmp_sorted and velocity, NMO and stack are invalidated (as every conditioning).
- Budgets: conditioning passes 2 -> 3, velocity analyses 4 -> 6 (DMO adds one conditioning pass and one velocity model).

sudmofk and susort become TRUSTED (susort stays ALLOWED for inspection as before).

## Protocol P8

1-6 as P7 (import ... datum_shift). 7 pick_velocity (+ refine once on FAIL). 8 export_product velocity_model
(output_name D_vel0.json); apply_nmo, stack_cmp; copy the stack to results/v0260/stacks/D_stack0.su.
9 condition_gathers [dmo]. If accepted: pick_velocity (+ refine once), export velocity_model as D_vel1.json, apply_nmo
(overwrite), stack_cmp (overwrite). 10 copy the stack to results/v0260/stacks/D_stack1.su. 11 residual_statics as P7
(stack 2 if accepted). 12 migrate_stack phase_shift.

## Evaluation

A. Regression (no DMO, P7 path): v2 stack bytes `7374cb63…`, Viking `181fc5ba…`; unit tests pass.
B. Clean v2 with DMO: DMO accepted; stack >= 0.66; |median signed pick error| < 4%; Q_mig >= 0.55. Viking with DMO:
   descriptive (no truth).
C. Eleventh held-out ladder, generated after the code is frozen, seeds 111-113: statics 12 ms + band noise 0.6x, white
   noise 0.8x, band noise 1.2x, delay 70 ms, clean line cropped to 102 shots (5 km). Predictions: DMO accepted on every
   level; stack after DMO >= stack before DMO - 0.01 on every level and higher on at least three; |median signed pick
   error| smaller after DMO on at least four; no C among the released stacks.

Failure of v0.26: any C in C; DMO lowering a released stack's truth match by more than 0.01; DMO refused on two or more
levels in C; a regression byte change; any budget overrun or false claim.

## Addendum (before the first formal run)

1. D1 reference. The chain includes a mute (sunmo smute 1.5) that the raw injection does not see, so the reference
   for D1 is the injection passed through sunmo -> sunmo invert=1 alone (same model, same mute), and preservation is
   measured as for every menu operation: corr(chain(data + injection) - chain(data), reference). The chain must also
   keep the (cdp, offset) trace order. Found while writing the operation, before any MCP run.
2. Development value on clean v2 (cloud replica, not held-out): D1 = 0.912, accepted; noffmix 4, dxcdp 10 m, vdmo
   1450-2201 m/s; stack truth match after DMO 0.696 (the manual experiment gave 0.695). The margin over 0.9 is small;
   the threshold is not changed.
