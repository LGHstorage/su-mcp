# User guide

## 1. How the server sees a project

The project root (`SU_MCP_ROOT`, by default the repository directory) has fixed directories.

| Directory | Use | Access |
|---|---|---|
| `raw/` | field data | read-only; never overwritten |
| `test_dataset/` | external test data | read-only |
| `work/` | intermediate files | read and write |
| `results/` | products | read and write; an existing result is never overwritten |
| `qc/` | figures | read and write |
| `logs/` | `processing.jsonl`, one record per execution with inputs, parameters, outputs and hashes | append only |
| `state/` | one manifest per data set | written by the domain code only |

A path that leaves these directories, by an absolute path, `..` or a symbolic link, is refused.

Environment variables: `CWPROOT` (required), `SU_MCP_ROOT`, `SU_MCP_RUNTIME` (where `work/` lives, useful when the
project sits on a slow file system), `SU_MCP_STATE`, `SU_MCP_LOG_DIR`, `SU_MCP_DATA_DIRS` (extra read-only data
directories).

## 2. Data sets, capabilities and evidence

A data set is created by `dataset_import_segy` or `dataset_register_su` and is identified by a name you choose.
Its state is a set of capabilities, for example that the headers were parsed, that the fold is valid, that the
time origin is consistent, that a velocity model is validated, that a stack is complete. Each capability has

- a status: PASS, FAIL or UNKNOWN (a measurement that could not be made is UNKNOWN, not FAIL);
- the measurement that set it;
- the product it refers to.

`dataset_manifest` returns all of this. A tool states which capabilities it requires; if one is missing or
failed, the tool refuses and the refusal quotes the measurement.

## 3. Three verdicts on a product

A tool that makes a product ends in one of three ways.

- Accepted: the capability becomes PASS and later tools may use the product.
- Released with a restriction: the capability is PASS and a reliability record names each reason with its
  measured value (for example a half-stack bound below 0.95). Every product computed from it inherits the record.
- Refused: nothing is adopted and the reply says which measurement failed.

## 4. An acceptance expires

Products form a chain: velocity model, moveout correction, stack, time migration, depth image. When one is
replaced, every later capability returns to UNKNOWN and the files of later images are marked as superseded.
A new velocity pick withdraws the moveout correction, the stack and the images; an adopted conditioning pass
withdraws the velocity model and everything after it. `migrate_stack` with method `depth_convert` refuses a
migration that was made before the current stack, and `export_product` warns on a superseded file.

## 5. Tools

Inspection and general use

| Tool | Purpose |
|---|---|
| `su_status`, `su_search`, `su_help` | environment, program search, program documentation |
| `segy_inspect`, `su_inspect`, `su_preview`, `su_list_files`, `su_log` | read headers and samples, draw a preview, list files, read the execution log |
| `su_run`, `su_pipeline` | run Seismic Unix programs from an allow-list on files |
| `job_list`, `job_status`, `job_result`, `cancel_job` | long runs are jobs |

Data sets and geometry

| Tool | Purpose |
|---|---|
| `dataset_import_segy`, `dataset_register_su`, `dataset_list`, `dataset_manifest`, `dataset_forget` | create and inspect data sets |
| `geometry_analyze`, `survey_overview` | geometry from the headers, with the evidence for each quantity |
| `inspect_external_geometry`, `assign_external_geometry` | geometry from SPS or similar files |
| `measure_apparent_velocity`, `scan_coherence`, `fit_channel_geometry`, `fit_array_geometry` | measurements when headers are incomplete |

Processing

| Tool | Purpose | Main gate |
|---|---|---|
| `assess_reflection_feasibility` | is there reflection signal, and is the time origin consistent | direct-arrival intercept; coherence in band |
| `build_cmp`, `sort_cmp` | CMP numbers, sorted gathers, field statics | fold; corrupt samples; first-arrival intercept |
| `pick_velocity`, `refine_velocity` | stacking velocity at locations along the line | valid locations; support of the reflection window |
| `apply_nmo`, `stack_cmp` | moveout correction and stack | validated model; half-stack bound |
| `conditioning_menu`, `condition_gathers` | filters, datum shift, dip moveout, residual statics, removal of corrupt traces | injection test or the gate of the operation |
| `migrate_stack` | phase-shift time migration, depth conversion | focusing of synthetic diffractions; aperture; stability |
| `export_product` | copy a product from `work/` to `results/` | warns on a superseded product |

Normal moveout, stacking, velocity analysis, dip moveout, residual statics and migration cannot be reached
through `su_run` or `su_pipeline`. They run only inside the tools above.

Each data set allows six velocity analyses and three conditioning passes.

## 6. A typical session

```
dataset_import_segy(dataset_id="line-a", segy_file="raw/line.sgy")
geometry_analyze(dataset_id="line-a")
assess_reflection_feasibility(dataset_id="line-a")
build_cmp(dataset_id="line-a")
sort_cmp(dataset_id="line-a")
pick_velocity(dataset_id="line-a")
apply_nmo(dataset_id="line-a")
stack_cmp(dataset_id="line-a")
migrate_stack(dataset_id="line-a", method="phase_shift_smooth")
dataset_manifest(dataset_id="line-a")
```

The full argument list of each tool is in its description, which the MCP client shows. If a step is refused,
read the quoted measurement: it names the capability that is missing and, where one exists, the operation that
could supply it (for example a datum shift for a displaced time origin).

## 7. What the system does not do

It does not judge geology and it does not promise a good image. It reports what was measured, releases what the
measurements support and says what they do not support. A product released with a restriction is usable within
that restriction; a refusal on a noisy line is a result.
