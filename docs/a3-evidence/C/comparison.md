| Level | Metric | baseline | cand-minilm | cand-mxbai | cand-llama1b |
|---|---|---|---|---|---|
| target | embedding model | nomic-embed-text | all-minilm | mxbai-embed-large | llama3.2:1b |
| module | paraphrase mean cosine | 0.823 | 0.641 | 0.817 | 0.842 |
| module | unrelated mean cosine | 0.497 | 0.116 | 0.411 | 0.570 |
| module | gap | 0.327 | 0.525 | 0.406 | 0.272 |
| module | embed ms per chunk (mean) | 525.337 | 58.446 | 1051.490 | 2155.778 |
| component | recall@3 | 0.775 | 0.775 | 0.825 | 0.450 |
| component | recall@5 | 0.800 | 0.800 | 0.850 | 0.600 |
| component | MRR | 0.725 | 0.742 | 0.700 | 0.487 |
| component | nDCG@5 | 0.727 | 0.733 | 0.738 | 0.489 |
| component | noisy recall@5 | 0.750 | 0.725 | 0.775 | 0.475 |
| endpoint | faithfulness (judge) | 0.947 | 0.944 | 0.947 | 0.857 |
| endpoint | abstention correctness | 1.000 | 1.000 | 0.833 | 1.000 |
| endpoint | false abstention rate | 0.050 | 0.100 | 0.050 | 0.300 |
| endpoint | citation validity | 1.000 | 1.000 | 1.000 | 1.000 |
| endpoint | latency p50 (s) | 99.570 | 85.130 | 107.070 | 59.700 |
| endpoint | latency p95 (s) | 153.040 | 175.350 | 190.870 | 87.790 |
| **gate** | **verdict** | **(baseline)** | **PASS** | **FAIL** | **FAIL** |

Module level for cand-minilm is from the corrected module-only run.
