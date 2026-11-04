# Traceability: case study → code → test → evidence

The assignment PDF (*Assignment 02, RAHBAR: Grounded RAG on Kubernetes*) is the single
source of truth. Every row is one requirement from it, by section. **Test** names a test
that fails if the requirement breaks. **Evidence** is a file produced by running the
system, not by writing about it. The planning documents (`docs/PRD.md` R01–R30,
`docs/PHASES.md`, `docs/CRITICAL-PATH.md`) map onto these rows; `docs/PRD.md` carries the
final status of each of its requirements.

Test locations: `api/tests/`, `indexer/tests/`, `eval/tests/`, `tests/` (architecture and
manifests, run on every CI build), and `tests/system/` (live cluster, `make system-test`).

## 2 · Corpus

| Requirement | Code / config | Test | Evidence |
| --- | --- | --- | --- |
| ≥ 6 documents, ≥ 40 pages, public | `corpus/sources.yaml`, `corpus/MANIFEST.md` | `scripts/check_submission.py` (B) | `docs/evidence/corpus-pdffonts-and-pages.txt` (9 docs, 279 pages, 9/9 SHA match) |
| Two versions of one policy | `sources.yaml` `superseded: true` on the 2023 rules | `api/tests/test_retrieval.py::test_superseded_chunks_only_come_back_when_asked_for` | `docs/CORPUS.md` version table; golden v01–v03 |
| Scanned PDF, OCR | `indexer/pipeline/extract.py` (`_usable`, `ocr_page`) | `indexer/tests/test_extract.py::test_scanned_page_is_routed_to_ocr`, `::test_real_ocr_reads_a_scan` (runs in CI) | `pdffonts` output; Job log `ocr_pages` |
| Table with real information | `extract.py` `render_table`, HTML table rows | `test_extract.py::test_html_headings_tables_and_noise`, `::test_render_table_merges_wrapped_cells_and_skips_blanks` | `docs/PIPELINE.md` table before/after |
| Long definitions | `indexer/pipeline/chunk.py` sentence splitting | `indexer/tests/test_chunk.py::test_a_long_definition_is_split_on_sentences_not_mid_sentence` | GenAI policy chunks |
| Deliberately absent topic | hostel PDF excluded in `sources.yaml` | `eval/golden.yaml` a01–a03; `tests/system/...::test_the_absent_topic_is_declined` | `eval/results.json` abstention |
| Exact-term content | clause numbers kept by `clean.py`; `$contains` assist in `api/app/retrieval/chroma.py` | `test_clean.py::test_tables_fees_and_clause_numbers_survive`, `api/tests/test_retrieval.py::test_exact_terms_are_pulled_to_the_front` | recall by type in `eval/results.json` |
| Fetch politely, SHA-256 manifest, no PDFs in Git | `corpus/fetch.py`; `.gitignore` `corpus/raw/` | Job init container fails closed on a changed manifest | `fetch.py --verify` output |

## 3 · Application

