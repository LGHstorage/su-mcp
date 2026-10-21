# Reproducing the results

This guide says what each result of the paper rests on, where the data come from and which script produces it.
Paths are relative to the repository root. All scripts refuse to overwrite existing output.

## 1. What can be checked from the repository alone

| Claim | Where |
|---|---|
| The code behaves as described | `python3 -m unittest discover -s tests -t .` (551 tests) |
| Each rule set had a criteria document before its code and a result document after | `results/v0150` … `results/v0330`: `CRITERIA.md`, `RESULT.md`, evaluation JSON |
| The invalidation rule | `sumcp/evidence.py` (`invalidate_downstream`, `superseded`), `tests/test_v0332_invalidation.py` |
| Agent experiment 1: frozen criteria, run log with the two harness corrections, scores | `results/baseline01/` (`CRITERIA.md`, `FREEZE.json`, `LOG.md`, `RESULT.md`, `scores.json`, `f3.json`) |
| Agent experiment 2: frozen criteria, interim scores, the stop decision | `results/baseline02/` (`CRITERIA.md`, `FREEZE.json`, `LOG.md`, `scores_stage1.json`) |

The documents under `results/` are development records. The result documents of rule sets 0.15 to 0.25 are English translations of the Korean originals.

## 2. Data

No seismic data are stored in the repository.

### Synthetic reference line

An acoustic finite-difference model of a part of Marmousi2 (Martin et al., 2006; AGL Elastic Marmousi,
https://wiki.seg.org/wiki/AGL_Elastic_Marmousi): 126 shots, 96 channels, 2 ms, 2.6 s.

| File | Place in the project | SHA-256 |
|---|---|---|
| `marm2_known_truth_v2_2p6s.sgy` (66 MB) | `test_dataset/Marm2_v2/` | `159c1363773cf10d1aaea51cc43de3060a9c00c97782fe8919c72317ddb71372` |

The line is available from the data archive of the paper: [data archive DOI to add].

The velocity model used for modelling and for the true rms velocity is in the repository
(`test_dataset/Marm2_known_truth/truth/`), as is the zero-offset reference section
(`results/marm2_oracle_diagnostic/er_zero_offset_reference.npz`).

The modelling code is `dev/marm2_oracle/acoustic_fd2d_v2.c` (shot records, `generate_v2.py`) and
`dev/marm2_oracle/exploding_reflector.c` (reference section, `run_er.py`). Compile with
`cc -O3 -fopenmp -o fd_v2 acoustic_fd2d_v2.c -lm` and `cc -O3 -fopenmp -o er exploding_reflector.c -lm`.
`generate_v2.py` copies trace headers from the first version of the line, which is not published; the modelling
code is given so that the method can be read, and the line itself is taken from the data archive.

### Field lines

| Line | Source | File used | SHA-256 |
|---|---|---|---|
| Viking Graben (Mobil AVO line 12; Keys and Foster, 1998) | https://wiki.seg.org/wiki/Mobil_AVO_viking_graben_line_12 | `test_dataset/VikingGraben/paracdp.segy` (CMP-sorted, 120,120 traces) | `73b5edc6e37001f785f8d45c4009adf96782038d11a7afe6236e068474d719d4` |
| Poland 2D Vibroseis Line 001 (Geofizyka Toruń) | https://wiki.seg.org/wiki/2D_Vibroseis_Line_001 | `test_dataset/Poland_Vibroseis/Line_001.sgy` with its SPS, RPS and XPS files | `c7618b674f07a42a07f8600cbfb5a26caba0aae04078654760aa52d67ee4af87` |

## 3. Degradation ladders

Each ladder is generated from the reference line with fixed seeds, written in the script.

```bash
python3 dev/marm2_ladder/make_ladder.py        # diagnostic ladder  -> test_dataset/Marm2_ladder/
python3 dev/marm2_ladder/make_heldout.py       # held-out ladder 1  -> test_dataset/Marm2_ladder_heldout/
python3 dev/marm2_ladder/make_heldout2.py      # ... to make_heldout14.py
```

The ladder made for a rule set is named in the criteria document of that rule set.

## 4. Processing and evaluation

Each level is processed through the server with the fixed protocol written in the criteria document of its rule
set (the sequence of section 6 of `docs/USER_GUIDE.md`, with the conditioning steps that the rule set allows).
The released stack is then compared with the reference section:

```bash
python3 dev/marm2_ladder/evaluate.py <ladder> matrix <output.json>      # early rule sets
python3 dev/marm2_ladder/evaluate_v031.py <output.json>                 # later rule sets, one script per version
```

`evaluate*.py` hold the quality measure (correlation with the reference between 0.7 and 2.4 s at the best lag
within 20 ms, median over traces) and the classification into outcome classes. The evaluation JSON recorded at
the time is beside each `RESULT.md`.

The code of earlier rule sets is not released as separate versions. Their results are documented by the
evaluation JSON and the recorded gate outcomes beside each `RESULT.md`. The repository holds the final version
(0.33.3); the rule that every stack a new rule was not meant to touch stays byte-identical is checked in
the result documents.

## 5. Figures

```bash
python3 dev/paper/figures_paper.py            # all processing figures -> figures/
python3 dev/paper/figures_paper.py chain      # one figure: chain, velocity, timezero, noise, statics, migration, viking, poland
```

The script reads the reference line, the ladder levels and the released products under `results/`. The products
are made by section 4; those used for the published figures are in the data archive.

## 6. Agent experiments

- `dev/baseline01/make_challenge.py`, `dev/baseline02/make_challenge.py`: the cases, with seeds.
- `evalsrv/`, `scripts/b01_ab_server.sh`, `scripts/b01_c0_server.sh`: the program-interface server (condition B)
  and the server with the criteria switched off (condition C0). Condition C is the normal server.
- `results/baseline0*/RUNBOOK.md`: how a run was started, isolated and logged.
- `dev/baseline01/score_all.py`, `dev/baseline02/score_all.py --stage 1`: classification and endpoints.
  `dev/baseline01/f3_system_vs_agent_rev1.py baseline01` (or `baseline02`): the F3 analysis. They read the
  reports, stacks, submitted artifacts, case parameters, and system manifests of the data archive, unpacked into
  the repository root; the scores they produced are
  `results/baseline01/scores.json` and `results/baseline02/scores_stage1.json`.

A new run of an agent experiment is not a reproduction in the strict sense: the language model is an external
service and its behaviour is not fixed.
