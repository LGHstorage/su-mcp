# Baseline study 01: runbook for the orchestrating session

For the Claude session that runs the formal study. The study is frozen: read results/baseline01/CRITERIA.md
(sections 2-12) once, then follow this file. Never change code, task texts, cases, labels, the run order or the
criteria. The only file you add to is results/baseline01/LOG.md.

## What exists

- results/baseline01/runs.json: the 72 runs in order (seq 1-72), each with its case block (1-12), condition (B,
  C0, C), repeat, run name and the path and sha256 of its frozen task text (results/baseline01/run_prompts/).
- Evaluation servers on the user's machine: su-b01-b (condition B) and su-b01-c0 (condition C0); condition C uses
  the production seismic-unix server. Check at the start that `su-b01-b` and `su-b01-c0` tools appear in
  ToolSearch; if not, stop and tell the user.
- The results of the runs are not scored until all 72 have run (CRITERIA section 11: no look at outcomes while
  the study is running).

## How to run a block

The user decides how many case blocks to run in a session (a block = the 6 runs of one case). For each run of the
block, in seq order:

1. Read the task text from its path and check its sha256 against runs.json. A mismatch stops the study.
2. Launch it with the Agent tool: subagent_type general-purpose, no model override, the task text verbatim as the
   prompt, description "b01 <run>". At most three runs at the same time, taken in seq order.
3. When the agent returns, save its final report verbatim to results/baseline01/reports/<run>.md, and the JSON
   block from its end to results/baseline01/reports/<run>.json (if there is no JSON block, write
   {"run": "<run>", "no_answer": true}). Append one line to results/baseline01/LOG.md: seq, run, UTC end time,
   subagent tokens and duration as the Agent tool reports them, the model name if reported, and anything unusual.
4. Do not read the artifact, score it, or comment on the processing. Do not answer the agent or ask it anything.

## Interruptions and failures

- A run cut off by a disconnect, a session interruption or a dead job: discard it, log why, and run it again from
  the start under the same run name with the suffix -x2 (then -x3). Never continue a cut-off agent.
- A run that ends normally is final, whatever it did (abstention, errors, wrong processing). Never repeat it.
- If a step of yours is stopped by the platform's safety filter, do not retry it in another form; log it and tell
  the user.
- If a tool or server fails for everyone (infrastructure), stop the block, log it, and tell the user. Fixes are the
  user's decision and go in LOG.md as an addendum.

## End of a session

Report to the user in Korean: the runs done (seq range), any interruptions or failures, total subagent tokens, and
the next seq to run.