| Requirement | Code / config | Test | Evidence |
| --- | --- | --- | --- |
| 3.1 Extract (OCR, headers/footers) | `extract.py`, `clean.py` | `test_extract.py`, `test_clean.py` (18 tests) | `docs/PIPELINE.md` Extraction |
| 3.1 Clean (rules, one thing kept) | `clean.py` docstring rules | `test_clean.py::test_running_header_and_alternating_folio_are_removed` | `docs/PIPELINE.md` Cleaning |
| 3.1 Structure-aware chunk with overlap | `chunk.py` | `test_chunk.py` (25 tests) | amplification in Job log |
| 3.1 Embed with the pinned model | `indexer/pipeline/embed.py` | `test_embed.py` | Job log `dimension: 768` |
| 3.1 Store id/text/vector/metadata | `indexer/pipeline/store.py` | `test_store.py` | collection metadata via `/readyz` |
| 3.1 Metadata source/section/page/doc_version/superseded | `indexer/pipeline/models.py::Chunk.metadata` | `test_chunk.py::test_chunks_respect_size_and_carry_metadata` | |
| 3.1 Three (size, overlap) settings measured | `scripts/chunk-sweep.sh` | | `docs/evidence/chunking/`, `docs/PIPELINE.md` table |
| 3.2 Validate 3–500 chars | `api/app/schemas.py::AskRequest` | `api/tests/test_starter.py::test_question_length_is_enforced` | |
| 3.2 Cache check, skip follow-ups | `api/app/services/answer.py`, `guard.py::is_follow_up` | `test_answer.py::test_unsafe_answers_are_not_cached`, `test_guard.py::test_follow_up_detection` | |
| 3.2 Same embedding model | `api/app/retrieval/embedder.py::prepare_query` | `tests/test_boundaries.py::test_both_sides_prepare_text_identically_for_the_pinned_model` | |
| 3.2 top-k from ConfigMap, superseded filter | `chroma.py::retrieve` | `test_retrieval.py::test_superseded_chunks_only_come_back_when_asked_for` | |
| 3.2 Augment: instructions, numbered evidence, question | `api/app/services/prompt.py` | `test_prompt.py::test_order_is_instructions_evidence_question` | |
| 3.2 Generate schema-constrained, low temperature | `providers/llm/ollama.py` (`format`), ConfigMap `TEMPERATURE` | `test_providers.py::test_ollama_sends_schema_temperature_and_messages` | |
| 3.2 Validate, retry once, fall back | `answer.py::generate_checked` | `test_answer.py::test_two_failures_give_a_safe_canned_answer_not_a_500` | |
| 3.2 Store turn, cache if safe | `answer.py::_log_turn`, cache `store` | `test_answer.py::test_one_log_line_per_turn_with_ids_scores_and_no_text` | |
| 3.3 Redis/second collection + ADR | `api/app/services/cache.py`; `k8s/base/redis.yaml` | `test_cache.py` | `docs/adr/0003-semantic-cache-store.md` |
| 3.3 Threshold from ConfigMap, chosen with data | `CACHE_THRESHOLD` | | `docs/evidence/cache-threshold.txt` (0.95; 0.92 ruled out by Rector's vs Dean's List) |
| 3.3 Never cache follow-ups/abstentions/failures | `answer.py` `cacheable` | `test_answer.py::test_unsafe_answers_are_not_cached`, `::test_fallbacks_are_not_cached` | |
| 3.3 Invalidate on re-index | generation-scoped keys, `cache.observe` | `test_answer.py::test_reindex_expires_the_cache` | |
| 3.4 One Pydantic model as contract and validator | `schemas.py::Answer` sent as `format`, validated with `model_validate_json` | `test_providers.py::test_ollama_prose_instead_of_json_is_a_validation_error` | |
| 3.4 Abstain below the relevance floor | `answer.py` floor | `test_answer.py::test_below_the_relevance_floor_abstains_without_calling_the_model` | floor 0.60 measured in `docs/PIPELINE.md` |
| 3.4 Cite only what was retrieved | `api/app/services/guard.py::check_answer` | `test_guard.py::test_fabricated_citations_are_rejected` | citation validity in `eval/results.json` |
| 3.4 Retrieved text is data; poisoned-chunk test | `prompt.py` (delimiters, `neutralise`) | `api/tests/test_injection.py` (3 tests incl. live model) | `docs/FAILURE-ANALYSIS.md` |
| 3.4 Temperature 0–0.3 with a reason | ConfigMap `TEMPERATURE: "0.2"` + comment | `tests/test_manifests.py::test_configmap_carries_every_tunable_and_the_pin` | |
| 3.5 Provider behind an interface, one-file swap | `providers/llm/{base,ollama,hosted,stub}.py` | `test_providers.py::test_provider_selection_is_one_config_key` | `docs/adr/0004-...md` |

## 4 · Kubernetes

