# Security threat model, network graph, logs and metrics

Assignment security closures: **(1)** never commit secrets, **(2)** distinct ServiceAccounts and disable token automount when unnecessary, **(3)** non-root read-only containers with dropped capabilities, **(4)** default-deny and explicit required network flows including DNS and Ollama host egress, **(5)** treat retrieved documents and LLM outputs as untrusted. Restrict Chroma to API/indexer and Redis to API; UI must not reach Chroma.

**Metrics and evidence:** JSON stdout per request with request ID; expose request count/latency, retrieval and generation latency, cache-hit ratio, abstentions, fallbacks and token counts. Record top-k IDs and scores, never whole sensitive documents or credentials. Log/metric samples are evidence only after observing a running build.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-23-security-threat-model-md"></a>

## Threat model and concrete mitigations


### Assets and trust boundaries
Assets: user question, public document text, Chroma vectors/metadata, Redis cached answers, LLM credentials, registry token and cluster config. Boundaries: internet -> Ingress/UI/API; API -> Chroma/Redis/Ollama; indexer -> external public corpus + Chroma; CI -> image registry; operator -> Kubernetes API. Threat model assumes documents/questions are untrusted and may contain commands that a generative model might follow.

### Threat table
| Threat | Impact | Mitigation | Proof |
|---|---|---|---|
| Poisoned paragraph tells model to ignore rules | fabricated answer | evidence delimiters, system policy, schema, citation validation, injection golden | indexed poisoned fixture + test |
| Model cites nonexistent clause | academic misinformation | exact citation whitelist against retrieved `(source,section,page)`, fallback | unit/CI validation |
| Old policy indexed as current | stale answer | signed/verified source version metadata + superseded filter | 2 version golden cases |
| Git-tracked API key | credential compromise / rubric deduction | secret via CLI, `.gitignore`, scanning, rotate leaked keys | Git history + GitHub Secrets review |
| Chroma or Redis public endpoint | data leak/write abuse | ClusterIP services only, default-deny NetworkPolicy | service YAML + connectivity test |
| Root container can write node FS | escalation | runAsNonRoot, readOnlyRootFilesystem, capabilities drop, no escalation | manifest/exec inspect |
| Kubernetes workload token unnecessary | API access abuse | ServiceAccounts per workload, automount=false where unused | manifest audit |
| Cache cross-index answer reuse | false trusted answer | generation namespace + negative-pair threshold + invalidation | rerun after reindex |
| Malicious / malformed PDF | extraction crash/resource exhaustion | bounds, timeouts, subprocess OCR isolation, recoverable error logging | corrupt PDF test |

### Secrets
Never store real credentials in files or YAML. In hosted mode create `rahbar-secret` with `kubectl` after namespace exists and reference through `envFrom`/`secretKeyRef`. A placeholder secret file is never included in kustomization. Git history leak requires key rotation and two-line incident note.

### NetworkPolicy implementation nuance
Rubric explicitly asks Redis accessible **only from API**; cache invalidation therefore occurs when API discovers a new index generation, not by letting indexer contact Redis. Indexer writes Chroma control metadata, API reads Chroma and evicts Redis keys. Verify that exact graph in actual Calico cluster.

### Human-review release gate
Check `git log`/history and secrets scan, container user/volume constraints, network denial, citation injection tests, provider requests, immutable tags and minimal workflow permissions. Do not assert compliance only from presence of YAML labels.

---

<a id="merged-docs-24-observability-md"></a>

## Logging, metrics and runtime diagnostics


### What is already given
`api/app/logjson.py` provides JSON logging + request-id context. `api/app/main.py` middleware tags requests, echoes `X-Request-ID`; `api/app/routes/metrics.py` exposes request counters and latency histogram. They do **not** yet provide all assignment RAG metrics.

### Implement additional Prometheus series
Proposed names (consistent usage throughout code; labels remain low-cardinality):
| Name | Type | Required insight |
|---|---|---|
| `rahbar_retrieval_seconds` | Histogram | Chroma/embedding retrieval timing |
| `rahbar_generation_seconds` | Histogram | LLM network wait/generation timing |
| `rahbar_cache_hits_total` / `rahbar_cache_lookups_total` | Counter | derive cache hit ratio |
| `rahbar_abstentions_total` | Counter | out-of-knowledge declines |
| `rahbar_fallbacks_total` | Counter | malformed JSON/timeouts/guard failures |
| `rahbar_tokens_input_total` / `rahbar_tokens_output_total` | Counter | provider token consumption |
| existing request/latency metrics | Counter + Histogram | HTTP activity and latency |

### Structured request record
Per request: `request_id`, route, provider, retriever, `top_k`, retrieved `chunk_ids` and similarity scores, answer_from_context, cache state, retrieval_ms, generation_ms, fallback_reason category, token counts. **No raw question or source full-text in stdout by default**, no user identifiers, no credential string.

### Alerts / diagnostic thresholds
This assignment does not require production alert-manager deployment. Suggested operational observation: readiness unavailable, Job Failed, zero API endpoints, rising 5xx, spike in fallbacks/abstentions, high retrieval latency, cache hit ratio jumps after reindex, HPA `<unknown>`; document any chosen alert as an observation, not live alerting unless built.

### Measurements for engineering notes
Capture indexer peak memory while indexing, API CPU requests and HPA target, pin mismatch error, retrieval scores and by-type recall. Include timestamp and commit. CPU HPA may miss slow LLM service because API is I/O-bound; discuss queue depth/in-flight requests for a better custom scaler.

---

<a id="merged-docs-specs-network-security-md"></a>

## Implementation spec — Network Security


**Owner:** B. **WBS:** T16. **Primary paths:** `k8s/base/networkpolicy*.yaml; k8s/base/*serviceaccount*; Dockerfiles`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Required trust graph
Ingress controller -> UI and API; UI -> API (when needed; same-origin browser traffic generally hits Ingress); API -> Chroma, Redis, DNS, embed/LLM host; indexer -> Chroma, DNS, source download if used, embed host; **UI must not reach Chroma**, Chroma and Redis never exposed by NodePort/LoadBalancer. Default deny ingress/egress, then add minimal labels/ports. Assignment enumerates Redis **API-only ingress**: use index-generation-based API cache invalidation so the indexer does **not** need Redis access.

### Security context
Dedicated ServiceAccount for each workload, disable automount where no API server calls; no root; `readOnlyRootFilesystem=true`; no privilege escalation; capability drop ALL; minimal `/tmp`/data writable volumes. Secrets from `kubectl create secret ...`, never a real value in a committed manifest. Ensure `kustomization.yaml` excludes `secret.placeholder.yaml`.

### Verification
From UI pod, `nc -vz chroma 8000` should fail (network policy) while a permitted API request through Ingress succeeds; from API pod Chroma 8000 and Redis 6379 allowed; DNS resolves; indexer Chroma allowed but Redis denied; check actual Calico enforce. Probe connectivity also requires allowed egress. Test secret grep/history and Trivy HIGH/CRITICAL-fixable gate.

### Threats
Prompt injection from crawled documents; user injection; stale/hallucinated citation; malicious PDF parsing; secret leak; public data store; write-capable API; Kubernetes default privileges; cache poisoning. Bound each with schema, citation check, input limits, nonroot, PVC isolation and NetworkPolicy.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

