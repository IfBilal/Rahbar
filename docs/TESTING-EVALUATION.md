# Test matrix, golden set, retrieval scores and enforced CI gate

Golden set first, tuning second: **≥15 questions**, minimum 8 ordinary + 2 version-sensitive + 2 exact-term + 2 must-abstain + 1 prompt-injection. Record known relevant passages as `(source, section)` or stable chunk IDs **before** seeing retrieval results. `eval/run_eval.py` runs against the *live* stack, writes `eval/results.json`, and must enforce three thresholds: recall@5 must not fall more than **0.05 absolute** below committed baseline; **100%** correct must-abstain; **≥95%** citation validity. Also report recall@3/5 and by-type performance.

**CI distinction:** `eval/fixtures/` is a small fictional corpus and has its own six-question golden set. Real corpus quality metrics and fixture CI tests are different measurements; never replace the real evaluation with stub-only fixture success. Implement existing four `STARTER-TODO` functions in `eval/run_eval.py`.

## Exact metric semantics and assertions

Let `G(q)` be distinct gold `(source,section)` pairs manually labeled for question q, and `R_k(q)` the distinct top-k retrieved pairs. For answerable questions:

`recall@k(q) = |G(q) ∩ R_k(q)| / |G(q)|`.

For must-abstain questions with empty `G(q)`, report recall as `null` / not applicable and exclude from average denominators; **do not turn 0/0 into 1.0**. Record both macro-average recall across eligible questions and recall@5 by type. The assignment requires recall@3 and recall@5. If labels use chunk IDs instead, explicitly normalize identifier matching before counting.

Citation validity is `number of citations whose (source,section,page) match this response's retrieved references / total citations`. Zero citations require special handling: report N/A rather than pretending 100% validity, but fail or flag answerable responses claiming context with no citation. Compute global percent using a count-weighted numerator/denominator, and separately count citation-less answered responses. Must-abstain correctness is `correctly declined must-abstain / total must-abstain`, and must equal **1.0**.

Gate should return a **non-empty list of failures** (and script exit 1) for any of these: baseline recall@5 minus current recall@5 greater than 0.05 absolute; must-abstain less than 1.0; citation validity less than 0.95. Baseline creation must be an explicit, reviewed step, never a CI-side auto-update. Ensure invalid/empty evaluation data fails rather than achieving a green check via missing denominators.

### Integration test matrix by stage

| Stage | Normal case | Negative/chaos case | Owner |
|---|---|---|---|
| Corpus | manifest SHA matches 6+ downloaded docs | altered checksum, missing old version | A |
| Extract | PDF text, OCR, HTML, table, MD | scan no OCR, corrupt PDF, mixed pages | A |
| Chunk | long definition, section and page survive | size=0, no overlap, duplicate ID | A |
| Embed | fixed dimension, equal vectors count | provider timeout, NaN vector, pin mismatch | A |
| Store | nonempty immutable generation | interrupted staging, duplicate job | A+B |
| Retrieve | cosine similarity, current versions | old-only hits, top_k=1, absent question | A |
| Generate | valid Answer/citations | malformed JSON, injection, model offline | A |
| Cache | semantic paraphrase hit and TTL | false hit, follow-up, stale generation | A |
| Health | live `/healthz`, ready `/readyz` | slow Chroma, down Redis, wrong pin | B |
| Network | UI→API→Chroma and API→Redis allowed | UI→Chroma rejected, DNS resolution blocked | B |
| Scale | ≥3 healthy API endpoints | kill one pod, rollback, HPA unknown | B |
| CI | lint/test/build/manifest/fixture gate | bad code, failing gate, bad manifest | B |

### Test command convention

```bash
make test
make lint
python eval/run_eval.py --api http://<ingress-host> --golden eval/golden.yaml
python eval/run_eval.py --api http://<fixture-host> --golden eval/fixtures/golden.fixture.yaml
python scripts/check_submission.py
```

The example host placeholders must be replaced with actual reachable addresses. Track test result, sample size, corpus hash, index generation, embedding model and commit SHA together to keep score comparisons valid. Snapshot real output in `docs/evidence/` after generating it; don't commit fake JSON merely to satisfy a path.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-20-test-strategy-md"></a>

## Verification strategy and quality gates


### Test pyramid
- **Unit / stub (fast):** API schema/validation, abstention floor, citation whitelist, structured model retry, cache eligibility, version filtering, OCR and chunks, eval formulas. No external model or network; use starter StubRetriever/StubProvider plus fake adapter errors.
- **Component (local/minikube):** indexer run against Chroma 1.0.12, Redis cache, OCR system dependency, query embedder and shared pin. Use temporary collection names to avoid overwriting production.
- **Integration (minikube):** one-shot Job, 3 API replicas, read-only UI, Ingress route, health/readiness, HPA, Calico policies and persistent PVCs.
- **End-to-end (CI and real corpus):** fixture documents indexed in ephemeral cluster + 6 fixture golden; full corpus indexed locally + >=15 actual golden, gate + manual grounding review.

