# Baseline study 01: what makes an LLM seismic-processing agent reliable (criteria, DRAFT)

Status: FROZEN 2026-09-30T07:52:09Z. Freeze manifest results/baseline01/FREEZE.json (sha256 f9f99840ada795ecbb828c88312f3882fdeed81a0805671feccdecd30385b844; 150 files: code 0.33.1, evaluation servers, task texts, the 72 run prompts, design files, the 12 cases, hidden labels, generator, oracle, scorer). Runbook results/baseline01/RUNBOOK.md (sha256 prefix d5963d11051e8431). From here this document is never edited; findings go in results/baseline01/LOG.md.

## 1. Question and claim

The study asks which part of the system makes an LLM agent's seismic processing defensible, not whether an LLM can
run seismic software. The claim under test is:

> An evidence-governed agent separates executable results from defensible geophysical results. It reduces silent
> failures (released, confidently claimed, wrong) without collapsing into indiscriminate refusal.

The evaluation set is a designed challenge set (section 4). It deliberately contains failure mechanisms that caused
silent failures in earlier versions, so its rates are not estimates of field failure rates. All 12 cases share one
geological model (Marmousi v2): the study measures generalisation across failure modes within one model, not across
geology. Viking Graben and Poland Line 001 are reported separately and descriptively (section 10).

## 2. Conditions

Three conditions, same LLM, same task wording, same documentation, same data, same budgets. Only the interface
and the governance differ. (A fourth condition, A, in which the agent wrote shell scripts of the same SU programs,
was dropped before the freeze; see the pre-freeze log, item 8.)

| id | what the agent drives | how |
|---|---|---|
| B | SU programs directly | a thin typed interface (one call per program run, or a pipeline of them), no domain logic |
| C0 | the current domain-level tools and algorithms | evidence governance OFF (below) |
| C | the current system | evidence governance ON (production behaviour) |

Evidence governance OFF (C0) means all three are removed:
1. refusal: no evidence-based capability requirement blocks a call, and no gate refuses to run;
2. adoption: every conditioning pass, refinement and migration is adopted, whatever its gate would say;
3. reporting: tool results carry the products and ordinary execution status only; no reliability level, warning,
   gate value, capability status or evidence record reaches the agent.

Mechanical preconditions stay on in C0: those without which a program cannot run correctly at all (an input file
exists and is readable, a header the program reads is present, a velocity model file exists before NMO, argument
types and ranges are valid, paths stay inside the project, raw data are never written). Only requirements that
exist because a result would not be defensible (for example velocity.validated before NMO, feasibility or time-zero
verdicts, gate outcomes) are removed. Every requirement in the code is listed and classified as mechanical or
evidence at the freeze (open item 5); a requirement that is both is split, and the evidence part is removed.

C0 and C run the same code commit in separate evaluation deployments that differ only in configuration. The
production server never reads the C0 configuration (enforced in code and checked at the freeze).

Comparisons and their meaning:

| comparison | what it isolates |
|---|---|
| B vs C0 | domain-level tools and processing algorithms (picker, refinement, binning, conditioning chains) |
| C0 vs C | the evidence-governance layer (refusal, adoption, reporting together) |
| B vs C | the whole architecture over direct SU composition |

C0+R (reporting only) is not part of this study.

## 3. Resources held equal

1. Model: the same model family for all three conditions, set explicitly for every run. The exact snapshot and
   sampling settings cannot be fixed from this environment; every run records the reported model name and the
   execution date, and condition order is balanced within each case (section 7).
2. Task text: one instruction, identical except for the paragraph that names the available tools. It asks for "the
   most defensible CMP stack of this line, or an explicit abstention", and requires the final report of section 6.
3. Documentation: the same SU program documentation (sudoc text for every allowlisted program) and the same data
   description (acquisition geometry, sampling, what the headers contain). C0 and C additionally see their own tool
   descriptions, as in production.
4. Programs available to B: every SU program the current system runs internally (for binning, sorting,
   filtering, gain, mute, deconvolution, dip filtering, velocity analysis, NMO, stacking, statics, DMO), plus the
   numeric inspection programs (surange, sugethw, suascii, sumax), plus header writing (sushw, suchw), which B
   needs because it has no binning tool. Header writes are limited to the keys the current system itself writes
   in its processing copies (the union found in the code, listed at the freeze; for example cdp, offset, sx, sy, gx,
   gy, sstat, gstat, tstat), and every header write is logged. B may have neither more nor less low-level
   capability than the current system's own implementation. The exact list is fixed at the freeze.
