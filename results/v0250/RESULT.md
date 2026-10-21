# v0.25.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-28. Criteria in `CRITERIA.md` (written before the code, no edits or addenda). Code `sumcp/migrate.py` (migrate-0.2), `sumcp/config.py` (0.25.0), `server.py` (descriptions only). Three M5 tests were added to `tests/test_v024_checks.py`.
- Tenth held-out ladder `test_dataset/Marm2_ladder_heldout10/` (`make_heldout10.py`, generated after the code was deployed). Four short lines and band noise 0.8x.
- Evaluation `dev/marm2_ladder/evaluate_migration.py`, numbers in `migration_eval/*.json`, figure `qc/v0250/fig7_short_lines.png`. One bug in the evaluation harness was fixed. The correlation stopped when muted traces were present, and such traces are now left out of the calculation.
- Run. There was no new MCP tool, so it ran without a server restart. Two operators ran P7 in parallel, with no retries.

## Summary

**v0.25 passed its pre-registered criteria.**
- All five predictions for M5 (the fraction of image cells whose migration aperture leaves the line) were correct.
- Every product with M5 OK had a migration gain of 0.22 or more. Every product with WARN had 0.17 or less.
- The migration samples and stack bytes were the same as in v0.24.
- M3 was moved to a report, so the clean v2 migration was released without a warning.

**One silent error (C) appeared outside the criteria.** The stack of the 2.0 km line has a quality of 0.508 with reliability OK (interpretation item 2).

## A. Regression

The stacks are Viking `181fc5ba…` and v2 `7374cb63…`. The four migration samples (v2 and Viking × two methods) had the same sha256 as in v0.24. 456 of 459 unit tests passed, 3 skipped.

## B. Viking and clean v2

| Data | M5 fraction | M3 (report) | Reliability (phase_shift / blend) | Gain g (ps / blend) |
|---|---|---|---|---|
| Viking | 1.00 | 0.23 | WARN (M5) / WARN (M5) | no truth |
| clean v2 | 0.403 | 0.41 | OK / OK | 0.314 / 0.246 |

## C. Tenth held-out ladder (phase_shift)

| Level | Line | Velocity locations (valid) | Stack quality | M5 fraction | Reliability | unmig | mig | g | Prediction | Correct |
|---|---|---|---|---|---|---|---|---|---|---|
| 27 shots | 2.0 km | 5 (833–848) | 0.508 | 0.967 | WARN | 0.109 | 0.211 | 0.102 | WARN | yes |
| 52 shots | 3.0 km | 5 (781–896) | 0.578 | 0.844 | WARN | 0.188 | 0.265 | 0.077 | WARN | yes |
| 77 shots | 4.0 km | 5 (733–948) | 0.624 | 0.607 | WARN | 0.203 | 0.372 | 0.169 | WARN | yes |
| 102 shots | 5.0 km | 7 (681–996) | 0.646 | 0.475 | OK | 0.216 | 0.440 | 0.224 | OK, g ≥ 0.15 | yes |
| full + band 0.8x | 5.95 km | 9 | 0.638 | 0.393 | OK | 0.210 | 0.468 | 0.258 | OK, g ≥ 0.15 | yes |

The minimum g on the M5 OK side was 0.224, and the maximum on the M5 WARN side was 0.169. Criterion met. M1 was PASS for all 10 migrations. The third apex of the 52-shot phase_shift was exactly at the tolerance limit (4 traces).

## Interpretation

1. **On short lines, migration does not damage the image but helps less.** The gain fell from 0.31 at 5.95 km to 0.08 to 0.10 at 2 to 3 km. As Fig. 7 shows, on a short line the smiles from the line ends cross the section. Viking is the same case (M5 1.00).
2. **New C, the stack of the 2.0 km line.** The 5 velocity analysis locations fell within cdp 833 to 848, inside 15 CDPs. On a short line the stable-fold part is only in the middle, and the fold criterion gathered the locations there.
   - The 80% coverage rule and K2 are measured on the analyzed span, so they passed.
   - In fact the whole line of 200 CDPs was stacked with a velocity extrapolated from 15 CDPs.
   - It is not the object of these criteria (migration gain), so it does not meet a failure condition, but it is a silently wrong stack.
   - Next rule candidates. The analyzed span must cover a set fraction of the line released as a stack (K3), or the extrapolated part is disclosed or cut (extension of S1).
3. **Moving M3 to a report was right.** The problem of a warning on the clean v2 migration of the default method, which is the better one, disappeared.
