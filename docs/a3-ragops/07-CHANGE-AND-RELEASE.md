# 07 — Part C (change experiment, release gate) and F3 (controlled release)

Covers **C1-01, C1-02, C2-01…C2-04, C3-01, F2-05, F3-01…F3-05** (paper 4.1(d) Release, 4.2.5, 4.2.6 live testing). Owners: **A** (candidate, suite, gate), **B** (Deployments, release script, rollback). Tasks T28–T34. Formats: [14](14-INTERFACE-CONTRACTS.md) §5, §7.

The story you must be able to tell at the demo, in one breath: *we changed one thing, built the candidate in its own collection, ran the same three-level suite on baseline and candidate, a gate with thresholds from a ConfigMap decided, the bad candidate was stopped and never rolled out, the good one was released with a zero-downtime rolling update, and a release that went wrong in production was undone with `kubectl rollout undo` — after which the next trace shows the previous collection and embedding version.*

---

## 1. Vocabulary

| Term | Meaning here |
|---|---|
| **Baseline** `B0` | the live pipeline: `nomic-embed-text`, collection `rahbar`, release id `R1` |
| **Candidate** | the same pipeline with **one** change, in its own collection, served by `api-candidate` |
| **Candidate-bad** `Cb` | a deliberately worse variant of the **same change type**; must be stopped by the gate |
| **Candidate-good** `Cg` | the variant we expect to be at least as good; must pass the gate |
| **Gate** | `ragops.gate.apply`: compares two result files against `gate.yaml`, exit 0/1 |
| **Release** | copying the candidate's release-scoped settings onto the live Deployment, rolling update |
| **Release id** | `R<n>-<short>` stamped in the pod template and in every trace |

---

## 2. Choosing the one change (C1-01) — decision D-09

The PDF allows: chunk size or overlap, **embedding model**, reranker, top-k, prompt template. Pick **one** and write the choice and why into the report.

| Option | Module level moves? | Component | End-to-end | F3-05 ("trace shows previous **collection and embedding version**") | Cost (CPU) | Verdict |
|---|---|---|---|---|---|---|
| **Embedding model** | **yes** (gap, ms/chunk, determinism) | yes | yes | **meaningful** — both collection and embedding differ | re-embed ≈ 530+ chunks: minutes | **recommended** |
| Chunk size / overlap | barely (ms/chunk only) | yes | yes | collection differs, embedding same | re-chunk + re-embed | acceptable fallback |
| Top-k | no | yes | yes | nothing differs in collection/embedding | none | weak for F3-05 |
| Prompt template | no | no | yes | nothing differs | none | weak for F3-05 |
| Reranker | no | yes | yes | nothing differs in collection/embedding | needs new code | optional bonus |

**Recommendation (final choice recorded after the feasibility check below):** change the **embedding model**. Baseline `nomic-embed-text`. Candidate-good: a larger/stronger local model (e.g., `mxbai-embed-large`, 1024-d) **or** `bge-m3`/`snowflake-arctic-embed` if present. Candidate-bad: a deliberately weak/small model (e.g., `all-minilm`, 384-d). These names are *suggestions to try*, not claims about their quality on your corpus — the gate decides.

### 2.1 Feasibility check (30 minutes, before committing to the choice)
1. `ollama pull <model>` for each candidate; note size and the embedding dimension (`/api/embed` returns it).
2. Embed 20 chunks with each: time per chunk, no errors, finite vectors.
3. Read the model card for **text prefixes** and casing (A2 found `nomic-embed-text` needs `search_document:`/`search_query:` and lowercase input). Record the profile for each candidate (see §3).
4. Quick sanity: embed 3 paraphrases and 3 unrelated sentences; if the gap is not visibly positive, the model is broken in your setup.
If a candidate cannot be pulled or is unusably slow, fall back to **chunk size** (baseline 300/40; good 400/60; bad 80/0) — still one change, still three levels, but F3-05's embedding part will be "unchanged" and you must say so.

### 2.2 Candidate specification files
`ragops/config/candidates/<name>.yaml` (one per candidate; committed **before** the runs):

