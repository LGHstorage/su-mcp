# v0.30.0 criteria: corrupt samples and non-finite measurements (written before any code)

Written 2026-09-29 after v0.29 failed on the full Viking line: one sample of 3.4e38 (float32 maximum, an IBM-float
overflow clamped on conversion) at CDP 713 turned the half-stack S/N, the DMO gate and M2 into NaN, and N1 read the
NaN as CLEAR, so the stack was released with reliability OK. Not edited after the first formal run; anything found
before it goes in an addendum. No new MCP tool; one new conditioning operation (the worker picks it up).

## Rules

**Q0 (sample check).** A trace is corrupt when it holds a non-finite sample or a sample larger in magnitude than 10^6
times the median trace RMS of the file (120 dB: no recorded amplitude range reaches it, and a clamped overflow is
30 orders beyond it). The median is taken over live traces (RMS > 0). Computed in float64, block by block.

**Where Q0 acts.**
- condition_gathers refuses every operation except kill_corrupt, before spending a pass, when cmp_sorted has corrupt
  traces (filters, AGC, DMO and statics would spread the sample, and the injection gate would read NaN).
- stack_cmp: a stack built from corrupt traces carries quality WARN "Q0 corrupt samples", naming the CDPs.
- migrate_stack (time and depth) refuses a stack with corrupt traces, before running: migration spreads one sample
  over the aperture.
- The refusal and warning texts name the remedy: condition_gathers [{"op": "kill_corrupt"}].

**kill_corrupt (new solo conditioning operation, no parameters).** Zeroes the samples of every corrupt trace and
leaves all other traces byte for byte as they were. Gate K0: accepted only if (a) the corrupt traces are at most 1%
of the file (beyond that the data are not a few bad traces and zeroing is not a repair) and (b) every other trace is
byte-identical in the output and no corrupt trace remains. It spends a pass and invalidates velocity, NMO and stack
like every conditioning pass.

**N0 (non-finite measurements).** A non-finite QC number is never a pass. N1 with a non-finite half-stack
correlation reports status UNMEASURABLE and adds the quality reason "N1 not measurable (non-finite samples)"; a
non-finite injection preservation is a FAIL that says so; M2 reports a non-finite correlation as null.

Everything else unchanged (budgets, gates, thresholds).

## Protocol P12

P11 of v0.29 with condition_gathers [kill_corrupt] after sort_cmp (a refusal "no corrupt traces" is a no-op), then
as P11: pick, stack 0, DMO, re-pick, stack 1, migrate phase_shift, phase_shift_smooth, depth_pspi. New id
v030-vikfull. The agent-operated run is repeated (v030-vikagent) with the same instruction as v0.29.

## Evaluation

A. Regression: stack bytes Viking 200-CDP `181fc5ba…`, v2 (P7) `7374cb63…`, phase_shift migration of that stack
   `f8c90340…`; unit tests pass, including: a file with one 3.4e38 sample is flagged, killed, and nothing else
   changes; N1 on it reports UNMEASURABLE; migrate refuses it; a clean file is not flagged.
B. Q0 on existing data: no corrupt trace on clean Marmousi2 v2, the 200-CDP Viking window or the thirteenth ladder
   levels (a false flag on any of them is a failure).
C. Full Viking line, P12: Q0 flags CDP 713 (and nothing that is not corrupt); kill_corrupt accepted; N1 measured
   (finite); DMO D1 finite (accepted or refused on its own terms); F3 (>= 0.8 against the 200-CDP control) holds.
   Recorded without prediction: M1 on the migrations, Z2 on depth, the agent's route.

Failure of v0.30: a regression byte change; a false Q0 flag on B; a released product whose QC contains a non-finite
number read as a pass; kill_corrupt changing a trace that is not corrupt; a budget overrun or false claim.
