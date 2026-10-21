# Protocol P6 (v0.24 formal run) -- to be run after the MCP server is restarted

P6 = P5 of v0.23 for the stack (unchanged), then migrate_stack twice per released stack:
method "phase_shift" (default) and method "phase_shift_blend" (run_as_job=true; the blend takes a few minutes).
Stack-1 copies go to results/v0240/stacks/. Frozen v0.20-v0.23 datasets are not touched; all ids are new.

| id | source | steps |
|---|---|---|
| v024-viking | test_dataset/VikingGraben/cdp1000_1199.segy | P5 regression (cdp 1100, 25 m, no conditioning), then both migrations |
| v024-v2 | test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy | full P5, then both migrations |
| v024-h9-st15 | test_dataset/Marm2_ladder_heldout9/statics_15ms.sgy | full P5, then both migrations |
| v024-h9-bn100 | test_dataset/Marm2_ladder_heldout9/bandnoise_1p00x.sgy | same |
| v024-h9-wn100 | test_dataset/Marm2_ladder_heldout9/whitenoise_1p0x.sgy | same |
| v024-h9-dl080 | test_dataset/Marm2_ladder_heldout9/delay_080ms.sgy | same |
| v024-h9-st15bn | test_dataset/Marm2_ladder_heldout9/statics15_bandnoise_0p80x.sgy | same |

Checks after the run:
- sha256 of results/v024-viking_stack.su = 181fc5ba..., of the v024-v2 stack 1 = 7374cb63...
- stack quality: python3 dev/marm2_ladder/evaluate_v024.py results/v0240/eval_v024.json
- migration quality: python3 dev/marm2_ladder/evaluate_migration.py . results/migration_reference/er_mig_true_blend.npz
  results/<id>_stack.su results/<id>_mig_phase_shift.su results/<id>_mig_phase_shift_blend.su
- M1 verdicts, M2, M3 and inherited reliability from state/datasets/<id>.json (migration.completed evidence;
  the capability holds the last call, so record each method's tool output as it returns).
