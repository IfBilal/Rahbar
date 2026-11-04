> **Status (5 November 2026):** the tested runbook is `README.md` (clean clone → answered question) with `docs/evidence/clean-clone.log`. This guide is kept as the plan of record.

# Cluster bootstrap, rollouts, re-indexing and recovery

This document is an **operator runbook**; commands are planning examples until executed on the target machine. The starter's Makefile and `STARTER.md` supersede guesses about available targets. Local development should work with stubs before real RAG, with Chroma PVC persistence and no API-startup writes. Reserve separate time to collect real command output for submission.

**Diagnostic order:** `kubectl get pods -n rahbar` → `kubectl describe pod ... -n rahbar` (Events) → `kubectl logs ... -n rahbar` (`--previous` for crashes). A 0/1 READY API usually points to empty/incompatible collection, Redis, or probe wiring. A `ImagePullBackOff` after a local build often needs `minikube image load` + `IfNotPresent`; an unknown HPA CPU percentage needs resource requests and metrics-server.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-21-deployment-runbook-md"></a>

## Deployment runbook — clean minikube


**Planned commands; runbook must be verified after manifests are built.** Use bash/Linux or WSL2, Docker, minikube, kubectl, make, Python 3.12; recommended 6GB RAM for minikube while Ollama runs on host (assignment notes 4GB minimal, 8GB for in-cluster model). API/UI/indexer Dockerfiles and manifests do not yet exist in the starter.

### 1. Cluster prerequisites
```bash
make cluster  # minikube --driver=docker --cni=calico --memory=6144 --cpus=4
kubectl get nodes
minikube addons enable metrics-server
minikube addons enable ingress
```
Confirm Calico actually enforces NetworkPolicy; minikube default CNI may silently ignore it.

### 2. Host model (selected default)
```bash
# Separate terminal on laptop (host, not in minikube):
OLLAMA_HOST=0.0.0.0 ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```
Check `host.minikube.internal:11434` from an allowed API/indexer pod; allow host IP/CIDR in network policy. If hosted provider selected, configure from Kubernetes Secret only, not committed values.

### 3. Corpus and images
```bash
cp corpus/sources.example.yaml corpus/sources.yaml  # verify file rather than blindly using all URLs
make install
make fetch
python corpus/fetch.py --verify
make images TAG=dev
```
Confirm real PDFs are accessible to the Job: define explicit init fetch or mount method; localhost `corpus/raw/` is **not** magically visible in the container. Never commit external PDF files. For dummy G2 development choose ConfigMap `EMBED_MODEL=dummy-768`, `RETRIEVER=stub`, `LLM_PROVIDER=stub`; real environment later selects `nomic-embed-text`, `RETRIEVER=chroma`, `LLM_PROVIDER=ollama-host`.

### 4. K8s apply order
Prefer `kubectl apply -k k8s/overlays/dev` once all manifests are complete, **but wait for prerequisite stateful stores and indexer Job before expecting API readiness**. For deterministic clean clone steps: namespace + ConfigMap -> storage PVC/StatefulSet/Redis and services -> security/ingress/hpa -> Job/CronJob -> API/UI -> wait for readiness. If using kustomize single-pass, readiness intentionally remains false until index exists.
```bash
make apply
kubectl get ns rahbar
kubectl get pods,svc,sts,deploy,pvc,job,cronjob,ingress,hpa -n rahbar
kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc --all -n rahbar --timeout=180s  # adjust if unsupported
```
For hosted mode create Secret **only after namespace exists**:
```bash
export LLM_API_KEY='...set locally, never put in README/manifest...'
make secret
```
No real secret value in code or docs.

### 5. Index once
```bash
make index  # creates Job from cronjob/reindex, once CronJob exists
kubectl get jobs -n rahbar -w
kubectl logs job/<actual-job-name> -n rahbar
```
Require `Complete` and nonempty Chroma collection. Dummy Job can exercise infra; real Job must ingest verified sources and store vectors and metadata. Avoid running two indexing jobs concurrently. After first real index, configure real model and ensure API pin agrees, otherwise `/readyz` must fail.

### 6. Test ingress/replicas
```bash
kubectl rollout status deployment/api -n rahbar
kubectl get endpoints api -n rahbar -o wide
make ask Q='What does the academic warning policy say?'
```
If Linux, `INGRESS_IP=$(minikube ip)`; macOS/Windows Docker driver: use `minikube tunnel` and `INGRESS_IP=127.0.0.1` if needed. Requests to host-based ingress must use header `Host: rahbar.local`.

### 7. Reindex, rollback and smoke
`kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` (unique name each run); verify new active index generation, stale cache not reused, no API deployment restart. Roll image with a tested SHA then `kubectl rollout status deployment/api -n rahbar`; `kubectl rollout undo deployment/api -n rahbar` and verify previous image/response. Do not imply these were run until evidence exists.

