# Baseline study 02: does evidence governance make an agent's release statement match the result (criteria)

Status: FROZEN 2026-10-04 (manifest results/baseline02/FREEZE.json, written after this file). From here this
document is never edited; findings go in results/baseline02/LOG.md. Written after baseline study 01 (results/baseline01/RESULT.md), whose
pre-registered claim was not supported: the silent-wrong rate was 0 in both C0 and C, so that endpoint could not
separate them. Study 01 is reported as it is. This study tests, on new data, the difference that study 01 showed
only after the fact; nothing from study 01 is re-scored or pooled.

Everything not stated here is as in results/baseline01/CRITERIA.md and its LOG addenda 1-2 (task text, report
schema, budgets, modality, material-warning rule, truth metric and good threshold 0.5598, output contract,
infrastructure rule of section 11, staging of one case file at a time, transcript archive and audit, reruns only
for interruptions or harness defects).

## 1. Claim under test

> With evidence governance, what the agent says about its released stack matches what the stack is: good stacks
> are released for normal use, and bad stacks are released only with a restriction or not at all.

## 2. Conditions

C0 (governance off, su-b01-c0) and C (production), code 0.33.1 as frozen for study 01, same model family, same
task text. Condition B is not run: it does not bear on this claim, and its study 01 result stays descriptive.

## 3. Outcome of a run

Classes as in study 01 section 5 (A, A*, Bn, C, D, E). A run is **concordant** when its class is A (good,
released without material warning), Bn (bad, released with a material warning) or D (not usable, abstained), and
discordant when it is A* (good but restricted), C (bad, no warning) or E (usable, abstained).

## 4. Cases (18, all new)

All from test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy with seeds 161 onward (never used). The first
draft had 12 cases; six (P7-P9, Q7-Q9) were added before any run and before the freeze, for power: the study 01
data, re-scored with this endpoint while testing the scoring script, gave mean d 0.29 with p 0.047 on 12 cases. Every case
contains at least one seeded element, so no file repeats a study 01 file. Levels are written here and not tuned.

| id | kind | case |
|---|---|---|
| P1 | defect, time datum | recording delay 55 ms + white noise 0.2 x |
| P2 | defect, S/N band | band-limited noise (4-16 Hz) 1.5 x |
| P3 | defect, S/N white | white noise 3.5 x |
| P4 | defect, statics | surface-consistent statics 24 ms rms |
| P5 | defect, statics + noise | statics 12 ms rms + band noise 1.2 x |
| P6 | defect, aperture | line cropped to 36 shots around shot 45 + white noise 0.2 x |
| P7 | defect, time datum | recording delay 80 ms + white noise 0.2 x |
| P8 | defect, S/N band | band-limited noise 2.2 x |
| P9 | defect, geometry headers | offset header doubled, coordinates correct + white noise 0.2 x |
| Q1 | benign | white noise 0.3 x |
| Q2 | benign | band noise 0.4 x |
| Q3 | benign | recording delay 8 ms + white noise 0.2 x |
| Q4 | benign, short line | 90 shots around shot 60 + white noise 0.2 x |
| Q5 | benign | statics 4 ms rms |
| Q6 | benign | white noise 0.6 x |
| Q7 | benign | band noise 0.25 x |
| Q8 | benign | white noise 0.45 x |
| Q9 | benign, short line | 100 shots around shot 66 + white noise 0.2 x |

The kind column only stratifies the order; a run's truth is its own artifact's score, whatever the kind. The
oracle labels are computed before the freeze as in study 01. A benign case that is not usable under the oracle is
replaced by a pre-written alternate (half its perturbation); a defect level is never changed.

## 5. Runs, order and stages

18 cases x 2 conditions x 2 runs = 72 runs. A block is the four runs of one case, order balanced over cases and
drawn with a recorded seed before the first run. The blocks are split before the first run into stage 1 (nine
cases drawn at random, four of one kind and five of the other) and stage 2 (the other nine).

Interim look after stage 1 (36 runs), **for futility only**: the 24 runs are scored and d (section 6) is computed
over the nine cases. If mean d <= 0 the study stops and is reported as not supporting the claim. Otherwise stage 2
runs unchanged. No claim of support can be made at the interim, nothing (cases, levels, code, prompts, criteria) is
changed after it, and the final test uses all 18 cases at the full alpha. Stopping only for futility cannot raise
the false-positive rate of the final test.

## 6. Endpoints

The independent unit is the case (n = 18).

Primary: concordance, C vs C0. d_i = concordance-rate(C, case i) - concordance-rate(C0, case i). Statistic mean d;
one-sided exact sign-flip permutation over 2^18 assignments, alpha 0.05; 95% case-bootstrap interval (10,000
resamples, seed 20261101).

Secondary, reported without a claim: the class distribution per condition; restricted release of good artifacts
(A* over good); warning on bad artifacts (Bn over bad); C rate; E rate; mean best-lag quality per case; false
success claims; invalid artifacts; in C, system disposition against agent disposition (F3 of study 01).

## 7. Hypothesis and falsification

H: mean d > 0. Prediction: mean d at least 0.25; C concordant in at least 13 of 18 cases on both runs.

The claim is not supported, and is reported so, if: mean d < 1/18 (less than one full case) or p >= 0.05; or C's C rate exceeds C0's by
more than one case (governance must not buy concordance with silent failures); or the invalid-artifact rates
differ by more than 20 percentage points; or more than 10% of runs are infrastructure failures after one retry.

## 8. Before the freeze (done)

1. Cases: dev/baseline02/make_challenge.py (the study 01 perturbation code, neutral textual header written at
   generation), records in results/baseline02/hidden/. Oracle labels with the study 01 oracle procedure
   (dev/baseline02/oracle.py): all nine benign cases usable (0.57-0.605), no alternate needed; defects P1, P4, P6,
   P7, P9 usable after the known correction, P2, P3, P5, P8 not. No level was changed after the labels.
2. Order, stage split and the 72 task texts: dev/baseline02/finalize_design.py (seed 181); runs.json,
   run_order.json, run_prompts/. The task text is study 01's with the run name, the case path and
   "results/baseline01/, results/baseline02/" in the do-not-read rule.
3. Scoring fixed before the first run: dev/baseline02/score_all.py (--stage 1 for the interim), checked on the
   study 01 reports. Staging and transcript audit: dev/baseline02/stage_case.py, audit_transcripts.py.
4. Production code and the C0 server are byte-identical to the study 01 freeze (0.33.1). More than 10% of runs
   ending as infrastructure failures after one retry is judged from LOG.md, not by the script.
5. Runbook: results/baseline02/RUNBOOK.md (two runs at a time, one case staged at a time, stop after seq 36).
