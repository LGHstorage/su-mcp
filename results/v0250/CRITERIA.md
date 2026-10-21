# v0.25.0 criteria: where migration can be trusted along the line (written before any code)

Written 2026-09-28 after v0.24.0 passed its criteria. Not edited after the first formal run; anything found before it
goes in an addendum. No new MCP tool (38 tools): the change is inside migrate_stack, so the worker picks it up without
a restart. Stack pipeline unchanged.

## What v0.24 left

1. M3 (lateral velocity spread > 10% warns the 1D method) warned every default migration of Marmousi2, although the
   1D method was the better one on 4 of 6 lines. It states a fact about the model, not about the image.
2. The Viking migrations (2.5 km line, 6 s record) are dominated below about 2.5 s by crossing "smiles": the migration
   operator wants a wider aperture than the line has, so energy from the line ends sweeps across the section. M1
   cannot see this (it tests the operator on diffractions placed inside the line) and nothing warned.
3. A development check on clean v2 (not held-out): scaling the migration velocity by 0.85-1.05 and choosing the scale
   that maximises image focus (varimax) picks 0.90, while the truth match is best at 1.00 (phase shift: 0.450 at 0.90,
   0.536 at 1.00). A focus-driven velocity scan is therefore not adopted.

## Rules

**M3 becomes a report.** The lateral spread is still computed and disclosed; it no longer adds a quality reason.

**M5 (aperture).** For each output trace at distance d from the nearer line end and each time t, the migration is
edge-affected when d < A(t) = v(t) * t / 2 * tan(30 deg), with v the lateral median of v_rms. The edge-affected fraction
f is the share of (trace, t) cells so affected between the last direct arrival and the record end. f is reported;
f > 0.5 adds the quality reason "M5 migration aperture truncated by the line ends over x% of the section". 30 degrees
is a conventional minimum aperture for time migration, not a fitted value. Expected: clean Marmousi2 v2 f ~ 0.40 (OK),
Viking f ~ 1.0 (WARN).

Everything else as v0.24 (method, velocity, M1, M2, inheritance). Migrated samples are unchanged.

## Protocol P7 = P6 of v0.24

## Evaluation

Migration gain g = Q_mig - Q_unmig, both against the migrated reference image (as in v0.24), phase_shift method.

A. Regression: stack bytes (Viking `181fc5ba…`, v2 `7374cb63…`) and migrated samples identical to v0.24 for v2 and Viking
   (both methods). Unit tests pass.
B. Viking: M5 WARN. Clean v2: M5 OK and reliability OK (no M3 reason any more).
C. Tenth held-out ladder, generated after the code is frozen: the clean v2 line cropped to 27, 52, 77 and 102 shots
   centred on shot 63 (CMP spans about 2.0, 3.0, 4.0 and 5.0 km; expected f about 1.0, 0.8, 0.6 and 0.48), and the full
   line with band noise 0.8x (seed 101). P7 on every level. Predictions: M5 WARN on the 2.0, 3.0 and 4.0 km crops, OK on
   the 5.0 km crop and the full noisy line; every M5-OK product has g >= 0.15; the smallest g among M5-OK products is
   larger than the largest g among M5-WARN products.

Failure of v0.25: a migrated-sample or stack byte change in A; an M5-OK product with g < 0.10; an M5-WARN product
with a larger g than some M5-OK product; any budget overrun or false claim.
