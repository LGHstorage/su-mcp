# v0.15.0 success criteria (written before any code change)

Written 2026-09-23 against v0.14.0 (226 tests pass, 22 skipped on the Linux VM).
These criteria are not edited after the first v0.15 run. A result that differs is
recorded as it is.

## Principle

v0.15 only adds refusals and information. No capability that is FAIL or UNKNOWN
under v0.14 may become PASS under v0.15, no existing threshold is changed, and no
tolerance is chosen by looking at which value separates the Marmousi2 cases.
Every new tolerance is an existing quantity: one dominant period, one velocity
scan step, the edge of the velocity scan, MIN_SUPPORTED_POINTS.

## Rules

R1 time-zero consistency (new capability `acquisition.time_zero_consistent`).
Measured by `assess_reflection_feasibility` only when the direct wave is ROBUST
at the flattening velocity. The direct wave is flattened at velocities within
5% of that velocity; the lag of the envelope peak of the trace-normalised stack
is the time-zero intercept. PASS if |intercept| <= one dominant period of the
flattened direct wave, FAIL otherwise, UNKNOWN when the direct wave is not
ROBUST. `pick_velocity` sets `velocity.validated` FAIL when this capability is
FAIL, because a shifted time axis biases every hyperbolic velocity.

R2 scan-edge picks. A non-held control point whose velocity is the first or last
value of the scan, at a time where the dense path clears its local null, is a
censored maximum, not a measurement. The location is invalid. A scan-edge point
where the path does not clear its null is reported as unconstrained and does not
invalidate the location.

R3 feasibility candidates slower than the direct wave. When the direct wave is
present, a candidate whose velocity is below the flattening velocity minus one
scan step (50 m/s) is rejected with that reason: a primary reflection beneath
the layer the direct wave travels in cannot have a lower moveout velocity.

R4 Dix-valid window, report only. When a measured Dix interval is imaginary or
out of band, the location reports the time of the last control point that is
not an endpoint of any violating interval, provided at least MIN_SUPPORTED_POINTS
supported path points lie above it. `pick_velocity` reports the minimum over
locations. `velocity.validated` is not scoped by it in v0.15.

## Predicted verdicts

| dataset | v0.14 | v0.15 prediction |
|---|---|---|
| Marm2 v1 as delivered, 0-2.6 s | velocity PASS, stack | R1 FAIL (intercept about 150-160 ms against a period near 0.1 s); R2 invalidates the locations with 1400 m/s picks; velocity FAIL; no stack |
| Marm2 v1 as delivered, 5.0 s | velocity FAIL | R1 FAIL; velocity FAIL |
| Marm2 v1 time-corrected, 0-2.6 s | velocity PASS, stack | R1 PASS; no R2 edge; velocity PASS; stack byte-identical to v0.14 (`82acd28f...`) |
| Marm2 v1 time-corrected, 4.85 s | velocity FAIL (2/5) | R1 PASS; velocity FAIL unchanged; R4 reports a window ending near or before 2.7 s |
| Marm2 v2, 0-2.6 s | velocity PASS, stack | R1 PASS; velocity PASS; stack byte-identical to v0.14 (`cbb46bd5...`) |
| Marm2 v2, 5.0 s | feasibility PASS on 1400/1350 m/s candidates; velocity FAIL | R3 rejects both candidates; feasibility not PASS; pipeline stops at build_cmp |
| Viking cdp1000-1199 | stack `587e9a81...` | R1 PASS or UNKNOWN; no R2 edge; stack byte-identical |
| B01 BAD_CDP | stack, bit-identical to A00 | unchanged |
| B02 L1/L2/L3 | L1 feasibility PASS; L2 INCONCLUSIVE; L3 per v0.14 | unchanged (planted event 2400 m/s; noise-only fixtures carry no direct wave) |
| B03 INVALID_VELOCITY | velocity FAIL | velocity FAIL unchanged; R4 reports a window above the 3.3-3.9 s violation |

## What counts as a failure of v0.15

- Any positive control above (Viking, B01, time-corrected v1 2.6 s, v2 2.6 s)
  losing its stack, or its stack changing by a single byte.
- Any expected refusal (B03, v1 as delivered) turning into a stack.
- Any existing unit test failing.

A positive control refused by a new rule is investigated and reported; the rule
is not tuned to let it through.
