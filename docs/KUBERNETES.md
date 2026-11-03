# Kubernetes deployment object contracts and cluster behavior

**Required namespace:** `rahbar`, never `default`. Required workload topology: API Deployment **3** replicas, UI Deployment ≥1, Chroma StatefulSet with `volumeClaimTemplates`, Redis Deployment and PVC, one-shot indexer Job, weekly reindex CronJob, four internal Services, same-host `/` and `/api` Ingress, shared ConfigMap, Secret placeholder/runtime Secret, default-deny NetworkPolicy, API HPA min 3 / max 8. Each container needs resource requests and limits; API needs startup/liveness/readiness probes and rollout `maxUnavailable:0`, `maxSurge:1`.

**Hard test:** a starter dummy Job (`--dummy`) must run before the real model pipeline. In dummy mode `EMBED_MODEL=dummy-768` is the starter-compatible pin; the real model must later be set consistently in both API and indexer before the production Job. Calico is necessary to enforce NetworkPolicy on minikube.

## Agent-ready manifest-by-manifest build contract

Use the actual starter service entrypoints, not a novel application structure. Save objects under `k8s/base/` and overlays under `k8s/overlays/dev/` and `k8s/overlays/prod/`. Manifest names may vary, but every required object and its verifier must remain discoverable:

| Object | Minimum implementation contract | Evidence / common regression |
|---|---|---|
| `Namespace` | `metadata.name: rahbar`; all resources use namespace | `kubectl get all -n rahbar`; default namespace empty of project objects |
| `ConfigMap` | `RETRIEVER`, `LLM_PROVIDER`, `EMBED_MODEL`, `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION`, `TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TEMPERATURE`, relevance/cache thresholds; distinguish API and indexer consumers | `kubectl describe configmap`; both workloads see same embedding pin |
| `Deployment/api` | initial three replicas; `strategy.rollingUpdate.maxSurge: 1`, `maxUnavailable: 0`; resource requests/limits; nonroot + read-only; preStop sleep + graceful termination; all three probes | `kubectl get pods`, `kubectl get endpoints api`, rolling update and rollback |
| `Deployment/ui` | nginx unprivileged, port 8080, read-only root, `/tmp` writable `emptyDir`; ≥1 replica | `/` gives UI, UI fetches same-origin `/api/ask` |
| `StatefulSet/chroma` | **one** replica, version `chromadb/chroma:1.0.12` to match starter Python client; `volumeClaimTemplates`, mounted `/data`; ClusterIP | delete Chroma pod, verify PVC and data persistence; *do not use a Deployment* |
| `Deployment/redis` and PVC | service port 6379, persistent `/data`, AOF/appendonly enabled, filesystem ownership compatible with nonroot | cache survives pod restart; redis never exposed externally |
| `Job/indexer` | one-shot `python -m pipeline.run` (or `--dummy` only in early phase); `restartPolicy: OnFailure`, explicit `backoffLimit`, memory larger than serving pod if measured | Job transitions Complete, logs actual chunks, does **not** start with API |
| `CronJob/reindex` | weekly schedule, same image and arguments as Job, `concurrencyPolicy: Forbid`, explicit job history and resource policy | manual `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` |
| Four Services | API→8000, UI→8080, Chroma→8000, Redis→6379, all ClusterIP | `kubectl get svc -n rahbar`; no NodePort/LoadBalancer for data stores |
| Ingress | same host with `/api` prefix routed to API and `/` routed to UI; prefix order must favor `/api` | curl through real host/header; avoid accidental `/api` stripping |
| `Secret` | if hosted, created at runtime by `kubectl create secret`; committed sample has **no real** value | `git grep` secret checks; no real Base64 manifests |
| `NetworkPolicy` | default-deny ingress+egress and explicit app-specific allow rules, DNS and external model egress | test expected flows *and* UI→Chroma rejection |
| HPA | API target `minReplicas:3,maxReplicas:8`, valid CPU request, utilization target as tested | `kubectl get hpa -n rahbar` contains number, not `<unknown>` |

### Probe and rollout specifics

Starter-required probe pattern (verify endpoint port and route):

```yaml
startupProbe:
  httpGet: {path: /healthz, port: 8000}
  periodSeconds: 2
  failureThreshold: 30
livenessProbe:
  httpGet: {path: /healthz, port: 8000}
  periodSeconds: 20
  failureThreshold: 3
readinessProbe:
  httpGet: {path: /readyz, port: 8000}
  periodSeconds: 10
  failureThreshold: 3
```

**Never put Chroma/Redis/LLM calls in `/healthz`.** Readiness tests dependencies with short timeouts and reports 503 on unavailable, empty or mismatched active Chroma and on unavailable Redis. When the initial cluster is built around stubs, establish a consistent fixture/dummy pin before requiring real metadata; document exactly when the probe is enabled.

### Deployment-order contract