| Requirement | Manifest | Test | Evidence |
| --- | --- | --- | --- |
| Namespace `rahbar`, never default | `k8s/base/namespace.yaml`, `kustomization.yaml namespace:` | `tests/test_manifests.py::test_nothing_lands_in_the_default_namespace` | `kubectl get all -n rahbar` |
| api: 3 replicas, 3 probes, requests/limits, maxUnavailable 0 | `k8s/base/api.yaml` | `::test_api_has_three_replicas_three_probes_and_zero_unavailable` | `docs/evidence/rollout-and-endpoints.txt` |
| ui: nginx | `k8s/base/ui.yaml`, `ui/Dockerfile` | `::test_every_container_is_hardened` | |
| chroma StatefulSet + volumeClaimTemplates | `k8s/base/chroma-statefulset.yaml` | `::test_chroma_is_a_statefulset_with_a_claim_template` | `docs/ARCHITECTURE.md` (the reason) |
| redis Deployment + PVC | `k8s/base/redis.yaml` | `::test_redis_persists_to_its_claim` | |
| Job: OnFailure, backoffLimit | `k8s/base/indexer-job.yaml` | `::test_indexer_job_and_cronjob_share_image_and_args` | `docs/evidence/indexer-job.txt` |
| CronJob weekly, same image and args | `k8s/base/reindex-cronjob.yaml` | same test | |
| 4 Services, all ClusterIP | `k8s/base/services.yaml` | `::test_data_tier_services_are_cluster_internal` | |
| Ingress `/` ui, `/api` api, one host | `k8s/base/ingress.yaml` | `::test_ingress_routes_api_and_ui_on_one_host` | `tests/system/...::test_ingress_serves_the_ui_and_the_api` |
| ConfigMap keys | `k8s/base/configmap.yaml` | `::test_configmap_carries_every_tunable_and_the_pin` | |
| Secret gitignored, placeholder only | `.gitignore`, `k8s/base/secret.placeholder.yaml` | `::test_the_secret_placeholder_is_never_applied` | checker section A |
| NetworkPolicy deny-by-default + allowed paths | `k8s/base/networkpolicy.yaml` | `::test_network_is_deny_by_default`, `::test_network_graph_matches_the_architecture` | `docs/evidence/networkpolicy-tests.txt` |
| HPA 3..8 on api | `k8s/base/hpa.yaml` | `::test_hpa_scales_api_from_three_to_eight` | `docs/evidence/hpa.txt` |
| 4.2 Indexer is a Job; ADR 0001 | `indexer-job.yaml`; `docs/adr/0001-indexer-as-job.md` | `tests/test_boundaries.py::test_the_api_never_writes_to_chroma`, `::test_api_startup_does_no_indexing` | |
| 4.3 /healthz touches nothing; /readyz checks deps | `api/app/routes/health.py` | `api/tests/test_health.py` | |
| 4.4 Pin in collection metadata, API refuses readiness | `store.py` metadata; `chroma.py::pin_problem`; `health.py` | `test_health.py::test_not_ready_names_the_dependency[...embedding_pin]`, `tests/system/...::test_changing_the_embedding_model...` | `docs/evidence/pin-mismatch.txt` |
| 4.5 Requests and limits everywhere, from `kubectl top` | all workloads | `::test_every_container_has_requests_and_limits` | `docs/evidence/kubectl-top*.txt` |
| 4.6 maxSurge 1/maxUnavailable 0, grace + preStop | `api.yaml` | `::test_api_has_three_replicas_...` | `docs/evidence/rollout-and-endpoints.txt` (set image, undo) |
| 4.6 Scale ≥ 3, endpoints list that many | | `tests/system/...::test_three_api_endpoints_behind_the_service` | `docs/evidence/rollout-and-endpoints.txt` |
| 4.7 ServiceAccount per workload, no token | `serviceaccounts.yaml` | `::test_dedicated_service_accounts_without_tokens` | |
| 4.7 Non-root, read-only root, caps dropped | all workloads; Dockerfiles `USER` | `::test_every_container_is_hardened` | |
| 4.7 ui cannot reach chroma | `networkpolicy.yaml` | `tests/system/...::test_network_policy_blocks_ui_to_chroma_and_allows_api_to_chroma` | `docs/evidence/networkpolicy-tests.txt` |
| 4.7 Unsafe output never eval'd | | `tests/test_boundaries.py::test_no_eval_or_exec_on_model_or_document_text` | |
| 4.8 JSON logs to stdout, request_id | `api/app/logjson.py`, `main.py` middleware | `test_starter.py::test_request_id_is_echoed` | |
| 4.8 /metrics with the required series | `api/app/routes/metrics.py` | `api/tests/test_app.py::test_rag_metrics_are_exposed` | `docs/evidence/metrics.txt` |
| 4.8 One line per request: top_k, ids, scores, abstention | `answer.py::_log_turn` | `test_answer.py::test_one_log_line_per_turn_with_ids_scores_and_no_text` | `docs/evidence/api-request-log.txt` |

