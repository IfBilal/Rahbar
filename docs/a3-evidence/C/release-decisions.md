# Part C: release decisions

One change, the embedding model. Same suite, same seed, same golden set (hash 2cabdf74ca990ab2), corpus state A,
the thresholds of `ragops/config/gate.yaml` (derived from the two baseline runs and committed before any
candidate ran). Numbers: `comparison.md`; decisions: `eval/results/*_cand-*.decision.json`.

| Candidate | Spec (written before the run) | Predicted | Gate | Decision |
|---|---|---|---|---|
| `cand-minilm` (all-minilm, floor 0.25) | expected: fail | fail | **PASS** | **RELEASE** |
| `cand-llama1b` (llama3.2:1b as embedder, floor 0.50) | expected: fail | fail | **FAIL** (recall@5 0.80 to 0.60, faithfulness 0.857 below 0.89) | **REJECT**, never rolled out (`release.sh` refused, exit 1) |
| `cand-mxbai` (mxbai-embed-large, floor 0.50) | expected: pass | pass | **FAIL** (abstention correctness 0.833 against 1.000) | **REJECT** |

**cand-minilm: RELEASE, with reservations.** The gate passed every rule: recall@5 0.800 (unchanged), faithfulness 0.944
(floor 0.89), abstention 1.000, citation validity 1.000, p95 175.4 s (limit 225). Embedding is 9 times faster per chunk
(58 ms against 525 ms) and vectors are half the size (384 against 768 dimensions). Reservations the gate does not
cover: false abstention doubled (0.10 against 0.05; no rule limits it), 74 of 532 chunks (14 percent) were embedded
from a shortened text because the model's 512-token context refuses dense table pages, and the calibrated floor (0.25)
is so low that 5 of 6 unanswerable questions reach the model, so abstention rests on the model rather than the floor.
It was released with a rolling update (47 of 47 probe requests answered, `docs/a3-evidence/F/F5-*`) and then rolled
back after the demonstrations so that the Batch B experiment changes one thing. Our prediction that it would fail was
wrong: a smaller embedding model is not necessarily a worse one on this corpus.

**cand-llama1b: REJECT.** A general language model has no retrieval training. recall@3 fell from 0.775 to 0.450 and
the false abstention rate rose to 0.30. The gate stopped it and the release script refused it.

**cand-mxbai: REJECT.** It retrieved best (recall@5 0.850, recall@3 0.825), but the gate caught one regression: the
Canada visa question (g022, which must be declined) was answered. mxbai's top-1 score for it cleared the floor, and
the model replied that the student "cannot apply using the provided evidence passages", which in substance declines
but is recorded as an answer with a citation, so abstention correctness fell to 0.833. A candidate that retrieves
better can still fail the gate because its score scale needs its own floor. We did not re-tune the floor after seeing
the result: that would tune the candidate to the test set. It is recorded as the follow-up.

Caveat on the module level: the first run of `cand-minilm` embedded with the wrong model (a bug in our suite, since
fixed with a test); its module-level rows come from `C1-module-minilm-corrected.txt`. The gate rules do not use the
module level, so the decision is unaffected. The module level also shows why it is not enough on its own: minilm's
paraphrase/unrelated gap (0.525) is far better than nomic's (0.327) while its end-to-end quality is the same, and
mxbai has the second-best gap and the best recall and still fails on abstention.