```yaml
name: cand-mxbai                       # label used in results, Deployment annotations, release id
release_id: R2-mxbai
change: embedding_model                # the single changed dimension (D-09)
collection: rahbar-cand-mxbai          # its own collection name (F3-01)
embed_model: mxbai-embed-large
embed_version: ""                      # filled from `ollama show` digest at build time, then committed
chunk_size: 300                        # unchanged from baseline (only the model changes)
chunk_overlap: 40
top_k: 5                               # unchanged
calibrates_floor_for: embed_model     # the floor moves WITH the embedding model; the validator rejects it otherwise
relevance_floor: 0.0                   # CALIBRATE (see 2.3); never reuse nomic's 0.60 blindly
cache_threshold: null                  # cache is off for the candidate
prompt_version: same                   # unchanged
expected: pass                         # your hypothesis, written BEFORE running (honesty)
```

### 2.3 Calibrate what an embedding change invalidates
Cosine scores are **not comparable across models**. A2 set `RELEVANCE_FLOOR=0.60` for `nomic-embed-text`; the same floor on another model can make the system abstain on everything or answer everything. For each candidate model, recompute the floor with the A2 method (highest floor that keeps every answerable golden question's gold passage above it; the data is in `ragops.suite` component output top-1 scores) and set it in the candidate spec. The **cache threshold** (A2: 0.95) is likewise model-specific; the candidate runs with the cache **off**, and the release must set a safe threshold or leave the cache on the old, validated value only if the same model — record the decision. **This is the most likely reason a "good" candidate fails the abstention gate** — it is a legitimate finding for the report.

---

## 3. Building the candidate

1. **Shared embedding profiles.** Today the document-side text preparation lives in `indexer/pipeline/embed.py` and the query-side in `api/app/retrieval/embedder.py`, each keyed on `model.startswith("nomic-embed-text")`. Add one small shared table (`embed_profiles`: `doc_prefix`, `query_prefix`, `lowercase`) imported by **both** so the pin cannot drift (the A2 pin rule). Unit-test that doc and query preparation use the same profile for each model. A candidate whose profile is wrong looks "bad" for the wrong reason.
2. **Build the index** as a Job: `python -m pipeline.run build-index --collection rahbar-cand-mxbai --embed-model mxbai-embed-large [--chunk-size … --chunk-overlap …]`. It reads the **verified documents from the lake** (the current set, plus archived ones flagged `superseded`) and writes a **new collection** with its own registry (`rahbar-cand-mxbai-registry`). It registers the index in the ledger (`indexes`), so later `sync` runs keep it current (§9 of [05](05-DATA-MANAGEMENT.md)). The live collection is never touched.
3. **Serve it:** `api-candidate` Deployment (1 replica) with the candidate's env (collection, embed model/version, floor, release id, `REDIS_URL` empty), distinct label `app: api-candidate`, its own Service `api-candidate`. Readiness passes only when the candidate collection exists, is non-empty and its recorded model matches (the A2 pin) — a wrong build fails visibly. See [10](10-KUBERNETES.md) §4.
4. Record `embed_version` = the Ollama model digest (`ollama show <model>` / `/api/tags`), commit it into the spec, and make the API read it from `EMBED_VERSION` (and log a warning if the running digest differs).

---

## 4. Comparing baseline and candidate on all three levels (C1-02)

Run the identical suite on each target, **same seed, same golden hash, same corpus state**:

```bash
# Jobs (the grading path):        kubectl apply -f k8s/eval-job.yaml   with target+label from the ConfigMap
make eval TARGET=live      LABEL=baseline
make eval TARGET=candidate LABEL=cand-mxbai
make eval TARGET=candidate LABEL=cand-minilm
```

The comparison table (also printed by the gate, and the basis of the report table):

| Level | Metric | Baseline | Cand-bad | Cand-good | Δ good | Direction | Gate rule |
|---|---|---|---|---|---|---|---|
| module | gap | | | | | ↑ better | `min_gap` (optional) |
| module | embed ms/chunk | | | | | ↓ better | informational |
| component | recall@3, recall@5 | | | | | ↑ | **max drop 0.02 (recall@5)** |
| component | MRR, nDCG@5 | | | | | ↑ | informational / optional |
| component | noisy recall@5 | | | | | ↑ | optional |
| end-to-end | faithfulness | | | | | ↑ | **min value** |
| end-to-end | abstention correctness | | | | | ↑ | **not lower than baseline** |
| end-to-end | false-abstention rate | | | | | ↓ | optional cap |
| end-to-end | citation validity | | | | | ↑ | min 0.95 (A2 carried over) |
| end-to-end | p95 latency | | | | | ↓ | **max value** |

Write two or three sentences per level on **why** the numbers moved (a bigger model: slower per chunk, bigger vectors, maybe better recall; a smaller one: faster, maybe worse on exact terms). The paper's point (4.2.5): the module-level change reaches the component and end-to-end levels — show the chain, or show where it **did not** (short answer (b)).

---

## 5. The release gate (C2) — config, thresholds, justification

### 5.1 `ragops/config/gate.yaml` (and the same content in ConfigMap `ragops-gate`, key `gate.yaml`)

```yaml
version: 1
require_same: [golden_hash, corpus_digest, suite_schema, seed]   # refuse to compare unlike runs
on_missing_metric: fail                                          # null/absent = fail, never pass
rules:
  - {id: recall5_drop,      level: component, metric: recall@5,                 type: max_drop_abs,           value: 0.02}
  - {id: abstention,        level: endpoint,  metric: abstention_correctness,    type: not_lower_than_baseline, value: 0.0}
  - {id: faithfulness_min,  level: endpoint,  metric: faithfulness,              type: min_value,              value: 0.XX}   # justify
  - {id: citation_validity, level: endpoint,  metric: citation_validity,         type: min_value,              value: 0.95}
  - {id: p95_latency,       level: endpoint,  metric: latency_p95_s,             type: max_value,              value: YY}     # justify
  - {id: false_abstain,     level: endpoint,  metric: false_abstention_rate,     type: max_increase_abs,       value: 0.10}   # optional
justification:                      # REQUIRED text per tunable threshold; the report copies it
  faithfulness_min: "…"
  p95_latency: "…"
```

Rule types: `max_drop_abs` (candidate may not fall more than `value` below baseline), `max_increase_abs`, `min_value`, `max_value`, `not_lower_than_baseline` (with tolerance `value`). Rules with `level` set cover **all three levels** at least once through the PDF's examples plus any module rule you add.

### 5.2 How to derive and justify the two free thresholds (C2-04)
Commit the derivation **before** you run the candidates (a git commit timestamped earlier than the candidate result files is your proof you did not tune the gate to pass).

* **Faithfulness minimum.** Take the baseline's faithfulness and the **run-to-run variation** measured by the stochasticity test (B-S-01). Set `min = baseline − max(0.05, 2 × |Δ_run1,run2|)`, rounded down to 2 decimals; write: "the baseline is X, runs vary by ±Y, so a candidate below X − Z is a real loss not noise". Also reconcile with the judge's hand-agreement: if agreement is poor, gate on the deterministic proxy and say why.
* **p95 latency maximum.** Tie it to a user-visible budget, not to the baseline alone: e.g., `max = min(1.25 × baseline_p95, UI/Ingress timeout margin)`. Show the arithmetic with your measured baseline p95 and the Ingress/client timeout you actually have (A2: answers take up to ~190 s; `terminationGracePeriodSeconds: 240`). A model that is slower per chunk and per answer on a CPU laptop is exactly what this rule catches.
* **recall@5 drop 0.02** and **abstention not lower than baseline** are the PDF's own examples; keep them as written unless you have a reason, and if you change a number say why.

Record the final numbers and arithmetic in `docs/a3-evidence/gate-thresholds.md` and in the report (G3 "faithfulness at least a value you justify").

### 5.3 The gate script — semantics (`python -m ragops.gate.apply`)

```
python -m ragops.gate.apply --baseline <result.json> --candidate <result.json> \
        --config ragops/config/gate.yaml [--decision-out decision.json] [--explain]
```

| Step | Behaviour |
|---|---|
| 1. comparability | for each key in `require_same`, baseline and candidate values must be equal; otherwise **exit 2** ("incomparable: corpus digest differs") — a gate that silently compares different data is worse than none |
| 2. evaluate | each rule → `pass`/`fail` with the baseline, candidate and limit values and the arithmetic |
| 3. missing | a metric `null`/absent ⇒ `fail` (`on_missing_metric: fail`) — never a green check from a missing denominator (A2 rule) |
| 4. decision | writes `decision.json` (rules, values, overall, config hash, both result file names and git SHA) **and** prints a table; overall `pass` only if **every** rule passes |
| 5. exit | **0** pass · **1** fail · **2** usage/incomparable/IO · never anything else |

Floating-point: compare after rounding to 4 decimals with `1e-9` tolerance; the boundary tests must show *exactly the limit passes, one step beyond fails*. Print the reasons in words (`recall@5 0.793 is 0.057 below baseline 0.850 (limit 0.020)`) — this output is **Screenshots C1 (fail) and C2 (pass)**.

---

## 6. Release decision (G3) — template

For each candidate fill (in the report, ≈ ¼ page each):

```
Candidate: <name> (change: embedding model nomic-embed-text → <model>), collection <c>, suite runs <file>.
Gate: PASS | FAIL (decision.json, config hash …). Rules failed: …
Evidence by level: module gap …, ms/chunk …; component recall@5 … MRR … nDCG@5 …; end-to-end faithfulness …, abstention …, p95 …
Residual risks: (e.g., calibration of the floor on a new score scale; slower generation; judge agreement n=…)
Decision: RELEASE | REJECT. Reasons (3 bullets). Rollback plan: kubectl rollout undo deployment/api; previous release R1 stays indexed (collection rahbar is kept current by ingestion).
```

Expected shape of the final write-up (to be *replaced* by your real outcome): the bad candidate is **rejected** and never rolled out; the good candidate is **released** — **only if its gate decision is a genuine pass**. If the "good" candidate fails, **reject it honestly** and report why; then use another genuinely better candidate or demonstrate the pass with a different valid candidate. Do not loosen the gate after seeing the numbers.

---

## 7. The release script (`scripts/ragops/release.sh`, owner B)

Preconditions it **enforces** (this is how "stopped by the gate and never rolled out" is mechanised — Kubernetes itself does not know about the gate, so say that in short answer (f)):

1. a `decision.json` exists for exactly this candidate `release_id`, with `overall: pass`, generated from the **current** config hash (not older than the candidate result);
2. `api-candidate` is Ready and serves the candidate collection (`/readyz` ok, trace shows the right collection);
3. no ingest Job is running (single writer; avoid releasing mid-update).

Action:
```bash
kubectl -n rahbar annotate deployment/api kubernetes.io/change-cause="release R2-mxbai (gate decision <sha>)" --overwrite
kubectl -n rahbar set env deployment/api \
  RELEASE_ID=R2-mxbai CHROMA_COLLECTION=rahbar-cand-mxbai EMBED_MODEL=mxbai-embed-large \
  EMBED_VERSION=<digest> RELEVANCE_FLOOR=<calibrated> TOP_K=5 PROMPT_VERSION=<same>
kubectl -n rahbar rollout status deployment/api --timeout=900s
```
(`set env` writes values **into the Deployment's pod template**; that is the whole point — see 04 §6 and 03 C-07.) After the rollout it prints `kubectl rollout history deployment/api`, sends one test question and prints the resulting trace's `release_id`, `collection`, `embedding`. Exit code: 0 success; 1 refused (gate); 2 rollout failed/timeout (**does not undo automatically** — undoing is a deliberate demo step, and in real use a decision).

`--dry-run` prints the commands. `--force` **does not exist** (an escape hatch would defeat F3-03).

---

## 8. F3 — the three live scenarios (script for demo and screenshots)

### Scenario S1 — candidate stopped by the gate, never rolled out (F3-03)
1. `api-candidate` serves `Cb` (bad). Run the suite Job against it, then the gate Job/command against the baseline → **FAIL** (Screenshot **C1**).
2. Run `release.sh` for `Cb`: it refuses (exit 1, "no passing gate decision"). Show `kubectl rollout history deployment/api` unchanged (still revision N) and `kubectl get deploy api -o jsonpath='{.spec.template.spec.containers[0].env}'` still `R1`.

### Scenario S2 — candidate passes, released with a rolling update (F3-02)
1. Same for `Cg` → gate **PASS** (Screenshot **C2**).
2. `release.sh` → `kubectl rollout status` shows pods replaced one at a time; in a second terminal `watch kubectl get pods -l app=api` and a loop of `curl` against the Ingress shows **no failed request** (`maxUnavailable: 0`, `maxSurge: 1`); the HPA keeps 3–8. Screenshot **F5**: `kubectl rollout status` output.
3. Send a question; the trace shows `release_id=R2-mxbai`, `collection=rahbar-cand-mxbai`, `embedding=mxbai-embed-large@<digest>`.

### Scenario S3 — a bad release, reversed with `kubectl rollout undo` (F3-04, F3-05)
A *release* is bad when it harms production even though offline tests passed, or when it is simply broken. Use the option that is honest for your run (state it in the report):

* **S3-a (deterministic, recommended for the demo):** release a configuration whose pods cannot become Ready — for example `CHROMA_COLLECTION` pointing at a collection that does not exist (a typo) or an embed model different from the collection's recorded model. The A2 readiness probe keeps the new pods **0/1 Ready**, the rolling update **stalls without taking down** any old pod (`maxUnavailable: 0`), `kubectl rollout status` waits then reports failure (`progressDeadlineSeconds` is 1800 in the A2 manifest; use `--timeout=120s` in the demo). Then `kubectl rollout undo deployment/api`.
* **S3-b (a *live* regression, more realistic):** release `Cg` with the **wrong relevance floor** (e.g., nomic's 0.60 on the new model's score scale). Pods are Ready, but `trace.summary` over the post-release window shows the abstention rate jumping and the top-1 similarity distribution shifted; the on-call decision is to undo.
* Either way: `kubectl rollout undo deployment/api` → `kubectl rollout status deployment/api` → ask a question → **the new trace shows `collection=rahbar`, `embedding=nomic-embed-text@<digest>`, `release_id=R1`** (Screenshot **F6** shows the undo **and** that trace). `kubectl rollout history` lists the revisions with their `change-cause`.

Explain why undo restores the collection and embedding: they live in the Deployment's pod template (`env`), and undo restores the previous ReplicaSet's template. If they had been in the shared ConfigMap, undo would not have changed them (C-07) — good viva material.

---

## 9. After the experiment

* The rejected candidate's collection is deleted by `ops unregister rahbar-cand-minilm` (single writer rule: via the Job). Keep the passing candidate's collection registered so ingestion keeps it current.
* Because ingestion maintains **every registered index** (05 §6.2b), after a release the previous collection `rahbar` continues to be updated, so `rollout undo` returns to a **current** index, not a stale one. If you chose not to implement multi-index maintenance, document that undo returns to a stale snapshot and re-run `sync` against it after the undo.
* Promote a new baseline **only** by an explicit reviewed step (`ragops.gate.promote --result <file> --reason "..."`, writes `baselines/live.json` with the reason); never from CI or automatically.

---

## 10. Tests

| Area | Cases |
|---|---|
| Gate | each rule type: pass, fail, exactly at limit, 1e-4 beyond; missing metric → fail; incomparable runs → exit 2; rounding; config hash changes with any threshold; threshold edit flips the outcome with the **same** result files (the F2-05 principle at unit level) |
| Candidate spec | rejects a spec that changes more than one dimension (`change` must name exactly one and the others equal the baseline). `relevance_floor` is a tracked dimension: it may differ only together with `embed_model` and `calibrates_floor_for: embed_model` (a per-model calibration, part of that one change); a floor change alone is rejected |
| Release script | refuses without a decision; refuses on a decision for another release id; refuses on a stale decision; `--dry-run` output stable |
| Embed profiles | doc vs query preparation share the profile; unknown model → no prefix, no lowercasing, flagged in the result |
| Manifests | the live Deployment's `env` contains the release-scoped keys; the candidate has `REDIS_URL` empty; strategy `maxSurge 1`, `maxUnavailable 0`; distinct selector labels |

---

## 11. Pitfalls

| Pitfall | Consequence | Defence |
|---|---|---|
| Changing two things at once (model **and** chunk size) | PDF says *one* change; attribution impossible | spec validator |
| Reusing nomic's floor/threshold on the new model | false abstention or false answers | recalibrate; make it part of the candidate spec |
| Release values in the ConfigMap | `rollout undo` does not restore them | explicit `env` in the pod template |
| Shared Redis between live and candidate | the two invalidate each other's cache | candidate cache off |
| Gate thresholds tuned after seeing candidate numbers | meaningless gate | commit thresholds + derivation first |
| Comparing runs on different corpus states | invalid | `require_same` |
| `--force` flag "for the demo" | contradicts F3-03 | do not build it |
| Releasing while an ingest Job is running | the live collection changes under the release | precondition 3 |
| Stale previous collection after release | undo serves stale data | ingestion maintains all registered indexes |
| Demo bad release that *crashes the cluster* | you lose the live demo | S3-a keeps old pods serving by design; rehearse it |