### Coverage and commands
Run from root after `make install`: `make test`, `make lint`; for API coverage `cd api && ../.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=60` (pytest-cov dependency must be available). Add similar indexer coverage if desired. CI must use Python 3.12 and stubbed LLM. Document skipped tests and why. **A test suite that exists but was never run is not evidence.**

### Metric boundaries
`recall@5 >= baseline-0.05` (strictly more than five percentage points drop fails), citations validity >=0.95, must-abstain 1.0. Include threshold-boundary unit tests and ensure empty citation sets are not misinterpreted as automatically valid. Test both real corpus and CI fixture scenario with appropriate separate baselines (a 6-question fixture score cannot truthfully replace 15-question real corpus score).

### Fault-injection and cluster tests
Four of A-F stages documented and restored; pod delete while ingress queries; Chroma down vs probes; API-only embed pin change; HPA scale; rolling image update/rollback; UI blocked from Chroma with Calico; Redis outage; reindex invalidates cache. Capture observed command, exit, timestamp and repair. See `TESTING-EVALUATION.md`.

### Review criteria
For each test check: clear expected failure/success; controlled fixture, no live private data; reproducible steps; actual results; rubric row link; failure visible in CI when injected; no tests that simply assert on the exact non-deterministic wording of the model.

---

<a id="merged-docs-specs-evaluation-md"></a>

## Implementation spec — Evaluation


**Owner:** A. **WBS:** T07,T15,T22. **Primary paths:** `eval/golden.yaml; eval/run_eval.py; eval/{baseline,results}.json`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Golden before tuning
Minimum 15: 8 ordinary, 2 version-sensitive with genuinely different policy answers, 2 exact-term codes/clauses/thresholds, 2 must-abstain absent-topic, 1 prompt injection. Label **actual** `(source,section)` from the corpus without using retriever rankings. Keep `eval/fixtures/golden.fixture.yaml` separate (6 fictional questions for fast CI).

### Metrics definition
For each non-empty relevant set: `recall@k = |relevant (source,section) pairs found in top-k| / |all relevant pairs|`. Aggregate over answerable questions with non-empty labels, report recall@3 and recall@5 overall and by question type, using an unambiguous macro-average. For must-abstain, recall undefined: exclude from recall denominator. Citation validity = number of cited `(source,section,page)` matching that request's retrieved entries / total citations, with empty-citation denominator handled explicitly; do **not** score no-citation as guaranteed 100%. Abstention correctness = fraction must_abstain questions with `answered_from_context=false` (must equal 1.0). Also manually assess answer factuality/relevance/unsupported clauses.

### Gate
`eval/run_eval.py` already reads golden, calls live `/api/ask`, writes JSON, exits 0/1. Implement `recall_at_k`, `citation_validity`, `summarise`, `gate`. Fail if `recall@5 < baseline_recall5 - 0.05`; fail if abstention<1.0; fail if citation validity<0.95; fail on malformed outputs or absent baseline according to policy. `baseline.json` is the verified prior production value, not fabricated sample. Only update baseline on approved improvement with documented reason.

### CI fixture e2e
CI must create kind/k3d (or other permitted ephemeral cluster), deploy tiny fixture corpus with **actual** indexer pipeline, use deterministic fixture embedding shared by API/indexer (or a pinned reachable local model), wait for ready API/UI, run evaluator, enforce failure exit. A stub retriever returning static passages for every question is **not** an honest end-to-end retrieval test. Capture green and deliberately failing PR checks.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

<a id="merged-docs-specs-test-matrix-md"></a>

## Implementation spec — Test Matrix


**Owner:** Both. **WBS:** T11-T24. **Primary paths:** `api/tests/*; indexer/tests/*; eval/tests/*; docs/evidence/*`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Unit checks
Input 2/3/500/501 char; no retriever hit; score=0.0/negative; current/old policy version; wrong metadata; wrong pinned embed model; scanned and table extraction; clean headings preserved; overlap and stable IDs; provider malformed JSON/timeout/false source; follow-up excluded cache; invalidation; fixture-only embedding deterministic; eval recall and citation denominators; gate boundary exactly baseline-0.05 and 94.99% citation validity.

### Integration checks
Dockerfiles build; Chroma writes one index and persists after pod deletion; Redis persists and redis availability blocks ready; actual API reads current collection not dummy; Ingress `/api/ask` and `/`; 3 API endpoints; readiness vs liveness under dependency timeout; payload with poisoned chunk; reindex version diff and stale cache; model mismatch -> 0/1 READY; UI pod cannot reach Chroma; HPA no `<unknown>`; image rollback.

### E2E and evidence
Golden >=15 across required types; fixture 6 in CI; live eval writes baseline/results; quality gate intentionally fails and is repaired; resource requests/limits and `kubectl top` peak; four stage failures; GitHub branch protection/CD SHA images; clean clone make check. Each test row needs execution ID, output and reviewer, not just test code existence.

### Coverage
`pytest --cov=app --cov-report=term-missing --cov-fail-under=60` (adjust invocation to the actual virtual environment and package root). The starter's 11 smoke tests do not prove the full app; count only real coverage after new code is merged.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