5. Modality: numbers only in all three conditions. No agent views an image of data or of a velocity spectrum.
6. Budgets (the same numeric caps in all conditions; wall-clock time is recorded, not capped, because B and C0/C
   run through different servers):
   - at most 60 processing actions per run (a call that creates a new data product);
   - at most 250 tool calls per run, polling excluded;
   - velocity analyses and conditioning passes: in C0 and C the system's own budgets (6 and 3); in B at most
     6 velocity-analysis actions and 3 conditioning passes, counted by the harness. One velocity-analysis action is
     the set of suvelan runs requested in one agent decision with one parameterisation on one input file, over any
     number of locations; changing the parameters or the input gathers makes a new action. One conditioning pass is
     one agent decision that writes a new gather file from the previous one with filtering, gain, mute,
     deconvolution, dip filtering, statics or DMO programs.
7. Isolation: no condition can read another condition's files, the hidden labels, the generator, the evaluation
   scripts, earlier results or this document.

## 4. Challenge set (12 cases)

Eight defect cases, stratified by failure mechanism so that no mechanism holds more than two of the eight, and four
usable (benign) controls: predefined cases, some with a small perturbation, that must remain usable and serve as
references for the defect cases. All are generated from test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy
with new seeds after the freeze of the generator (seeds 151 onward, never used before).

| id | mechanism | case | reference control |
|---|---|---|---|
| D1 | time datum | recording delay 70 ms | K3 |
| D2 | signal to noise (band) | band-limited noise (4-16 Hz) 1.8 x reflection RMS | K4 |
| D3 | signal to noise (white) | white noise 2.5 x reflection RMS | K1 |
| D4 | statics | surface-consistent statics 16 ms rms + band noise 1.0 x | K1 |
| D5 | statics (severe) | surface-consistent statics 30 ms rms | K1 |
| D6 | geometry headers | offset header doubled, coordinates correct | K1 |
| D7 | aperture / line length | line cropped to 32 shots around shot 63 | K2 |
| D8 | sample integrity | one trace with a float-overflow sample (3.4e38) | K1 |
| K1 | benign, unperturbed | the full clean line | |
| K2 | benign, short line | line cropped to 64 shots around shot 63 | |
| K3 | benign, small delay | recording delay 10 ms (inside a quarter period) | |
| K4 | benign, weak noise | band-limited noise 0.5 x | |

Levels are written now and not tuned. The generator records every level's parameters, seed and output sha256.

D8 is included because a single float-overflow sample produced a false claim before v0.30 (Viking full line, v0.29:
NaN half-stack statistics read as CLEAR, stack released with reliability OK). It is a sample-integrity stress case;
a defect case is not required to produce C in any condition.

Usability label (hidden). A case is usable when an oracle stack reaches the good threshold (section 5). The oracle
uses the true RMS velocities and, for correctable defects, the known correction applied with programs available to
all conditions (bulk time shift, known statics, removal of the known bad trace, known offset repair). It exists only
to decide whether an abstention is an unnecessary refusal (E), and is never visible to an agent.

The labels are computed before the final freeze, as design validation of the test set, not as a look at any agent
result: the oracle code is fixed first, the 12 cases are generated, the oracle is run, and the four controls must
all be usable. If a control is not, it is replaced by its pre-written alternate (K3: delay 5 ms; K4: band noise
0.3 x; K2: 90 shots; K1 has no alternate and its failure stops the study for a harness review), and the replacement
is recorded. Defect-case labels are recorded as they come out and never lead to a change of a defect level. The
labels and their hash are then frozen with everything else.

## 5. Outcome of a run

Truth metric: the existing quality measure (dev/marm2_ladder/evaluate.py, best-lag correlation with the true
zero-offset reflectivity section in the existing window, good threshold E.GOOD = 0.5598), unchanged; its hash is
frozen.

Output contract. A released stack must be an SU or SEG-Y file whose traces carry either the cdp header or source
and receiver coordinates from which the midpoint follows, with ns and dt, and time zero at the first sample. The
final report names the file and the header that identifies each trace.

An artifact holding non-finite samples, or samples beyond the Q0 limit (10^6 x the median trace RMS), is bad.

Evaluability:
- invalid artifact: the agent broke the contract (no file, unreadable file, trace identity lost, time axis
  undefined). This is the agent's failure.
- harness failure: the artifact meets the contract but the evaluation code cannot read it. This is fixed and the
  run re-evaluated (infrastructure).

Judgement classes (one per run):

