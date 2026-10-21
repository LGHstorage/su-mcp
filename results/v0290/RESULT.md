# v0.29 result: the full Viking Graben line

Run 2026-09-29 on SU-MCP v0.28.1, two runs (fixed protocol P11 = v029-vikfull, agent-operated = v029-vikagent),
as pre-registered in CRITERIA.md. No code change, no rerun. Figure: `qc/v0290/fig14_viking_full_stack.png`.

**Verdict: v0.29 fails** on its own failure condition "a false claim": both released stacks carry reliability OK
while their half-stack S/N measurement is NaN (reported as level CLEAR, S/N "inf", ceiling 1.0), and both contain an
unflagged sample of 4.6e36. The system refused every migration, so no wrong image was released, but the stack's
verdict rested on a measurement that did not exist.

## Cause: one corrupt sample in the field data

CDP 713 of paracdp.segy holds 3.4028e38 (float32 maximum; where an IBM-float overflow is clamped on conversion)
near 4.37 s, against typical samples of 1e7-3e8. Nothing in the system looks at sample values. Squared, it
overflows float32, and every correlation that touches it becomes NaN:

| measurement | value | how the system read it |
|---|---|---|
| half-stack S/N (N1) | r = NaN | CLEAR, ceiling 1.0, stack reliability OK (wrong) |
| DMO gate D1 | preservation NaN | FAIL (right outcome, wrong reason: "kept only nan correlation") |
| M2 velocity sensitivity | -0.003 / 0.000 | report only |
| M1 impulse gate | 0.756 / 0.595 / 0.263 (phase_shift), 0.834 / 0.448 / 0.606 (smooth) | FAIL, not released (right) |

The migrated sections are dominated by the impulse response of that one sample (a smile ~800 CDPs wide, 99th
percentile amplitude ~1e33); M1 refused them.

## Checks

| check | prediction | result |
|---|---|---|
| F1 scale | all steps complete as jobs | met: import 27 s, pick 42 s, DMO 4.4 min, phase_shift 3 min, phase_shift_smooth 44 min (60 sumigps runs on 2142 x 1500) |
| F2 velocity | 15 locations, K1/K2 | met: 15 of 15 valid (CDP 119-2024), max gap 248 (limit 477) |
| F3 consistency | >= 0.8 with the 200-CDP control over CDP 1000-1199 | met, barely: median 0.803 (p10 0.725) |
| F4 aperture | M5 OK | met: 0.21 |
| F5 DMO | accepted | **missed**: preservation NaN (the corrupt sample) |
| F6 (recorded) | M1, Z1, reliability, agent | M1 FAIL on all migrations; depth_pspi refused by Z2 (interval velocities outside 1000-7000 m/s at CDP 584 and 692, from deep picks of 3250-3400 m/s); stack reliability OK (false, see above) |

## The agent-operated run (R2)

The agent reached the same stack and the same refusals by its own route, and then found the cause: it chased four
readings that could not be right (NaN S/N, NaN preservation, a display clip of 9.6e-18, amplitudes of 1e7-1e8) with
su_preview at 100% clip until it located CDP 713. It tried AGC (the one menu operation that would make the sample
finite); the injection gate refused it (0.83 < 0.9), and the agent accepted the refusal rather than retrying with
another window. It ran all three time-migration methods (all refused by M1), recommended handing out none of them,
and offered the unmigrated stack with caveats (clip the spike; pre-applied top mute; picks at 3-6 s likely following
water-bottom multiples; deep pick jumps at CDP 476, 692, 801; a 1400 m/s pick at 0.04 s inside the mute).
Deviation disclosed by the agent: it staged and viewed three of its own QC images.

## Other findings (for the next version)

1. NaN is read as a good value in N1 and as an ordinary FAIL in the conditioning gate; there is no check of sample
   values anywhere, no menu operation that kills a trace, and dead traces (trid 2) stay in the gathers.
2. The reflection window starts at the far-offset arrival of an assumed 1492 m/s direct wave (2.17 s) when the
   direct wave is absent, although this line is pre-muted and reflects from 0.45 s: N1, E2 and the injection depths
   ignore the shallow section.
3. Deep picks of 3250-3400 m/s at CDP 476, 692 and 801 (likely multiples or diffractions) make Dix blow up (Z2).
4. pick_velocity allows 1400 m/s at 0.04 s, inside the mute and below water velocity.
5. geometry_analyze with defaults does no arrival-time measurement on a CDP-sorted file (receiver spacing stays
   UNKNOWN; build_cmp takes the caller's spacing).
