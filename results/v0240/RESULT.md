# v0.24.0 result

English translation of the Korean original. Numbers, file names, and decisions are unchanged.

2026-09-28. Criteria in `CRITERIA.md` (written before the code). The two addenda came from development runs before the formal run (M1 window size, default method). Development notes are in `DEV_NOTE.md` and the run procedure in `PROTOCOL_P6.md`.
- Code `sumcp/migrate.py` (migrate-0.1, new file), `sumcp/evidence.py` (migration.completed), `sumcp/config.py` (0.24.0, sumigps TRUSTED), `sumcp/tools.py`, `server.py` (new tool `migrate_stack`, 38 tools).
- Tests `tests/test_v024_checks.py` (13).
- Ninth held-out ladder `test_dataset/Marm2_ladder_heldout9/` (`make_heldout9.py`, seeds 91 to 93, generated after the code was deployed).
- Evaluation. The reference image is `results/migration_reference/er_mig_true_blend.npz` (computed separately by the evaluation harness). Numbers are in `eval_v024.json` (stack) and `migration_eval/*.json` (migration).
- Run. After a server restart, two operators ran P6 in parallel. There were no retries and no infrastructure errors.

## Summary

**v0.24 passed its pre-registered criteria (the first time since v0.21).**
- All 14 migrations passed M1 and were released.
- Migration raised the match with the reference image made with the true velocity on all data (from 0.18 to 0.22 up to 0.44 to 0.54).
- Every migration product inherited the warnings and cautions of its stack.
- The regression bytes did not change.

## A. Regression

Viking stack `181fc5ba…` and v2 default stack 1 `7374cb63…`. Both were byte-identical. 453 of 456 unit tests passed, 3 skipped (cloud SU).

## B. Clean v2

| Product | Match with the reference image (0.7–2.4 s) | 0.7–1.4 s | M1 focus | M2 (×0.95 / ×1.05) | Reliability |
|---|---|---|---|---|---|
| unmigrated stack | 0.222 | — | — | — | OK |
| phase_shift (default) | 0.536 | 0.725 | 0.87 / 0.87 / 0.78 | 0.870 / 0.874 | WARN (M3 0.41) |
| phase_shift_blend | 0.468 | 0.659 | 0.89 / 0.89 / 0.81 | 0.829 / 0.854 | OK |

The formal run matched the development run to the third decimal. The criterion (M1 PASS for both methods, Q_mig > Q_unmig) was met.

## C. Viking (no truth)

| Method | M1 focus | M2 (×0.95 / ×1.05) | M3 | Reliability |
|---|---|---|---|---|
| phase_shift | 0.80 / 0.68 / 0.50 | 0.173 / 0.168 | 0.23 (5.92 s) | WARN (M3) |
| phase_shift_blend | 0.83 / 0.84 / 0.78 | 0.268 / 0.264 | 0.23 | OK |

The Viking stack has a frequency of 46 Hz and a 6 s record, so a velocity change of only 5% changes the migrated image strongly (correlation 0.17 to 0.27). The focus of the third apex for phase_shift (0.504) was just above the 0.5 threshold.

## D. Ninth held-out ladder

| Level | Path | Stack quality (reference) | Stack reliability | unmig | phase_shift | blend | Migration reliability (ps / blend) |
|---|---|---|---|---|---|---|---|
| statics 15 ms | G1, RS2 PASS | 0.639 (0.601) | CAUTION | 0.220 | 0.494 | 0.465 | WARN and caution / CAUTION |
| band noise 1.0x | standard | 0.596 (0.572) | OK | 0.187 | 0.464 | 0.474 | WARN / OK |
| white noise 1.0x | G1 | 0.596 (0.565) | CAUTION | 0.199 | 0.478 | 0.439 | WARN and caution / CAUTION |
| delay 80 ms | T1 (−78 ms) | 0.641 (0.623) | OK | 0.221 | 0.523 | 0.497 | WARN / OK |
| statics 15 + band 0.8x | G1, RS2 PASS | 0.610 (0.543) | CAUTION | 0.177 | 0.472 | 0.477 | WARN and caution / CAUTION |

All five stacks were good (≥ 0.560). All predictions of the criteria were met.
- M1 was PASS for all 10 migrations (focus 0.56 to 0.89).
- Q_mig > Q_unmig for every migration.
- Every migration product inherited the warnings and cautions of its stack.

## Interpretation

1. **Migration moves the image far toward the truth.** The match with the reference image rose from 0.18 to 0.22 before migration to 0.44 to 0.54. In the shallow part (0.7 to 1.4 s), phase_shift gives 0.68 to 0.73.
2. **The limit on quality is the velocity.** Migrating the same clean stack with the true velocity gives 0.671 (`DEV_NOTE.md`). With the picked stacking velocity it reaches only 0.536. As M2 shows, the image is sensitive to a 5% velocity change (Marmousi correlation 0.79 to 0.90, Viking 0.17 to 0.27).
3. **The median velocity (default) is generally better than the per-location velocities.** It was better in 4 of 6 cases. In the other 2 (band-noise cases), blend was higher by 0.005 to 0.010. The per-location blend follows the picking error of each location.
4. **M3 states a fact but did not work as a quality warning.** Marmousi has a large lateral variation (0.34 to 0.44), and the 1D method still gave the better image. That every product of the default method carried an M3 quality WARN is a false alarm. It should be moved to a report in the next version.
5. **The M1 window text in the server.py description ("2 traces and 12 samples") was left from before the addendum.** The decision code scales with the period as the addendum says (Marmousi 7 to 8 traces and 43 samples, Viking 2 traces and 3 samples).
