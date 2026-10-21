# v0.15.0 result (2026-09-23)

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

## Summary

v0.15 adds four judgment rules to v0.14. All of them only add refusals or reports, and none turns an existing FAIL or UNKNOWN into PASS. Ten datasets were rerun through the MCP path as the pre-registered criteria (`CRITERIA.md`) require. All Marmousi2 and adversarial verdicts matched the predictions. The only item that missed its criterion was Viking, and the cause was in v0.14, not v0.15. During the regression a bug that stopped v0.14 on the Viking positive control was found and fixed.

| Rule | Content |
|---|---|
| R1 time zero | When the direct wave is ROBUST, the envelope-peak delay (intercept) of a stack of the near-offset direct wave flattened at its own velocity is measured. More than one period (inverse of the dominant frequency of the direct wave) gives `acquisition.time_zero_consistent` FAIL, and then `velocity.validated` FAIL |
| R2 scan-boundary pick | A location is invalid if, at a time where the path exceeds the null, a control point sits at either end of the scan (1400 or 5500 m/s). A boundary pick that does not exceed the null is only reported as unconstrained |
| R3 slow candidate | When a direct wave exists, a feasibility candidate more than one scan step (50 m/s) slower than the flattening velocity is rejected |
| R4 Dix valid window | Both end points of an interval with a Dix violation are suspect, and the window up to the last control point above it is reported. Report only, the verdict is not changed |

New module `sumcp/timezero.py`. Versions are 0.15.0 overall, reflection-0.7, velocity-0.8, stack-0.8, and timezero-0.1. The number of tools and the schemas are unchanged, so the change applies without a server restart.

## Regression results (MCP path, new dataset ids `v015-*`)

| Data | v0.14 | v0.15 prediction | v0.15 result |
|---|---|---|---|
| Marm2 v1 original 0–2.6 s | velocity PASS, stack | R1 FAIL, R2 invalid, no stack | Correct. Intercept +156 ms > tolerance 129 ms (7.7 Hz). All 5 locations have supported 1400 m/s picks at 0.6 and 0.88 s. Velocity FAIL. `apply_nmo` refused |
| Marm2 v1 time-corrected 0–2.6 s | PASS, stack `82acd28f…` | R1 PASS, same stack | Correct. Intercept +6 ms. Stack byte-identical |
| Marm2 v1 time-corrected 0–4.85 s | velocity FAIL 2/5 | FAIL kept, R4 window ≤ 2.7 s | Correct. FAIL 2/5. R4 windows 2.16 s (cdp 1048) and 2.68 s (637, 945). R2 also caught upper-boundary 5500 m/s picks at 4.28 and 4.80 s |
| Marm2 v2 0–2.6 s | PASS, stack `cbb46bd5…` | R1 PASS, same stack | Correct. Intercept −2 ms. Stack byte-identical |
| Marm2 v2 5.0 s | feasibility PASS (1400/1350 candidates) | R3 rejects, stops at build_cmp | Correct. Both candidates rejected, feasibility INCONCLUSIVE, `build_cmp` refused |
| Viking cdp1000–1199 | recorded as stack `587e9a81…` | R1 PASS/UNKNOWN, same stack | **Criterion missed.** R1 UNKNOWN (direct wave ABSENT), and no v0.15 rule fired. The stack is nevertheless different, `181fc5ba…`. See below |
| B01 BAD_CDP | stack = A00 | no change | Correct. Stack samples bit-identical to the v0.15 Viking stack (cdp numbers only 1–200) |
| B02 L1 STRONG | feasibility PASS (1.51 s, 2400 m/s) | no change | Correct. PASS with the same candidate |
| B03 INVALID_VELOCITY | velocity FAIL | FAIL kept, R4 reports the window above the violation | FAIL kept. R4 window 3.96 s. See below |

B02 L2 and L3 were not rerun. Their v0.14 verdicts rest on zero agreeing candidates, and R3 only removes candidates, so it cannot change the result.

## Items that missed the criteria and their causes

### 1. v0.14 stops on Viking (fixed)

`_apply_header_statics` in v0.14 required tstat = sstat + gstat whenever any of sstat, gstat, or tstat was nonzero. In Viking every trace has tstat = 11 ms and sstat = gstat = 0, so `pick_velocity` stopped with a ValueError. B01 and B03 inherit the Viking headers and stopped as well. In SEG-Y, tstat is the total static already applied, so the statics to apply are only sstat and gstat. When sstat and gstat are both zero, v0.15 applies nothing and records the tstat value as already applied. A file with sstat or gstat that does not match tstat is still refused (the SPS statics path of Poland is unchanged). Three unit tests were added. None of the 226 tests of v0.14 covered this path, and the Viking regression had not been run on v0.14.