1. Boot Calico minikube (`minikube start --driver=docker --cni=calico --memory=6144 --cpus=4`) and enable `ingress` and `metrics-server`.
2. Render and validate `k8s/overlays/dev` before applying; create namespace, ConfigMap, storage and internal Services, then workloads. In a public repository create real hosted credentials **after** namespace creation and **never** by committing YAML.
3. Ensure Chroma and Redis are available; run the dummy indexer Job, then wait for three API Ready endpoints and Ingress UI/API success. An empty real collection must leave API unready.
4. Transition to real indexing: update both indexer/API `EMBED_MODEL` from `dummy-768` to real model, launch full Job, publish verified collection and ensure readiness becomes green; do not conceal model-pin conflicts by relaxing the readiness check.
5. Use `k8s/overlays/prod` for final image SHA tags and environment-specific host, not literal `:latest`. Apply `kubectl rollout status deployment/api -n rahbar` and test current and absent questions via Ingress.

### Persistent storage and image traps

- Chroma volume belongs to the StatefulSet `volumeClaimTemplates`; Redis has its own PVC. Persistence is graded even on local minikube.
- Prefer image tags pinned to compatible versions; capture `kubectl describe pod` events before changing images based on guesses.
- Locally built images often require `minikube image load <tag>`; use `IfNotPresent` for locally loaded tags.
- A **default-deny egress** policy blocks DNS unless port 53 UDP/TCP toward kube-system DNS is explicitly allowed; check `nslookup chroma` inside an eligible pod.
- When Ollama runs on host, resolve `host.minikube.internal`, verify listening on `0.0.0.0:11434` and allow its *observed host IP* as an egress destination. Never use broad unrestricted egress just to bypass debugging.
- Choose resource limits from measured `kubectl top pods` rather than copying example values into a report; memory over-limit usually exits 137.

### Kubernetes acceptance script (commands after implementation)

```bash
kubectl get all,pvc,ingress,hpa,networkpolicy -n rahbar
kubectl get endpoints -n rahbar
kubectl get pods -n rahbar -o wide
kubectl logs job/indexer -n rahbar           # substitute actual Job name
kubectl rollout status deployment/api -n rahbar
kubectl top pods -n rahbar
kubectl get hpa -n rahbar
```

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-specs-kubernetes-md"></a>

## Implementation spec — Kubernetes


**Owner:** B. **WBS:** T05,T06,T11,T16,T20. **Primary paths:** `k8s/base/*; k8s/overlays/{dev,prod}/*`. **Status:** target implementation design; run tests to verify. **Source authority:** assignment PDF + STARTER.md + existing starter signatures.


### Object checklist (mandatory)
Namespace `rahbar`; ConfigMap (EMBED_MODEL, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, RELEVANCE_FLOOR, CACHE_THRESHOLD, TEMPERATURE, LLM_PROVIDER, CHROMA_HOST, etc.); placeholder-only Secret **not applied**; API Deployment 3 replicas; nginx UI Deployment 1+; Chroma StatefulSet with volumeClaimTemplates; Redis Deployment+PVC; indexer Job and weekly CronJob same image+args; 4 ClusterIP Services; Ingress `/api` vs `/`; default-deny+allow NetworkPolicy; CPU HPA min=3 max=8; dedicated ServiceAccounts.

### Build/apply order
`minikube start --driver=docker --cni=calico --memory=6144 --cpus=4`, addons metrics-server and ingress. Apply namespace, ConfigMap, PVC-backed data stores and Services first; then build/load pinned images; create optional Secret if hosted; then indexer Job/dummy index; API/UI Deployments, probes, ingress, policies and HPA. If kustomize applies all at once, readiness must wait until index finished; `kubectl rollout status` follows the indexing Job. No default namespace objects.

### Pod hardening/resources
`runAsNonRoot`, read-only root, drop all Linux caps, disable service account token automount for non-Kubernetes clients, proper `/tmp` writable emptyDir, resource requests/limits on every container, API termination grace + preStop and rolling maxSurge=1/maxUnavailable=0. Chroma client/server 1.0.12. Image references are immutable commit SHAs in prod, not `latest`. HPA CPU utilization requires valid requests.cpu and metrics-server.

### Gotchas
Calico mandatory for enforced NetworkPolicies; allow DNS egress port53 TCP+UDP; host.minikube.internal Ollama network and host bind `OLLAMA_HOST=0.0.0.0`; minikube image load for locally built images; setup Host header `rahbar.local`; on macOS/Windows docker driver use minikube tunnel. Only route Chroma/Redis on ClusterIP. Ensure initial dummy model `dummy-768` matches config when demoing dummy index.


### Definition of Done and handoff
- [ ] Only owner-approved paths edited, no contract drift or secret exposure.
- [ ] Tests executed for normal + listed negative cases; actual stdout/exit code linked from PR.
- [ ] Any relevant experiment is measured with the frozen golden set, not filled by guesswork.
- [ ] Consumer task owner receives exact invocation, env settings and expected response shape.
- [ ] Corresponding `Rxx` traceability rows moved to VERIFIED only after peer review.

---

