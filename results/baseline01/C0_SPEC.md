# Baseline study 01: C0 specification and A/B header allowlist (DRAFT, part of the freeze)

Written 2026-09-30 from the production code at v0.33.0 (sumcp/*.py as deployed; hashes go in CRITERIA.md at the
freeze). C0 runs the same code as C with `SU_MCP_GOVERNANCE=off` in a separate evaluation deployment. The
production server refuses to start with that setting.

## 1. Rule

A requirement or refusal is **mechanical** (kept in C0) when, without it, the program cannot run correctly at all:
a file, header, value or argument it needs is missing or invalid, or a resource budget is spent. It is **evidence**
(removed in C0) when it exists because the result would not be defensible. Budgets are resources, equal in all
conditions, and stay on.

## 2. Capability requirements (evidence.require)

| site | capabilities | C0 |
|---|---|---|
| analysis.py 96, 322, 361; tools.py 910 | dataset.imported, headers.parsed | kept (mechanical: the file and its headers were read) |
| stack.py 250 (pick_velocity), iterate.py 821 (condition_gathers), tools.py 770 (sort_cmp), iterate.py 963 (refine) | geometry.cmp_assigned | kept (a cdp header exists) |
| same sites | geometry.fold_valid | removed (fold grade) |
| cmp.py 70, 77 (build_cmp) | stack-track prerequisites, reflection.processing_feasible | removed (feasibility and geometry verdicts) |
| stack.py 435 (apply_nmo) | velocity.model_available | kept as "a velocity model file exists" |
| stack.py 435 | velocity.validated | removed |
| stack.py 793 (stack_cmp) | nmo.applied | kept as "an NMO file exists"; its PASS/stale status is removed |
| migrate.py 343, depth.py 147 | stack.completed | kept as "a stack file exists"; its status is removed |
| migrate.py 343, depth.py 147 | velocity.validated | removed |

## 3. Refusals inside tools

Kept (mechanical): argument and parameter validation (conditioning.py 43-57, 105-125, 209-220; migrate.py 337;
depth.py 144); CMP file not contiguous (iterate.py 94); cdp not on the line (iterate.py 103, stack.py 309); R1
gather not found (iterate.py 326); datum_shift with no measured lag at all (iterate.py 411: there is no number to
shift by); no bin size recorded (iterate.py 646, migrate.py 360, depth.py 170); fewer than 8 stacked traces
(migrate.py 364, depth.py 174); stack not starting at t = 0 (migrate.py 350, depth.py 153: sumigps assumes it); a
model with no location at all (migrate.py 356, depth.py 166); no spectrum above the noise floor (iterate.py 251);
inconsistent tstat != sstat + gstat (acqstatics.py 212: the statics cannot be applied unambiguously); a model older
than v0.19 (iterate.py 982); kill_corrupt with nothing to remove (iterate.py 849, a no-op); budgets (stack.py 254,
iterate.py 826, 978, 986); the obsolete header-statics ordering check (iterate.py 833).

Removed (evidence): datum_shift lag inside a quarter period (iterate.py 415: the shift is applied); residual
statics and DMO without a validated velocity (iterate.py 472, 641: the current model is used); Q0 corrupt-trace
refusals (iterate.py 852, migrate.py 316); refine only after a velocity FAIL, and not after a time-zero FAIL, and not
when no location failed (iterate.py 967, 971, 992); depth Z2 (depth.py 199); depth_convert requiring a released M6
migration (depth.py 159: kept only as "a time-migration file exists").

## 4. Adoption

Every gated decision adopts its product in C0: the conditioning injection gate, DMO (D1), residual statics (RS2),
kill_corrupt (K0), acquisition statics S1 (applied in the SEG-Y sense without the intercept check), velocity
location grading (every analysed location's function is used; no location is omitted as invalid), refine (re-picks
every analysed location with a 5-CMP supergather and adopts the result), migration M1 and depth Z1 (always
released), B1 demotion rules (not applied).

## 5. Reporting

C0 tool results carry products and ordinary execution status only (run id, output paths, sizes, elapsed time,
counts of traces and CMPs, the velocity functions themselves). Removed from every result: reliability and quality
levels, warnings and their reasons, capability statuses, gate values and verdicts, evidence records, notes that
evaluate a result, per-location validity and problems, time-datum and sample-check reports, feasibility verdicts.
The scrubbing is an allowlist of returned keys per tool, not a blocklist. Tools whose output is only evidence
(assess_reflection_feasibility verdict, dataset_manifest capabilities, survey_overview) return raw measurements only
(for example candidate event times and velocities) or are not offered; the choice is fixed at the freeze.

## 6. A/B header allowlist

The keys the current code writes into products or its own working copies: cdp, offset (build_cmp repair); sx, sy,
gx, gy, offset, scalco, counit, sstat, gstat, tstat (assign_external_geometry, acquisition statics); fldr, tracf,
cdp (the surface-consistent index copy for suresstat). A and B may write exactly these keys with sushw or suchw;
every write is logged.

## 7. Decisions

1. Evidence-only tools stay available in C0 and return raw measurements only (decided 2026-09-30).
2. The per-tool key allowlist is sumcp/governance.py (SAFE_KEYS, PASS_THROUGH and the per-tool extractors);
   its hash is frozen with the code.