## 5 · Evaluation

| Requirement | Code | Test | Evidence |
| --- | --- | --- | --- |
| ≥ 15 golden questions in the required mix, written before tuning | `eval/golden.yaml` (19) | `eval/tests/test_run_eval.py::test_golden_sets_have_the_required_mix` | git history: golden committed before the chunk sweep |
| recall@3 and @5, overall and by type | `eval/run_eval.py::recall_at_k`, `summarise` | `test_run_eval.py::test_recall_*`, `::test_summarise_pools_citations_and_breaks_down_by_type` | `eval/results.json` |
| Citation validity (%), abstention correctness (100%) | `citation_validity`, `summarise` | `::test_citation_validity_checks_source_section_and_page` | `eval/results.json` |
| CI gate: recall@5 drop > 5 pts, abstain, citations < 95% | `gate` | `::test_gate_boundary_is_exactly_five_points`, `::test_gate_failures_name_the_problem` | `.github/workflows/ci.yml` e2e-eval; the failing-gate PR |
| `eval/baseline.json`, `eval/results.json` committed | | | both files |
| 5.5 Break four stages, diagnose | `OCR_ENABLED`, `CHUNK_*`, `TOP_K`, `SUPERSEDED_FILTER`, `TEMPERATURE` | | `docs/FAILURE-ANALYSIS.md`, `docs/evidence/failures/` |

## 6 · DevOps

| Requirement | Where | Evidence |
| --- | --- | --- |
| `dev` for work, `main` protected (PR, CI, one approval) | branch settings | all work on `dev`, nothing pushed to `main`; **enabling protection needs repo-admin (owner step)** |
| ci.yml: lint, test (≥ 60%), manifests, build (no push), scan, e2e-eval | `.github/workflows/ci.yml` | Actions run URLs in `docs/evidence/ci-runs.txt` |
| cd.yml: test → build-push (SHA) → deploy (rollout, Ingress smoke) | `.github/workflows/cd.yml`, `scripts/smoke.py` | successful cd run URL |
| `needs:` on publishing/deploying jobs | `cd.yml` `build-push: needs: test`, `deploy: needs: build-push` | `scripts/check_submission.py` (I) |
| Deploy by SHA, never `:latest` | `kustomize edit set image ...:$GITHUB_SHA` | `tests/test_manifests.py::test_images_are_pinned_and_never_latest` |
| Credentials from GitHub Secrets, least-privilege `permissions:` | both workflows | |
| Gate shown failing then green | the gate demonstration PR | `docs/evidence/gate-demo.txt` |

## 7–8 · Notes, rules, submission

| Requirement | Where |
| --- | --- |
| Seven engineering questions with file:line references | `docs/ENGINEERING-NOTES.md` |
| No secret in Git history | `.gitignore`; `scripts/check_submission.py` section A |
| AI usage disclosed | `docs/AI-USAGE.md` |
| Checker clean | `docs/evidence/check-submission.txt` |