### 2. The Viking stack differs from `587e9a81…` (a difference made in v0.14)

In the v0.15 Viking run no v0.15 rule fired. R1 was UNKNOWN, R2 had only an unconstrained pick at 0.04 s, R3 rejected no candidate, and R4 had no violation to report. This stack is therefore the result of v0.14 with only the statics bug fixed. The difference comes from two changes in v0.14.

- Analysis locations. v0.13 used 1010/1055/1100/1144/1189, and v0.14 and later use 1021/1063/1105/1147/1189. The new selector picks only bins with fold 60, and 1010 to 1020 have fold 57 to 59.
- Supported depth. v0.13 had 4.8 to 5.92 s, and v0.14 and later have 5.92 s at all 5 locations, because of the change in the path-null method.

The two stacks have a median trace correlation of 0.996 but a relative NRMS of 0.43, and some traces differ strongly. `CRITERIA.md` was written assuming that v0.14 equals v0.13 on Viking, and this assumption had never been checked (v0.14 stopped on Viking). The criterion is not changed after the fact and the item is recorded as missed. The Viking reference stack from v0.15 on is `results/v015-viking_stack.su` (`181fc5ba…`), and its adoption is for the user to decide.

## Why R4 must not be used for verdicts (B03)

B03 has a physically impossible moveout (interval velocity 10077 m/s) planted between 3.3 and 3.9 s. The v0.15 picker chose the original Viking reflections (2200 to 2250 m/s) in this interval, and the violation was caught at 4.6 to 5.28 s. The R4 window extends to 3.96 s, so a verdict based on it would have stacked the interval that is impossible by design. The Dix valid window is therefore only above where a violation was found, and it is not evidence that the part above is correct. It stays report-only in v0.15. Turning it into an operating rule would need further evidence that handles cases like B03.

## Limits and cautions

- R1 margin. The intercept of the v1 original is 156 ms against a tolerance of 129 ms, a margin of 27 ms. The tolerance comes from the dominant frequency of the direct wave (lowered to 7.7 Hz by the 2D line source). The same delay would have passed with a dominant frequency of 6 Hz or less.
- R1 decides only on gathers where the direct wave is ROBUST. Viking (CMP gathers, direct wave ABSENT) and land data become UNKNOWN.
- R3 uses an assumed water velocity (default 1492 m/s). A real direct-wave velocity of 1500 is within one step.
- The 0.67 s, 1500 m/s feasibility candidate of the time-corrected v1 at 4.85 s is the boundary reflection of v1. It has the water velocity and cannot be separated by R3.
- The Poland regression was not run. It is land data, so R1 is probably UNKNOWN, but R2 may make locations with supported boundary picks invalid. This needs to be checked on WSL.
- Unit tests. The full suite was run in a separate Linux environment with SU installed (CWP/SU source built with XDR, the same big-endian SU format as the user's WSL). 344 of 347 passed, and 3 were skipped because the A03 fixture is not in that environment. At first 4 failed, all old tests unrelated to v0.15. They had not shown because the 22 SU tests had never been run. Two came from the renamed unit_evidence field of geometry-0.7, and two from tool_call entries that have been written to the log since audit-0.2. The judgment code was not changed, and the tests were updated to the current structure (`tests/test_geometry.py`, `tests/test_sumcp.py`).

## Decisions (2026-09-23)

- The Viking reference stack becomes `181fc5ba…` (`dev/reproduce_viking.py`). No v0.15 rule fired on Viking, and the difference comes from the location selection and supported-depth changes of v0.14. The previous reference `587e9a81…` is kept as the record of v0.9.2 to v0.13.
- R4 stays report-only. As B03 shows, there is no guarantee that the window is correct.
- The Poland regression is moved to the land stage. The marine path is completed first.

## Files

- Code: `sumcp/timezero.py` (new), `sumcp/reflection.py`, `sumcp/velocity.py`, `sumcp/stack.py`, `sumcp/tools.py`, `sumcp/evidence.py`, `sumcp/config.py`
- Tests: `tests/test_v015_checks.py` (18)
- Criteria: `results/v0150/CRITERIA.md` (written before the code change)
- Stacks: `results/v015-t0fix_stack.su` (82acd28f…), `results/v015-v2_stack.su` (cbb46bd5…), `results/v015-viking_stack.su` (181fc5ba…), `results/v015-b01_stack.su` (ea18cff9…, samples identical to Viking)
- MCP datasets: `v015-marm-v1win`, `v015-t0fix`, `v015-t0fixfull`, `v015-v2`, `v015-v2full`, `v015-viking`, `v015-b01`, `v015-b02l1`, `v015-b03`
