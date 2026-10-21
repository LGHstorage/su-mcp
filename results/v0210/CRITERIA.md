# v0.21.0 criteria: closing the two v0.20 failures (written before any code)

Written 2026-09-23 after v0.20.0 failed its own criteria. Not edited after the first run. Still no new MCP
tool schema (37 tools), so the evaluation runs without a server restart.

## What v0.20 left

1. Three silent wrong stacks (C), all admitted by G1 (feasibility INCONCLUSIVE) and all broadband-noise levels
   whose quality fell 0.01-0.06 below "good" without a W1 warning.
2. Residual statics never applied: with odd/even CMP halves a receiver station on this geometry feeds only one
   CMP parity, so receiver statics could never be compared. Separately, statics-free levels produced about 6 ms
   rms of repeatable but spurious "statics"; levels with statics produced 14-28 ms, estimated with truth
   correlation 0.80-0.96.

## Rules

**W2 (replaces the G1 disclosure).** A stack whose dataset entered binning through G1 carries reliability WARN,
reason "feasibility not established before binning". A stack that shows reflections only through velocity
analysis is not presented as a finding without a caution.

**RS2 (replaces the RS gate).**
- Halves: CMPs are split at random into two halves (fixed seed 0), not by parity, so every station is seen in both.
- Materiality: statics are applied only if they matter to the stack. With rms static sigma and dominant period T,
  the expected stack amplitude factor exp(-(2 pi sigma / T)^2 / 2) must be below 0.9 (the "good" fraction again),
  i.e. sigma > 0.073 T (8.4 ms at 8.7 Hz). Smaller statics cost less than 10% of stack amplitude and are left alone;
  this also keeps the ~6 ms repeatable artefacts of v0.20 out.
- Reliability: Spearman-Brown split-half reliability >= 0.9 for both source and receiver statics, each over at
  least 10 compared shots/stations; otherwise FAIL with the actual reason (including "not comparable").
- rms <= T/4 as before.

Everything else as v0.20 (T1, G1, G2, R3, S1, W1, Bonferroni refine, budgets).

## Protocol P3 = P2 of v0.20 (unchanged).

## Evaluation

A. Regression: v2 and Viking stacks byte-identical, W1 OK on both. Unit tests pass (data001 refusals included).
B. RS2 on known-statics levels (descriptive, not held-out; new dataset ids, full P3): H2 statics 18, H4 statics 16,
   L1 statics 20, H5 statics 12, H5 statics 24, H5 statics 16 + band noise 1.0. Expected: RS2 PASS on all where a
   stack 1 is released; stack 2 truth quality >= stack 1 - 0.01 (no harm), and higher on at least half.
   Clean v2: RS2 must FAIL on materiality.
C. W2 on the three v0.20 C levels (H3 white noise 1.0, L1 noise 1.0, H5 white noise 1.5; new ids, full P3): all
   must carry WARN (they become Bn).
D. Sixth held-out ladder, generated after the code is frozen, seeds 61-63, P3 on every level:

| level | prediction |
|---|---|
| statics 10 ms | A; RS2 PASS or FAIL on materiality (true rms 10 ms is near the 8.4 ms line) |
| statics 18 ms | A after RS2 (stack 2) |
| statics 28 ms | G1 likely; RS2 PASS; A or Bn |
| white noise 0.7x | G1 -> WARN (W2): A with a false alarm, or Bn |
| white noise 1.2x | G1 -> WARN: Bn |
| white noise 1.7x | G1 -> WARN: Bn, or D |
| band noise 1.0x | A or Bn |
| delay 60 ms | T1 -> A |
| statics 14 ms + white noise 0.8x | Bn or A |

Failure of v0.21: any C in C or D, any false claim, a regression byte change, any budget overrun, RS2 applied on a
level with no statics, or RS2 lowering a statics level's truth quality by more than 0.01.
