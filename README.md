# SU-MCP

Evidence-gated seismic processing over CWP/Seismic Unix, operated through the Model Context Protocol (MCP).

SU-MCP is a processing layer in which every product (CMP gathers, velocity model, moveout correction, stack,
migration) is accepted, released with a stated restriction, or refused according to quantities measured on the
data. An acceptance is withdrawn when a product it rested on is replaced. A language-model agent, or a script,
operates the layer through 38 MCP tools; the acceptance decisions are made by deterministic code.

Version 0.33.3. Licence: AGPL-3.0 (see `LICENSE`).

## What is in this repository

| Path | Content |
|---|---|
| `server.py` | MCP server: declares the tools, holds no logic |
| `sumcp/` | The domain package: parsing, measurements, acceptance criteria, evidence records, invalidation |
| `tests/` | Unit tests (551), runnable without an agent |
| `scripts/`, `examples/` | Installation, environment check, launcher, example MCP client configuration |
| `evalsrv/` | The two comparison servers of the agent experiment (program interface; criteria switched off) |
| `dev/marm2_oracle/` | Finite-difference modelling of the reference line and its zero-offset reference section |
| `dev/marm2_ladder/` | Generators of the degradation ladders (with their seeds) and the evaluation scripts |
| `dev/baseline01/`, `dev/baseline02/` | Case generators, scoring and freeze scripts of the agent experiments |
| `dev/modelb/` | Model, shot records, reference section, degraded copies, evaluation and figure of the second geological model |
| `dev/paper/` | The script that draws the processing figures of the paper |
| `results/v0150` … `results/v0330` | For each rule set: the criteria document written before the code, and the result document |
| `results/modelb/` | Criteria and result documents of the test of the final rule set on the second geological model |
| `results/baseline01`, `results/baseline02` | Frozen criteria, run log, scores and freeze manifests of the agent experiments |
| `docs/` | User guide and reproduction guide |

Seismic data are not stored here. `docs/REPRODUCE.md` says where each data set comes from and gives checksums.

The criteria, result, and log documents under `results/` are development records, kept in the order in which they
were written. The result documents of rule sets 0.15 to 0.25 were written in Korean and are given here in English
translation, with numbers, file names, and decisions unchanged.

## Requirements

- Linux (developed on Ubuntu under WSL2).
- CWP/Seismic Unix, built from source with its `src` tree present; `CWPROOT` must point to it. Tested with release 44R24 (25 March 2022).
- Python 3.10 or later with `mcp[cli]>=2.0`, `numpy>=1.24`, `matplotlib>=3.7` (`requirements.txt`).
- A C compiler, only to rebuild the modelling programs in `dev/marm2_oracle/`.

No GPU is needed and a laptop is sufficient. The unit tests take about 80 s on one core. The synthetic
reference line has 12,096 traces and the largest field line used in the paper has 120,120.

## Installation

```bash
git clone <repository URL> su-mcp && cd su-mcp
export CWPROOT=/path/to/cwp
bash scripts/install.sh          # creates .venv, installs dependencies, makes small test data, runs checks
```

Run the tests:

```bash
export PATH=$CWPROOT/bin:$PATH
python3 -m unittest discover -s tests -t .
```

Register the server in an MCP client (`examples/mcp_config.json`):

```json
{
  "mcpServers": {
    "seismic-unix": {
      "command": "/home/USER/su-mcp/.venv/bin/python",
      "args": ["/home/USER/su-mcp/server.py"],
      "env": {"CWPROOT": "/home/USER/cwp", "SU_MCP_ROOT": "/home/USER/su-mcp"}
    }
  }
}
```

On Windows with WSL, point the client at `wsl.exe` and `scripts/mcp_launch.sh`, which sets the environment itself.

## A first run

Put a SEG-Y file under `raw/` (read-only for the server) and ask the agent, or call the tools in this order:

```
dataset_import_segy  ->  geometry_analyze  ->  assess_reflection_feasibility  ->  build_cmp  ->  sort_cmp
->  pick_velocity  ->  apply_nmo  ->  stack_cmp  ->  migrate_stack
```

Each call returns the measurements it made and either a product or a refusal that quotes the measurement.
`dataset_manifest` shows the capabilities of a data set with their status (PASS, FAIL, UNKNOWN) and evidence.
`docs/USER_GUIDE.md` describes the tools, the verdicts and the directory rules.

## Reproducing the paper

See `docs/REPRODUCE.md`: reference line, degradation ladders, evaluation, figures and the agent experiments.

## Limits

The processing ends at post-stack time migration and a depth conversion. Prestack migration, multiple
attenuation, refraction statics and crooked-line binning are not implemented. The acceptance criteria were
developed on one synthetic geological model, tested unchanged on a second one, and applied to two public field lines. The domain tools call Seismic
Unix programs directly; no other processing package is supported.

## Citation

[Paper reference to add on publication.]

Data archive: Lee, G., 2026. SU-MCP validation data and agent experiment records, version 1.0. Zenodo.
https://doi.org/10.5281/zenodo.23549047