### 8. Evidence and cleanup
Run `make check`, the live eval runner and secure smoke tests. Collect `kubectl top`, HPA, API endpoints and model mismatch logs. Names and commands must be reconciled against actual YAML, not guessed. For failures see `DEPLOYMENT-RUNBOOK.md` and section 9 of assignment.

---

<a id="merged-docs-22-operations-and-recovery-md"></a>

## Operations, failure recovery and lifecycle


### Default diagnostic order
`kubectl get pods -n rahbar`, then `kubectl describe pod <pod> -n rahbar` (Events last), then `kubectl logs <pod> -n rahbar` with `--previous` if restarting; finally check service endpoints, ConfigMap, policy, PVC and dependent services. Record command and time.

### Failure playbooks
| Symptom | Likely diagnosis | Safe recovery | What not to do |
|---|---|---|---|
| API `Running 0/1 READY` | empty index, Chroma/Redis down, wrong model pin | inspect `/readyz`, collection metadata, logs, fix root and retest | remove readiness probe |
| CrashLoopBackOff `exit 137` | indexer OOM | use `kubectl top`/describe; measured batch/limit adjustment | invent CPU/memory value |
| HPA `<unknown>` | CPU request missing or metrics-server disabled | add request; enable addon and verify | claim autoscaling works |
| UI cannot resolve service | NetworkPolicy DNS blocked | allow TCP/UDP 53 to kube-dns | remove all policies for release |
| API cannot reach host Ollama | host listens on 127.0.0.1 or policy blocks | `OLLAMA_HOST=0.0.0.0`; allow host CIDR | embed with different model |
| `ImagePullBackOff` | minikube cannot see local image or bad SHA | `minikube image load` or publish exact SHA | deploy `latest` |
| Retrieval wrong version | missing superseded filter or inaccurate metadata | inspect retrieved IDs and fix metadata; rebuild index | instruct LLM to ignore old policies only |
| Stale answer after reindex | old cache generation reused | invalidate generation + cache keys, regression test | manually erase evidence of failure |
| Missing/invalid citations | provider hallucinated or guards absent | validate against retrieved, retry once, fallback | return uncited confident prose |
| Reindex aborted | source download, OCR, embedding, Chroma error | preserve old active index, inspect Job logs, rerun after repair | delete old live collection |

### Routine maintenance
Weekly CronJob with `concurrencyPolicy: Forbid`; audit source manifest/SHA and source version changes; review high/critical fixable vulnerabilities; verify PVCs and database server/client pin; rerun golden and observe by-type recall before promoting any chunk/threshold change. Limit retention of old collections to a tested rollback window; never delete only working index.

### Observability hooks
Logs to stdout JSON with request_id, top_k, chunk IDs, similarity, abstain and provider; metrics for retrieval/gen latency, cache hits and misses, fallback/abstention, token counts. Avoid including full questions, tokens, user identities or secrets in labels or logs.

---

<a id="merged-docs-29-troubleshooting-md"></a>

## Troubleshooting trees — diagnose before patching


### First three commands
```bash
kubectl get pods -n rahbar -o wide
kubectl describe pod <name> -n rahbar
kubectl logs <name> -n rahbar --previous  # only if restarted
```
The status and Events identify image, scheduling, volume, probe or OOM problems; then inspect app logs. Record exact symptom and date in evidence.

### API not ready
1. Port-forward API `/healthz` — if 200, process is alive; do not disable probes.
2. GET `/readyz` — dependency named in 503: Redis ping, Chroma heartbeat/collection count, pin metadata.
3. Check actual `EMBED_MODEL` from ConfigMap and collection metadata, plus dimension; don't re-embed queries with an incompatible model.
4. Check Chroma StatefulSet PVC Bound and server/client both version 1.0.12; verify index Job actually ran and published.
5. If Redis unavailable check PVC, TCP 6379/NetworkPolicy, AOF and service endpoints.

### Ingress returns 404/502
Check enabled addon, ingress class, `rahbar.local` Host header, `/api` path sent to API unchanged, UI nginx 8080, Services targetPort, API endpoints. On macOS/Windows Docker driver, use `minikube tunnel`. A bad ingress does not justify changing `POST /api/ask` URL contract.

### Indexer fails
Check Job pod Events, logs, `CORPUS_DIR` mount/fetch success, `_index.json`, OCR system tools, Ollama host route, Chroma count, memory limit (exit 137), batched embeddings and vector shape. A Job that writes three dummy chunks does not prove real corpus indexing. Avoid editing API to conceal missing index.

### Policy fails
If all DNS breaks after default deny, explicitly allow UDP+TCP 53 to kube-dns. If UI can reach Chroma, check minikube started with Calico, selectors/namespace and policy tests. If indexer cannot fetch sources, allow limited egress to verified public endpoints or stage corpus with mounted volume; don't broadly allow all egress without ADR and tests.

### Quality drops
Look in stage order: extraction (OCR missing), cleaning/chunk (headings lost), embed pin/dim, retrieval top-k/superseded filter, prompt, generation. Check retrieved IDs/scores before blaming model. Re-run baseline from same golden and don't silently update score thresholds.

---

