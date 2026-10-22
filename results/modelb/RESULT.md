# Second geological model: result

2026-10-21. Criteria in CRITERIA.md (written before the model existed, with Addendum 1 before any run). SU-MCP 0.33.3
was run without any change of code, threshold, or protocol. Numbers in eval_modelb.json, computed by
dev/modelb/evaluate_b.py. Shot records: test_dataset/ModelB/modelb_clean_2p6s.sgy (sha256 9ebc193c...), identical from the
cloud and the local build of the modeler. Degraded copies: test_dataset/ModelB/ladder/ (provenance.json).

## Summary

The test met its criteria. No released stack was class C, the clean line was released without a warning, and no
level was refused. Seven of the eight released stacks were good and carried no material warning (class A), and the
one stack below the good threshold carried a quality warning (class Bn). There was no warning on a good stack.

The good threshold is 0.664 (0.9 of the clean quality 0.738).

## Levels

| level | path | released quality | reference stack | reliability | class | prediction | correct |
|---|---|---|---|---|---|---|---|
| clean | DMO adopted, residual statics refused (immaterial, 2.0 ms) | 0.738 | 0.707 | OK | A | A | yes |
| delay 60 | datum shift by the measured lag of 58 ms adopted, DMO adopted | 0.741 | 0.649 | OK | A | A | yes |
| band 1.0 | DMO adopted | 0.709 | 0.693 | OK | A | A or A* | yes |
| band 1.6 | first stack warned (half-stack bound 0.929); after DMO the bound was 0.956 and the warning cleared | 0.683 | 0.670 | OK | A | A* or Bn | no (better) |
| band 2.0 | DMO adopted, bound 0.937 | 0.639 | 0.652 | WARN (N2) | Bn | Bn | yes |
| white 1.0 | feasibility inconclusive, time origin not measurable (direct wave absent), DMO adopted | 0.715 | 0.689 | CAUTION | A | A or A* | yes |
| statics 16 | feasibility inconclusive, DMO adopted, residual statics refused (receiver reliability 0.86 < 0.9) | 0.684 | 0.651 | CAUTION | A | A or A*, residual statics adopted | class yes, statics no |
| statics 12 + band 1.0 | feasibility inconclusive, DMO adopted, residual statics refused | 0.684 | 0.655 | CAUTION | A | A* or Bn | no (better) |

Totals: A 7, A* 0, Bn 1, C 0, D 0, E 0.

## Observations

1. The result does not show that the rules detect silent failures in general on model B. Only one level produced a
   stack below the good threshold, and it was warned.
2. No good stack carried a quality warning, unlike the last Marmousi2 ladder (four of six). On model B the half-stack
   bounds of the good stacks were 0.956 or more, and the bad stack had 0.937.
3. Residual statics were refused on both statics levels because the receiver solution was not repeatable between the
   two random CMP halves. The released stacks were still good, because the measured velocity and dip moveout absorbed
   part of the statics. The reference stacks of these levels, which keep the statics and use the clean-line velocity,
   were below the threshold.
4. As on Marmousi2, the released stacks were better than the reference stacks, because the system measured the velocity
   on the degraded data.
