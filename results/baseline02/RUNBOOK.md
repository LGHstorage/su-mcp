# Baseline study 02: runbook for the orchestrating session

For the Claude session that runs the study. The study is frozen: read results/baseline02/CRITERIA.md once, then
follow this file. Never change code, task texts, cases, labels, the run order or the criteria, and never read
anything under results/baseline02/hidden/ (stage_case.py reads it for you). The files you write are
results/baseline02/LOG.md, reports/, transcripts/ and, for an interrupted run, run_prompts_x2/.

## What exists

- results/baseline02/runs.json: the 72 runs in order (seq 1-72), each with its stage (1 or 2), case block (1-18),
  condition (C0 or C), repeat, run name and the path and sha256 of its frozen task text.
- Servers on the user's machine: su-b01-c0 (condition C0) and the production seismic-unix (condition C). Check at
  the start that both appear in ToolSearch; if not, stop and tell the user.
- Stage 1 is seq 1-36 (blocks 1-9), stage 2 is seq 37-72. **Stop after seq 36** and tell the user: the interim
  analysis is the user's, and stage 2 starts only when the user says so. Do not score anything yourself.

## How to run a block (the four runs of one case)

1. `python3 dev/baseline02/stage_case.py <case_id>` and check that it prints "staged ... sha256 ok".
2. For each run, read its task text and check its sha256 against runs.json. A mismatch stops the study.
3. Launch with the Agent tool: subagent_type general-purpose, no model override, the task text verbatim as the
   prompt, description "b02 <run>". Run positions 1 and 2 together, then positions 3 and 4 together; never more
   than two runs at once, never two blocks at once.
4. When an agent returns: copy its subagent transcript to results/baseline02/transcripts/<run>.jsonl; save its
   final report text verbatim (from the transcript) to reports/<run>.md and the JSON block at its end to
   reports/<run>.json (no JSON block: {"run": "<run>", "no_answer": true}). Append one line to LOG.md: seq, run,
   UTC end time, subagent tokens and duration, the model if reported, anything unusual.
5. Do not read the artifact, score it, or comment on the processing. Do not answer the agent or ask it anything.

## Interruptions, failures, audit

- A run cut off by a disconnect, a session interruption or a dead job: discard it, log why, and run it again from
  the start as <run>-x2 (task text = the frozen text with the run name replaced by <run>-x2 everywhere; record it
  in run_prompts_x2/reruns.json with "run", "replaces", "prompt", "sha256", "source_sha256", "reason").
- A run that ends normally is final, whatever it did. Never repeat it, except when the audit marks it INVALID.
- At the end of each session run `python3 dev/baseline02/audit_transcripts.py`, log its output, and repeat every
  INVALID run as <run>-x2 (stage its case first).
- If a step of yours is stopped by the platform's safety filter, do not retry it in another form; log it and tell
  the user. If a tool or server fails for everyone, stop, log it, and tell the user.

## End of a session

Report to the user in Korean: the runs done (seq range), interruptions or failures, the audit result, total
subagent tokens, and the next seq to run.