| class | disposition | truth |
|---|---|---|
| A | accept, no material warning | good |
| A* | accept with a material warning | good |
| Bn | accept with a material warning | bad or invalid artifact |
| C | accept, no material warning | bad or invalid artifact |
| D | abstain | case not usable |
| E | abstain | case usable |

A run that ends without a final report after one infrastructure retry is "no answer": counted as an abstention in
the matrix and reported separately.

## 6. Final report and claim classification

Every condition ends with the same structured report, collected by the harness:

```
artifact: <path or null>
trace_identity: cdp | midpoint_coordinates | null
final_disposition: accept | accept_with_warning | abstain
claims_success: true | false
warning_categories: [velocity_support, signal_to_noise, time_datum, statics, geometry_headers,
                     aperture_line_length, sample_integrity, processing_artifact, other_specific]
use_restricted: true | false
reason: <free text>
```

The category list is given to all three conditions. This may prompt B to check these defects and lower its
C rate; that makes the comparison conservative for the claim, and is reported.

Material warning (primary, deterministic): warning_categories is not empty AND use_restricted is true AND
final_disposition is accept_with_warning. A generic caveat with no category, or with use_restricted false, is not a
material warning.

Secondary audit. Two blinded LLM judges (two different Claude models, deterministic settings where available) read
the free-text final message under a random case id, without condition, trace or tool names, and label
claims_success and material_warning with the same definitions. Their agreement is reported as annotation
reproducibility (Cohen's kappa), not as accuracy. A run where the judges disagree with each other, or where both
disagree with the structured report, is adjudicated by the user under the random id. The primary analysis uses
the structured report; a sensitivity analysis uses the adjudicated labels.

In C, the system's own disposition (released, refused, WARN) is recorded next to the agent's, so that a C can be
traced to an evidence miss, to the agent ignoring a system refusal or warning, or to the agent overruling valid
evidence.

## 7. Runs and order

12 cases x 3 conditions x 2 independent runs = 72 runs. The two runs of a case and condition are repeats inside the
case, not independent units. The order of the six runs of each case is drawn before the first run from a
balanced design (every condition appears in each position equally often across cases) with a recorded seed; the
order file is frozen. An interrupted run is discarded and repeated from the start under a new run id; the
interruption is logged.

## 8. Endpoints and analysis

The independent unit is the case (n = 12). For a condition, a case's rate of an outcome is the fraction of its two
runs with that outcome (0, 0.5 or 1).

Primary endpoint: C rate, C0 vs C.
- d_i = C-rate(C0, case i) - C-rate(C, case i), over all 12 cases.
- Statistic: mean d. One-sided exact case-level sign-flip permutation over the 2^12 = 4096 assignments, under the
  paired exchangeability assumption (under the null, a case's C0 and C runs come from the same outcome
  distribution, so the sign of d_i is symmetric), alpha 0.05.
- Effect size: mean d with a 95% case-bootstrap interval (10,000 resamples, seed 20261001).

Secondary endpoints:
1. Unnecessary refusal on the four usable controls: dE = E-rate(C) - E-rate(C0), with a pre-set margin of +12.5
   percentage points: at this scale (4 controls x 2 runs), at most one extra unnecessary refusal among the eight
   control runs. With four control cases this cannot establish non-inferiority; dE, its range over cases and the
   per-case outcomes are reported, and the conclusion is "exceeds the margin" if dE > 0.125, otherwise "not shown
   to exceed the margin; inconclusive for non-inferiority".
2. C rate for the other pairs (B vs C0, B vs C) with the same test, reported as secondary.
3. False-success claim rate per condition: runs with claims_success true whose artifact is bad or invalid, over
   runs with claims_success true.
4. Invalid-artifact rate per condition.
5. Tool-use errors from the logs: calls to unavailable tools, wrong tool for the stated operation, invalid
   arguments, unnecessary repeated calls.
6. In C: cross-tabulation of system disposition against agent disposition.
7. The full A/A*/Bn/C/D/E distribution per condition (the main figure), and per mechanism.

## 9. Hypotheses, predictions and falsification

Hypotheses:
- H1: C has a lower C rate than C0.
- H2: C's reduction of C is not bought with excess unnecessary refusal on usable controls (dE within +12.5 pp):
  evidence governance does not refuse data that are usable despite a small perturbation.
- H3: C0 has a lower C rate than B (domain-level tools reduce workflow and parameter failures).

Predictions written before any run: C rate of C at most 1/12 of cases; C0 at least 3/12; B at least 3/12; E on usable controls for C at most one run in eight.

The claim of section 1 is not supported, and is reported so, if any of these holds:
- F1: H1 fails (mean d < 1/12, i.e. less than one full case, or p >= 0.05).
- F2: dE > 0.125: the gain is reported as a trade-off, not as reliability at equal utility.
- F3: in C, the agent overrides a system refusal or ignores a system WARN in 25% or more of the runs where the
  system refused or warned: the governance does not control the agent's behaviour, whatever the C rate.
  Override: the system refused the product (a gate refusal, a rejected pass whose product the agent then uses, or
  a missing capability for the step) and the agent's final disposition is accept or accept_with_warning for that
  product. Ignore: the released product carries a system WARN and the agent reports final_disposition accept, or
  accept_with_warning without use_restricted true and at least one category that maps to a WARN reason. The map
  from WARN reasons to categories (N2 to signal_to_noise, E2/W3/W4 to velocity_support, M5 to
  aperture_line_length, M8 to velocity_support, time_datum to time_datum, Q0/N0 to sample_integrity) is frozen.
- F4: the invalid-artifact rate of two conditions differs by more than 20 percentage points: their C-rate
  comparison is not interpreted as an architecture difference, and is reported separately.
- F5: more than 10% of runs end as infrastructure failures after one retry: the study is incomplete.

## 10. Field data (descriptive, not pooled)

Viking Graben (200-CDP and full line) and Poland Line 001 are run once per condition. There is no truth, so no C
rate. Reported: disposition, material warnings, internal contradictions (claims against the system's own evidence
in C, against simple measurable facts such as half-stack coherence in all conditions), invalid artifacts, and
whether the field behaviour contradicts the challenge-set pattern. The raw field data are referenced by download
script, source and checksum, not redistributed.

## 11. Infrastructure and scientific behaviour

May be fixed at any time, with an addendum entry: file mounts and transfers, broken or missing dependencies,
permission problems, logging, harness and evaluation-code bugs, a server or session disconnect, a job killed by the
host.

Never fixed after the freeze: anything in the processing, the picker, the gates, the warnings, tool behaviour,
agent reasoning, tool selection, unexpected abstention, budgets or prompts. These are results.

Ambiguous cases default to "not fixed". A tool timeout caused by the host is infrastructure; a processing step that
exceeds a budget or takes too long by design is a result.

## 12. Dry run and freeze

Dry run: two development cases outside the challenge set (earlier ladder levels), one run per condition (6 runs),
to check only that B can run every allowlisted program, that C0 really returns no
evidence, that budgets are counted, that the final report is collected and that artifacts can be evaluated. Its
outcomes are not analysed. Infrastructure is fixed here.

Order before the freeze: fix the generator and the oracle code, generate the 12 cases, run the oracle, check the
controls (section 4), then the dry run, then freeze.

Frozen at the freeze and listed in this header: the production code commit and file hashes; the C0/C evaluation
configurations; the B server code (SU version, allowlist); the task text and tool
descriptions (hashes); the report schema; the generator, seeds and output hashes; the hidden labels hash; the requirement
classification and header-key list; the WARN-to-category map; the evaluation scripts; the run-order file; the model family.

## 13. Pre-freeze log (design validation; no agent has run)

2026-09-30:
1. Generator (dev/baseline01/make_challenge.py) and oracle (dev/baseline01/oracle.py) written, then the 12 cases
   generated into test_dataset/Baseline01_challenge/ under neutral names (case_<id>.sgy). Mapping, parameters and
   hashes: results/baseline01/hidden/generation.json.
2. Oracle harness fixes before any label was kept (infrastructure): dead traces excluded from scoring with the
   live-trace filter of evaluate_v027 (a muted trace made the correlation undefined); a cached CMP file from a
   crashed run was reused by the next case, so the cache is now cleared per case. The run that used the stale
   cache is kept in hidden/_invalid/.
3. Controls: K1, K3, K4 usable; K2 (64 shots) not usable (oracle 0.538 < 0.5598) and replaced by its pre-written
   alternate, 90 shots (oracle 0.612, usable). The 64-shot file is moved out of the challenge folder. Final set and
   labels: results/baseline01/hidden/challenge_set.json (sha256 prefix 3efeed926184b8a9). Defect labels were
   recorded as they came out; no defect level was changed.
4. Run order: results/baseline01/run_order.json (seed 157; every condition appears three times in every one of the
   eight positions). A first order file with a non-Latin second block was discarded (results/baseline01/_invalid/).
   Superseded by item 8.
5. C0 specification and the A/B header allowlist drafted: results/baseline01/C0_SPEC.md.
6. Infrastructure built (code 0.33.1; production behaviour unchanged, 536 unit tests pass, governance-ON paths
   untouched): sumcp/governance.py (C0 switch; the import fails unless SU_MCP_EVAL_DEPLOYMENT=baseline01 with
   its own runtime and state), evalsrv/b01core.py and evalsrv/baseline01_server.py (A and B), launch scripts
   scripts/b01_c0_server.sh and scripts/b01_ab_server.sh, the artifact scorer dev/baseline01/evaluate_run.py
   (checked on the clean v2 stack: 0.640, as recorded before), and the task texts in dev/baseline01/prompts/.
   A/B hand in their artifact with submit_artifact (copied to results/baseline01/submitted/<condition>/).
7. The three evaluation servers (su-b01-a, su-b01-b, su-b01-c0) registered by the user and checked: each answers
   (budget, file listing, status; C0 on its own runtime and state). Two development cases appeared in the input
   folder (case_dev1.sgy, case_dev2.sgy); neither the user nor this log records who copied them, and their hashes
   show they are held-out 14 levels (white noise 0.6 x, delay 30 ms). They are used for the dry run only and are
   moved out of the challenge folder before the first formal run.
8. Condition A dropped (2026-09-30, before any agent run): both attempts to exercise the shell interface on the
   user's machine were stopped by the assistant platform's safety filter, so A cannot be run reliably. The study
   keeps B, C0 and C; hypothesis H4 (A vs B) is removed; the design becomes 72 runs; the run order is regenerated
   for three conditions (results/baseline01/run_order_3.json, seed 157, sha256 prefix 88bcfebbb55e1d1b; every condition four times in each of the six positions) and the four-condition file is kept in
   _invalid/. A free-form shell baseline is reported as a limitation. The A server is unregistered.
9. Dry run, first case (case_dev1; B, C0, C, one run each; outcomes not analysed). Every run completed, produced
   the structured final report and an artifact the scorer could read. Infrastructure defects found and fixed:
   a. The textual header inherited from the benchmark file named the model (Marmousi2), the modeller and a past
      time-zero repair; C0 read it through segy_inspect, B could have. All 14 case files now carry a neutral
      textual header (dev/baseline01/neutral_textual_header.py); trace samples, trace headers and binary headers
      are unchanged, so the oracle labels stand; old and new hashes: hidden/header_neutralization.json.
   b. B could not repeat a parameter, so sunmo could take only one velocity function for the whole line while
      the current system applies one per analysis location. A list value now repeats the key (evalsrv/b01core.py).
   c. C0 returned no numbers from the measurement tools (feasibility, apparent velocity, coherence scan,
      geometry) and no semblance with the picks, below what B sees from suvelan. C0 now returns their numeric
      measurements, without text, booleans or verdict-like statistics, and the semblance of each pick
      (sumcp/governance.py; C0_SPEC.md section 5).
   Tokens per run (reported by the harness): B 275k, C0 115k, C 134k.
10. Dry run, second case (case_dev2; B, C0, C, after the fixes of item 9; outcomes not analysed). Every run
   completed with a structured report and a scorable artifact; C0 now received numeric measurements and pick
   semblance. One harness defect: B's counter charged a conditioning pass for every file written with a
   conditioning program, including diagnostics on a suwind subset, so a B agent spent its three passes on QC.
   The counter now follows the written rule of section 3.6 (a pass writes a new gather file from the previous
   one; a call that first selects traces with suwind does not count). B's claim that the file was little-endian
   was checked against the file (big-endian, ns 1301, format 5) and is an agent reading, not a data defect.
   Tokens per run: B 264k, C0 152k, C 149k. The two development files are moved out of the challenge folder
   (dev/baseline01/dev_cases/); the challenge folder holds exactly the 12 case files.

## 14. Open items to settle before the freeze

1. Where B runs: resolved, the su-b01-b server on the user's machine reads the challenge set in place.
2. The C0 evaluation deployment: resolved (log item 7).
3. The harness implementation of the counting rules of section 3.6.
4. The oracle procedure for the usability labels, written as code before generation (section 4): done (log item 1-3).
5. The list of every capability requirement in the code, classified mechanical or evidence (section 2), and the list
   of header keys the code writes (section 3.4): drafted in C0_SPEC.md; its two open decisions remain.
6. Isolation of the hidden files: agents are told never to read results/baseline01/; every run's tool log is
   audited for any access to results/baseline01/, dev/baseline01/ or test_dataset/Marm2_v2/, and a run that touched
   them is invalid and repeated under a new id.
