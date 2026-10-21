# v0.19.0 criteria: bounded iteration and a conditioning menu (written before any code)

Written 2026-09-23 against v0.18.0. Not edited after the first run. User decisions: iteration
comes before migration; the number of attempts must be bounded; more tools are allowed so that
useful SU modules can be brought in.

## What changes in kind

Until v0.18 every refusal was final: the system said why and stopped. v0.19 lets the processing
try again, but only in pre-declared ways, a fixed number of times, with every attempt recorded,
and with every existing check applied unchanged to the result. Nothing that fails a check is
released; iteration only changes what is tried, never what is accepted.

Tool count goes from 32 to 35. New tool schemas need a restart of the MCP server.

## New tool 1: refine_velocity (bounded re-picking)

Runs only after pick_velocity, and only when velocity.validated is FAIL for location-level
reasons (support depth, scan-edge pick, Dix, path null). It refuses when the failure is
dataset-level (R1 time zero FAIL): re-picking cannot fix a late clock.

Fixed strategy ladder, applied to the failed locations only (valid locations keep their
measured functions); stop at the first attempt after which the model passes:
1. supergather: the location's CMP plus 2 bins on each side (5 CMPs) analysed as one gather;
2. relocate: the nearest eligible CMPs within a quarter of the spacing between analysis
   locations, at most 3 candidates, each as a 5-CMP supergather; the first valid one is kept;
3. wide supergather: 4 bins on each side (9 CMPs) at the original location.

Budget: at most 3 attempts per call and one refine_velocity call per velocity model (a new
pick_velocity resets it); at most 4 velocity analyses of a dataset in total. The velocity
model and the stack both record how many attempts it took ("velocity_attempts"), because every
extra attempt is another chance to pass by luck.

Why these three: pooling neighbouring CMPs is the standard way to raise fold where a single
CMP is too noisy; moving off a bad spot is what an analyst does; both keep the same estimator
and the same checks. Bin widths (2, 4) are the smallest symmetric pools that multiply fold by
about 5 and 9.

## New tool 2: condition_gathers (pre-stack conditioning with a QC gate)

Applies up to 3 operations, in the order given, to the CMP-sorted gathers. Operations come only
from a registry; each maps to an SU program the agent cannot reach through su_run
(TRUSTED, like sunmo), with validated numeric parameters:

| operation | SU program | purpose |
|---|---|---|
| bandpass | sufilter | remove energy outside the signal band |
| agc | sugain agc=1 | balance amplitudes before velocity analysis |
| mute_direct | sumute | remove the direct-wave corridor using R1's measured velocity |
| dip_filter | sudipfilt, per CMP gather | reject events with apparent velocity below a given value (linear noise) |
| predictive_decon | supef | shorten the wavelet / attenuate short-period reverberation |

Adding a module later means adding a registry entry (program, parameter rules, purpose) and
a unit test; the QC gate below applies to every entry automatically.

QC gate (signal preservation): on 5 CMP gathers, three synthetic hyperbolic reflections are
injected (a Ricker at the record's dominant frequency, t0 at 25/50/75% of the window below the
last direct arrival, velocities 1.1/1.3/1.5 x the direct-wave velocity, amplitude 0.5 x the
gather RMS). The chain runs on the gather with and without the injection; the difference is
the processed injection. preservation = median correlation between the processed and the
injected events. PASS when preservation >= 0.9 (the "good" fraction used throughout): the
conditioned gathers become the dataset's cmp_sorted product, processing.preprocessed PASS, and
velocity/NMO/stack are invalidated. FAIL: the product is kept for audit but not used.

Budget: at most 2 conditioning passes per dataset.

## New tool 3: conditioning_menu

Returns the registry: operations, parameters and their allowed ranges, purpose and cautions.

## Evaluation

Protocol P, fixed for every level (this is what the agent does after a refusal):
standard pipeline; if pick_velocity FAILs for location-level reasons, call refine_velocity once;
if it still FAILs, stop. Conditioning is not part of P, because none of the ladder defects
(time shift, in-band random noise, surface-consistent statics, white noise stopped at
feasibility) is what the menu removes; it is tested separately.

A. Regression: v2 and Viking stacks byte-identical; pick_velocity output unchanged.
B. P on every earlier velocity-refused level (descriptive): H1 delay 110 (R2 at 0.32 s on
   all 5 locations, predicted still refused: the 1400 m/s pick is real bias); H1 statics 15 and
   H2 statics 18 (one location fails; predicted released, cell A); band noise H1 3x, H2 2.5x,
   H3 1.75x and 2.25x (data not usable; if P releases them, they must carry an E1/N1 warning,
   otherwise it is a new C and a failure of v0.19). Ladder 1 delay 124/150: refine_velocity must
   refuse (R1 FAIL).
C. Conditioning QC on v2 (clean): bandpass 3-5-25-35 Hz must PASS; bandpass 30-35-60-70 Hz
   (outside the signal) must FAIL; mute_direct must PASS; predictive_decon and dip_filter are
   reported whatever they give; after a PASS the pipeline must still release a good stack.
D. Fourth held-out ladder (generated after this file), seeds 41-43: statics 16, 22 ms;
   band noise 0.3, 1.6, 2.2, 2.8 x; delay 105 ms.

| level | prediction |
|---|---|
| band noise 0.3x | released without refinement: A |
| band noise 1.6x | released; warned (E1 PARTIAL likely); B-warn or A |
| band noise 2.2x | velocity FAIL, refine may release; if released it must be warned |
| band noise 2.8x | velocity FAIL; refine probably still FAIL: D |
| statics 16 ms | feasibility uncertain; if velocity fails at one location, refine releases: A |
| statics 22 ms | feasibility likely INCONCLUSIVE (F1): E |
| delay 105 ms | R1 PASS; R2 likely refuses at 0.32 s; refine cannot remove a real bias: E |

Failure of v0.19: any new C, any attempt beyond budget, any byte change in a regression stack.
