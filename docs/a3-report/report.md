# RAHBAR + RAGOps: operating a grounded RAG pipeline on Kubernetes

**CS4032 Assignment 03 (RAGOps), Fall 2026.** Team: **Taimoor Shaukat (24I-3015)** and **Muhammad Bilal Tahir (24I-3166)**.
Repository: <https://github.com/IfBilal/Rahbar> · submitted commit: `«MEASURE: git SHA»` · all numbers come from runs on one machine (a CPU-only laptop, `docs/a3-evidence/host.md`).

We added the RAGOps layer of the reference paper (Xu et al., 2026) to our Assignment-02 pipeline RAHBAR (FAST-NUCES rules, answers with citations, abstains when the documents do not cover a question). It now has a verification and incremental-update lifecycle for the data (**Batch A**: nine public documents, 279 pages; **Batch B**: thirteen fictional files with planted problems), a three-level offline test suite, a configurable release gate, traces and metrics for every query, a coverage check against live queries, and a controlled release on Kubernetes. Ingestion and evaluation are Jobs; data, traces and results are on PersistentVolumeClaims; thresholds are a ConfigMap.

## 1. Table 1: the stages of Figure 3

| Figure-3 stage | What our pipeline does | File | What is missing |
|---|---|---|---|
| Ingest | An inbox on the `ragops-data` volume; adds, changes and removals are detected against a ledger; PDF, HTML, Markdown and text extraction with OCR for scans | `indexer/pipeline/catalog.py`, `extract.py`, `run.py` | No webhook or change-data-capture; formats beyond those four |
| Verify | Four checks per document (quality, completeness, recency, uniqueness) with a reason code; failures go to quarantine; one report per run | `verify.py`, `report.py` | No consistency check across documents; malicious content is not detectable here (B08 passes all four checks) |
| Update data lake | Verified versions on the PVC, superseded versions archived and restorable, deletions recorded, a versioned ledger | `lake.py`, `ledger.py`, `ops.py` | No access-control metadata |
| Update retrieval sources | Chunk-level incremental update: 0 embeddings when nothing changed, changed document replaces only its chunks, deletion leaves no orphans, `superseded` flag in metadata, revision in a registry | `incremental.py`, `store.py`, `index.py` | A change of embedding model or chunking is a full rebuild of a new collection |
| Offline testing | Golden set (30) and a three-level suite (module, component, end-to-end), seeds, run twice, one command; gate over ConfigMap thresholds | `ragops/suite/`, `ragops/gate/` | Public benchmarks; a larger golden set; a stronger judge than the 3B generator |
| Live testing | A candidate Deployment on its own collection, the same suite against it, a gated rolling release with `kubectl rollout undo`; traces and a summary over a time window | `k8s/candidate.yaml`, `scripts/ragops/release.sh`, `ragops/trace/` | No A/B traffic split; no alerting |
| Check coverage | Embedding similarity between live queries and golden questions; share against a calibrated threshold; uncovered topics; exit code | `ragops/coverage/coverage.py` | Retrieval-level and generation-level coverage |

## 2. Table 2: the five qualities

«MEASURE: filled from the measured runs: what is measured, the threshold from gate.yaml / coverage.yaml, and the evidence file»

## 3. Results

«MEASURE»

## 4. Short answers

«MEASURE»

## 5. Contribution and AI statement

«MEASURE»

<div class="appendix"></div>

## Appendix: screenshots

«MEASURE»
