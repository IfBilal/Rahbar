> **Status (5 November 2026):** answered in `docs/ENGINEERING-NOTES.md` with file:line references and measurements. This guide is kept as the plan of record.

> **Required output file:** Implement the material in this *supplementary planning guide* and record the final, evidence-backed results in the instructor-provided `docs/ENGINEERING-NOTES.md`. That original file is not included in this archive.

# Seven engineering questions — final answers require your own evidence

The instructor explicitly requires all seven answers to reference **your implemented code/manifests and actual line numbers**, plus observed logs/metrics. This file contains guidance and blanks, **not completed answers**. Neither developer nor agent may invent `kubectl top` readings, timing, benchmark rows or an alleged hour-long incident.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-engineering-notes-md"></a>

## Seven engineering notes — working answers, must be completed from actual implementation


**These are drafting guides, NOT final assessed answers.** The instructor requires each answer to point to **actual files and line numbers of your own completed implementation**; a generic answer scores zero. Replace every `MEASURE`/`LINE` after code merges, and cite specific observed metrics/logs.

### 1. Why can't the three API replicas index at startup?
Concurrent writers could rebuild the same live collection inconsistently; every restart would redo OCR/embedding and readiness could flip while serving empty results. Our protective object must be a dedicated Kubernetes `Job`/`CronJob`, while API `main.py` constructs only reader dependencies. Link final lines: `k8s/base/indexer-job.yaml:LINE`, `api/app/main.py:LINE` and prove Job completion; don't cite planned files that don't exist.

### 2. What happens if Chroma-dependent readiness and liveness are swapped for a 90-second slowdown?
A dependency-bound liveness probe could restart all three API pods repeatedly (restart storm) instead of removing unready endpoints temporarily. Correct `/healthz` answers based on process state only; `/readyz` validates Chroma/Redis/index/pin and returns 503. Cite `api/app/routes/health.py:LINE`, probe YAML lines and observed cluster fault test output `MEASURE`.

### 3. What is CPU HPA measuring while model generation waits?
It measures API pod **CPU usage relative to requested CPU**, not queued questions, generation work or model saturation. Network-bound waits may show low CPU even when latency and concurrency are high. A generation service would better scale from in-flight requests/queue depth or latency-derived custom/external Prometheus metrics via an adapter/KEDA (requires extra instrumentation/config). Cite HPA manifest `LINE`, `kubectl get hpa` `MEASURE`, metrics names, and justify not implementing a bonus scaler if out of scope.

### 4. What was indexer's peak memory, resource limit/margin and wrong-limit exit code?
Write actual `kubectl top pods -n rahbar` peak observed **MEASURE MiB**, indexer manifest memory limit **MEASURE MiB**, margin = limit − observed peak (**calculate**), workload context/document count **MEASURE**, exact YAML path:LINE. If memory is exceeded the process is typically OOMKilled, **exit code 137**. The number cannot be invented from the starter.

### 5. Where was recall@5 worst by question type, and why?
Fill measured by-type table: `ordinary MEASURE`, `version MEASURE`, `exact MEASURE`, `injection MEASURE`; discuss actual weakest type. Exact strings/codes/clauses can blur in dense embeddings; a measured lexical/hybrid retrieval technique may help, but don't assert it was your worst group without scores. Cite code `api/app/retrieval/chroma.py:LINE` and actual eval JSON key.

### 6. What happens on API-only EMBED_MODEL change?
Indexer metadata persists model name and observed vector dimension; API compares its ConfigMap pin against **active** collection metadata and returns 503 `/readyz`, becomes 0/1 READY, logs both values. Without this guard it could compare incompatible vectors and silently return nonsense. Cite `indexer/pipeline/store.py:LINE`, `api/app/routes/health.py:LINE`, and actual mismatch pod logs `MEASURE`.

### 7. Describe a real >1 hour failure
**Do not fabricate an incident.** Fill: date, duration, triggering task, exact error and symptoms, first mistaken hypothesis, smallest command/log/metric that revealed actual cause, fix and test, prevention. Include real `kubectl describe pod` Events/`kubectl logs --previous`/CI job URL and own code/manifests line references. If none cost >1h, report honestly and ask instructor how to address this requirement instead of inventing a story.

### Completion checklist
Seven questions answered with own line numbers and at least one actual command/output each where applicable; no `LINE`/`MEASURE`; second developer reviews narrative versus observed evidence. Keep evidence paths in `docs/evidence/` and ref values up to date after last commit.

---

