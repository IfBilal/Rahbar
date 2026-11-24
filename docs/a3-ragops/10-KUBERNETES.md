# 10 — Part F: running it on Kubernetes

Covers **F1-01…F1-04, F2-01…F2-05, F3-01…F3-05, F4-01…F4-03, F5-01, F-ALL-01, G-15** (paper 4.1(e) Deployment, 4.1(f) Operate & monitor, 5.1 reliability). Owner: **B**. Tasks T47–T58 in [11](11-IMPLEMENTATION-PLAN.md). The release mechanics are explained in [07](07-CHANGE-AND-RELEASE.md) §7–8; trace/volume details in [08](08-OBSERVABILITY-TRACING.md) §4.

> **Hard rule (PDF):** the pipeline must run on Kubernetes at the demo. Docker-only, Compose, or "run the suite on the laptop for speed" during the demo = **0 for the demo**. Every command in the demo script is a `kubectl` command (13).

All YAML below is a **sketch of the fields that matter**; copy the *style* of the A2 manifests in `k8s/base/` (security contexts, `readOnlyRootFilesystem`, `enableServiceLinks: false`, resource blocks). Numbers marked `MEASURE` are **starting guesses to be replaced by the F5 measurements** — do not commit a guess as if it were measured.

---

## 1. Object inventory (what exists after this part)

| Object | Kind | File | Origin |
|---|---|---|---|
| Namespace `rahbar` | Namespace | `k8s/base/namespace.yaml` | A2 |
| Live API | Deployment `api` (3 replicas, HPA 3–8) + Service `api` | `k8s/base/api.yaml`, `services.yaml`, `hpa.yaml` | A2, **modified** (release env, traces PVC) |
| Vector store | StatefulSet `chroma` + PVC template + Service | `k8s/base/chroma-statefulset.yaml` | A2 |
| Cache | Deployment `redis` + PVC + Service | `k8s/base/redis.yaml` | A2 |
| UI, Ingress | Deployment `ui`, Ingress | `k8s/base/ui.yaml`, `ingress.yaml` | A2 |
| **Data lake PVC** | PVC `ragops-data` | `k8s/base/ragops-storage.yaml` | **new** |
| **Traces PVC** | PVC `ragops-traces` | same | **new** |
| **Results PVC** | PVC `ragops-results` | same | **new** |
| **RAGOps config** | ConfigMap `ragops-config` (verification/ingest/eval knobs) | `k8s/base/ragops-config.yaml` | **new** |
| **Gate thresholds** | ConfigMap `ragops-gate` (`gate.yaml`) | `k8s/base/ragops-gate.yaml` | **new** |
| **Eval target** | ConfigMap `ragops-eval-target` (which Service to test, label, mode) | `k8s/base/ragops-config.yaml` | **new** |
| **Ingestion CronJob** | CronJob `ingest` (replaces A2 `reindex`) | `k8s/base/ingest-cronjob.yaml` | **new / replaces** |
| **Ingestion Job** | Job `ingest` (on demand) | `k8s/ingest-job.yaml` | **new** (replaces A2 Job `indexer`) |
| **Evaluation Job** | Job `eval` | `k8s/eval-job.yaml` | **new** (exact path required by the PDF) |
| **Candidate** | Deployment `api-candidate` + Service `api-candidate` | `k8s/candidate.yaml` | **new** |
| **Loader pod** | Pod `ragops-loader` (copies files in/out of PVCs) | `k8s/loader-pod.yaml` | **new** |
| **Coverage Job** | Job `coverage` (optional) | `k8s/coverage-job.yaml` | **new** |
| **Network rules** | NetworkPolicies for eval, candidate, loader | `k8s/base/ragops-networkpolicy.yaml` + edits | **new** |
| ServiceAccounts | per workload, token automount false | `k8s/base/serviceaccounts.yaml` | A2 + new `ragops-eval`, `ragops-loader` |

**Why this split:** everything the cluster needs to be a *working pipeline* from `kubectl apply -k k8s/overlays/dev` lives in **`k8s/base/`** (so a fresh cluster reaches a working pipeline by applying it — G-15). Things that are **run on demand** and re-run (`Job`s) or are **steady-state experiments** (candidate, loader) are plain manifests under `k8s/` applied with `kubectl apply -f` — Jobs must not be in a kustomization because re-applying a finished Job fails (spec is immutable); you `delete` then `apply`.

---

## 2. Storage (F1-04) — `k8s/base/ragops-storage.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: ragops-data, namespace: rahbar, labels: {app: ragops}}
spec:
  accessModes: [ReadWriteOnce]
  resources: {requests: {storage: 2Gi}}      # lake + archive + quarantine + ledger + reports; MEASURE growth
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: ragops-traces, namespace: rahbar, labels: {app: ragops}}
spec: {accessModes: [ReadWriteOnce], resources: {requests: {storage: 1Gi}}}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: ragops-results, namespace: rahbar, labels: {app: ragops}}
spec: {accessModes: [ReadWriteOnce], resources: {requests: {storage: 512Mi}}}
```

**Single-node `ReadWriteOnce` note (state it in `k8s/README.md`):** on minikube all pods run on **one node**, and RWO means "one *node*", so several pods (3–8 API pods, the ingest Job, the loader pod) may mount the same claim. On a multi-node cluster this would need `ReadWriteMany` or a per-pod sidecar shipping logs; say so under limits. Persistence proof (F1-04): `kubectl delete pod` the writer, then show the lake/quarantine/archive/ledger still present (the demo's "survive pod restarts" check).

Mount map:

| Volume | api / candidate | ingest Job/CronJob | eval Job | loader pod | coverage Job |
|---|---|---|---|---|---|
| `ragops-data` | — | **rw** `/data` | **ro** `/data` | rw `/data` | ro `/data` (optional) |
| `ragops-traces` | **rw** `/traces` | — | **ro** `/traces` | rw (for `kubectl cp` out) | — |
| `ragops-results` | — | — | **rw** `/results` | rw | rw |
| ConfigMap `ragops-gate` | — | — | ro `/config/gate.yaml` | — | — |

---

## 3. API Deployment changes (`k8s/base/api.yaml`)

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          envFrom:
            - configMapRef: {name: rahbar-config}
            - configMapRef: {name: ragops-config}              # EVAL_* flags, trace settings
            - secretRef: {name: rahbar-secret, optional: true}
          env:                                                  # RELEASE-SCOPED: in the pod template on purpose (03 C-07, 04 §6)
            - {name: HOME, value: /tmp}
            - {name: RELEASE_ID,         value: R1-nomic}
            - {name: CHROMA_COLLECTION,  value: rahbar}
            - {name: EMBED_MODEL,        value: nomic-embed-text}
            - {name: EMBED_VERSION,      value: "<ollama digest>"}     # filled at first deploy, committed
            - {name: RELEVANCE_FLOOR,    value: "0.60"}
            - {name: TOP_K,              value: "5"}
            - {name: POD_NAME, valueFrom: {fieldRef: {fieldPath: metadata.name}}}
          volumeMounts:
            - {name: tmp,    mountPath: /tmp}
            - {name: traces, mountPath: /traces}
      volumes:
        - {name: tmp, emptyDir: {}}
        - {name: traces, persistentVolumeClaim: {claimName: ragops-traces}}
```
* Remove `CHROMA_COLLECTION`, `EMBED_MODEL`, `TOP_K`, `RELEVANCE_FLOOR` from `rahbar-config` **for the API only** — explicit `env` entries override `envFrom`, so you can leave the keys in the ConfigMap for the **ingest** consumers and for A2 compatibility, but then the two copies can drift: add a test that the Deployment's values and the ConfigMap's agree at commit time, or delete the API-side keys from the ConfigMap and give the ingest Job its own (preferred: one place per consumer).
* `strategy: {type: RollingUpdate, rollingUpdate: {maxSurge: 1, maxUnavailable: 0}}`, `revisionHistoryLimit: 5` (A2 already) — **keep**; `rollout undo` needs history.
* `progressDeadlineSeconds: 1800` (A2) stays for first deploy; for the demo of S3-a use `kubectl rollout status --timeout=120s` rather than waiting 30 minutes.
* `tests/test_manifests.py` currently asserts the API has **no** `EMBED_MODEL` in `env` (A2 C-07). **Change the assertion deliberately** to: the *release-scoped keys are present in the pod template*, `REDIS_URL` etc. still come from `envFrom`, and the readiness probe still enforces the pin. Record the reason in the PR (the safety property — a mismatched pod stays unready — is unchanged).

---

## 4. Candidate (F3-01) — `k8s/candidate.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: api-candidate, namespace: rahbar, labels: {app: api-candidate}}
spec:
  replicas: 1
  strategy: {type: RollingUpdate, rollingUpdate: {maxSurge: 1, maxUnavailable: 0}}
  selector: {matchLabels: {app: api-candidate}}
  template:
    metadata: {labels: {app: api-candidate}}
    spec:
      serviceAccountName: api
      automountServiceAccountToken: false
      enableServiceLinks: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, runAsGroup: 10001, fsGroup: 10001, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: api
          image: rahbar-api                      # same image as live: the candidate differs by CONFIG, not code
          envFrom: [{configMapRef: {name: rahbar-config}}, {configMapRef: {name: ragops-config}}]
          env:
            - {name: RELEASE_ID,        value: R2-mxbai}
            - {name: CHROMA_COLLECTION, value: rahbar-cand-mxbai}
            - {name: EMBED_MODEL,       value: mxbai-embed-large}
            - {name: EMBED_VERSION,     value: "<digest>"}
            - {name: RELEVANCE_FLOOR,   value: "<calibrated>"}
            - {name: REDIS_URL,         value: ""}               # cache OFF (03 C-08)
            - {name: POD_NAME, valueFrom: {fieldRef: {fieldPath: metadata.name}}}
          # same probes as live: /healthz (startup, liveness), /readyz (readiness)
          # resources: its own measured numbers
          volumeMounts: [{name: tmp, mountPath: /tmp}, {name: traces, mountPath: /traces}]
      volumes: [{name: tmp, emptyDir: {}}, {name: traces, persistentVolumeClaim: {claimName: ragops-traces}}]
---
apiVersion: v1
kind: Service
metadata: {name: api-candidate, namespace: rahbar, labels: {app: api-candidate}}
spec: {type: ClusterIP, selector: {app: api-candidate}, ports: [{name: http, port: 8000, targetPort: 8000}]}
```
* **Selector isolation:** labels `app: api-candidate` ≠ `app: api`, so the live Service never routes to it and the live HPA never counts it. Do **not** expose it through the Ingress.
* `REDIS_URL: ""` ⇒ the A2 code disables the cache and readiness skips the Redis check (`if settings.redis_url:`), exactly what we want.
* The candidate traces carry `release_id: R2-mxbai`, so `trace.summary --release` can separate them.

---

## 5. Jobs and CronJob (F2-01, F2-02, F2-04)

### 5.1 Ingestion Job — `k8s/ingest-job.yaml`
```yaml
apiVersion: batch/v1
kind: Job
metadata: {name: ingest, namespace: rahbar, labels: {app: indexer}}      # A2 label so the A2 NetworkPolicy (chroma, Ollama, web) applies
spec:
  backoffLimit: 2
  activeDeadlineSeconds: 3600
  template:
    metadata: {labels: {app: indexer}}
    spec:
      restartPolicy: OnFailure                    # A2 convention; fatal errors retry up to backoffLimit
      serviceAccountName: indexer
      automountServiceAccountToken: false
      enableServiceLinks: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, runAsGroup: 10001, fsGroup: 10001, seccompProfile: {type: RuntimeDefault}}
      initContainers:
        - name: seed-inbox                        # only when the inbox has never been seeded
          image: rahbar-indexer
          command: ["sh","-c"]
          args: ["python -m pipeline.seed --inbox /data/inbox"]   # no-op if /data/inbox/.seeded exists; else A2 fetch.py + manifest diff
          volumeMounts: [{name: data, mountPath: /data}, {name: tmp, mountPath: /tmp}]
      containers:
        - name: indexer
          image: rahbar-indexer
          args: ["sync"]                          # python -m pipeline.run sync ; exit 1 (quarantine) mapped to success by the wrapper
          envFrom: [{configMapRef: {name: rahbar-config}}, {configMapRef: {name: ragops-config}}]
          env:
            - {name: DATA_DIR, value: /data}
            - {name: INDEX_TARGETS, value: "registered"}     # every index in the ledger (05 §6.2b)
          volumeMounts: [{name: data, mountPath: /data}, {name: tmp, mountPath: /tmp}]
          resources: {requests: {cpu: "1", memory: 1Gi}, limits: {cpu: "2", memory: 1536Mi}}   # A2 numbers; MEASURE again
      volumes:
        - {name: data, persistentVolumeClaim: {claimName: ragops-data}}
        - {name: tmp,  emptyDir: {sizeLimit: 512Mi}}
```
* The wrapper (`pipeline/job_entry.sh` or a `python -m pipeline.run --job-mode`) maps the CLI's exit `1` (finished, some documents quarantined) to **0**, passes `3` through. State this in `k8s/README.md`.
* Other operations (`restore`, `delete`, `build-index`, `count`) reuse the manifest with different `args`. Provide `scripts/ragops/job.sh <name> -- <args…>` that renders `k8s/ingest-job.yaml` with `args` replaced (`sed`/`kubectl patch --local`) and applies it as `ingest-<action>-<ts>`; keep the naming so `kubectl get jobs` tells the story.
* Ollama: `OLLAMA_URL=http://host.minikube.internal:11434` from `rahbar-config`; the A2 policy already allows the host IP on 11434 from `app: indexer`.

### 5.2 Ingestion CronJob — `k8s/base/ingest-cronjob.yaml`
Same pod template as 5.1, `schedule: "0 3 * * 0"` (A2's weekly slot; choose and justify), `concurrencyPolicy: Forbid`, `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`, `startingDeadlineSeconds: 3600`. **Same image and arguments** as the Job (A2 rule). Manual trigger (demo): `kubectl create job --from=cronjob/ingest ingest-manual-1 -n rahbar`. Delete the A2 `reindex` CronJob and `indexer` Job from `k8s/base/kustomization.yaml` (and the Makefile's `index` target → `ingest`) so there is **one** writer definition; update `tests/test_manifests.py` and the README accordingly.

### 5.3 Evaluation Job — **`k8s/eval-job.yaml`** (the PDF's literal path)
```yaml
apiVersion: batch/v1
kind: Job
metadata: {name: eval, namespace: rahbar, labels: {app: ragops-eval}}
spec:
  backoffLimit: 0                                  # a failing gate must stay failed, not retry into a pass
  activeDeadlineSeconds: 14400                     # MEASURE: longest suite run + margin
  template:
    metadata: {labels: {app: ragops-eval}}
    spec:
      restartPolicy: Never
      serviceAccountName: ragops-eval
      automountServiceAccountToken: false
      enableServiceLinks: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, runAsGroup: 10001, fsGroup: 10001, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: eval
          image: rahbar-ragops
          command: ["/app/job_entry.sh"]           # suite -> result file -> gate -> exit code
          envFrom: [{configMapRef: {name: ragops-eval-target}}, {configMapRef: {name: ragops-config}}]
          env:
            - {name: OLLAMA_URL, valueFrom: {configMapKeyRef: {name: rahbar-config, key: OLLAMA_URL}}}
            - {name: GATE_CONFIG, value: /config/gate.yaml}
            - {name: RESULTS_DIR, value: /results}
          volumeMounts:
            - {name: gate,    mountPath: /config, readOnly: true}
            - {name: results, mountPath: /results}
            - {name: data,    mountPath: /data,   readOnly: true}
            - {name: traces,  mountPath: /traces, readOnly: true}
            - {name: tmp,     mountPath: /tmp}
          resources: {requests: {cpu: 250m, memory: 256Mi}, limits: {cpu: "1", memory: 768Mi}}   # MEASURE
      volumes:
        - {name: gate,    configMap: {name: ragops-gate}}
        - {name: results, persistentVolumeClaim: {claimName: ragops-results}}
        - {name: data,    persistentVolumeClaim: {claimName: ragops-data, readOnly: true}}
        - {name: traces,  persistentVolumeClaim: {claimName: ragops-traces, readOnly: true}}
        - {name: tmp,     emptyDir: {}}
```
**`job_entry.sh` (contract):** reads `MODE` (`suite+gate` default · `gate` = re-apply the gate to an existing result · `suite` = run only), `TARGET_URL`, `LABEL`, `BASELINE_RESULT`, `CANDIDATE_RESULT` from `ragops-eval-target`; runs `python -m ragops.suite.run_suite …` writing `/results/<ts>_<label>.json`; runs `python -m ragops.gate.apply --baseline … --candidate … --config $GATE_CONFIG --decision-out /results/<ts>_<label>.decision.json`; **`exit` with the gate's exit code** (1 = FAIL → Job `Failed`, 0 = Complete). Suite infrastructure errors exit 3 (also `Failed`, distinguishable in logs by the final line `RESULT=INFRA_ERROR`). The last log line is always machine-readable: `RESULT=GATE_PASS|GATE_FAIL|INFRA_ERROR decision=<file>`.

`ragops-eval-target` (ConfigMap, edited with `kubectl patch`/`create … --dry-run=client -o yaml | kubectl apply -f -`; wrapped by `make eval TARGET=live|candidate LABEL=…`):

```yaml
data: {TARGET_URL: "http://api-candidate:8000", LABEL: "cand-mxbai", MODE: "suite+gate",
       BASELINE_RESULT: "/results/baselines/live.json", CANDIDATE_RESULT: "", SUITE_ARGS: "--batches A"}
```

**Show that changing a threshold changes the outcome without rebuilding the image (F2-05, Screenshot F4):**
1. `MODE=gate`, `CANDIDATE_RESULT=<an existing result>` (seconds, no suite run). `kubectl delete job eval --ignore-not-found; kubectl apply -f k8s/eval-job.yaml` → `kubectl wait --for=condition=failed job/eval` → logs show `GATE_FAIL`, e.g., `recall@5 … limit 0.02`.
2. `kubectl edit configmap ragops-gate -n rahbar` (or `kubectl patch`): relax `recall5_drop` `0.02 → 0.10`.
3. Delete and re-apply the **same** manifest → `GATE_PASS`. Prove the image did not change: `kubectl get job eval -o jsonpath='{.spec.template.spec.containers[0].image}'` printed both times (identical, ideally a digest/tag SHA), and `kubectl get cm ragops-gate -o yaml | head` showing the change. (A new Job pod reads the ConfigMap at start; do not rely on live-updating a running pod.)

---

## 6. Rollout, rollback and history (F3-02…F3-05) — the commands that matter

```bash
kubectl -n rahbar get deploy api -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' | grep -E 'RELEASE|COLLECTION|EMBED'
scripts/ragops/release.sh cand-mxbai                      # refuses without a passing decision.json
kubectl -n rahbar rollout status deployment/api --timeout=900s
kubectl -n rahbar rollout history deployment/api          # revisions with change-cause
kubectl -n rahbar rollout undo deployment/api             # back to the previous ReplicaSet (and its env)
kubectl -n rahbar rollout status deployment/api
curl -s -X POST http://$INGRESS/api/ask -H 'Host: rahbar.local' -H 'Content-Type: application/json' -d '{"question":"…"}' | jq .trace_id
python -m ragops.trace.show <trace_id>                    # shows collection=rahbar, embedding=nomic-embed-text@<digest>, release_id=R1
```
Watch zero-downtime in a second terminal during the rollout: `watch -n1 kubectl get pods -l app=api` and `while true; do curl -s -o /dev/null -w '%{http_code}\n' …; sleep 0.5; done` (all `200`). With `maxSurge 1 / maxUnavailable 0` and readiness gating, the live Service never has fewer than 3 ready endpoints; the A2 `preStop sleep 10` plus the 240 s grace protect in-flight answers.

Pitfalls: `kubectl rollout undo` goes back **one** revision (`--to-revision=N` for others); a **scale** change does not create a revision; `kubectl set env` with no actual change creates no revision; `kubectl rollout history` is limited by `revisionHistoryLimit` (5).

---

## 7. NetworkPolicy additions (`k8s/base/ragops-networkpolicy.yaml` + edits)

A2 is default-deny-all plus per-app allows. The new pods need explicit rules; **keep every A2 denial** (ui → chroma denied; redis from api only).

| Rule | Selector → destination | Ports |
|---|---|---|
| `eval-egress` | `app=ragops-eval` → `app=api`, `app=api-candidate` | TCP 8000 |
| `eval-egress-ollama` | `app=ragops-eval` → host ipBlock (A2's `192.168.49.1/32`; overlay-patchable) | TCP 11434 |
| `api-ingress-from-eval` | edit A2 `api-policy`: add `from: podSelector app=ragops-eval` | TCP 8000 |
| `candidate-policy` | `app=api-candidate`: ingress from `app=ragops-eval` (8000); egress to `app=chroma` (8000), Ollama (11434) — **no Redis** | |
| `chroma-ingress` | edit A2 `chroma-from-api-and-indexer`: add `app=api-candidate` (**not** `ragops-eval`) | TCP 8000 |
| `loader-isolation` | `app=ragops-loader`: ingress none, egress none (DNS only via `allow-dns-egress`) — `kubectl cp` uses the API server, not pod networking | |
| `coverage-policy` | `app=ragops-coverage`: egress Ollama only | |

Verification (keep outputs): `kubectl exec` from the eval pod: `api:8000` ok, `chroma:8000` **fails**, `redis:6379` **fails**; from the UI pod chroma still fails (A2). These are the F2-03 "only writer" evidence next to the lock and boundary tests.

---

## 8. The loader pod and getting files in and out (inbox, traces, results)

`k8s/loader-pod.yaml`: a small pod running **the `rahbar-ragops` image** with `sleep infinity` (it has `tar` for `kubectl cp` **and** the local-file tools), non-root, mounting `ragops-data` at `/data`, `ragops-traces` at `/traces`, `ragops-results` at `/results` (all rw). Label `app: ragops-loader`. It doubles as the **in-cluster tool shell**: `kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.show <id>` / `… ragops.trace.summary --since 1h` / `… pipeline`-free report readers all work from here, so the demo never needs a Python environment on the laptop. (Tools that need the network — coverage, suite — run as Jobs, because this pod has no egress.)

```bash
kubectl apply -f k8s/loader-pod.yaml && kubectl wait --for=condition=Ready pod/ragops-loader -n rahbar
kubectl cp corpus/batch-b/. rahbar/ragops-loader:/data/inbox/            # drop Batch B / the unseen demo batch
kubectl cp rahbar/ragops-loader:/results/. ./eval/results/               # pull results to commit (G-10)
kubectl cp rahbar/ragops-loader:/traces/ ./traces/                       # curated sample (commit a few lines only)
kubectl delete pod ragops-loader -n rahbar                               # when done
```
`kubectl cp` needs `tar` in the container: use an image that has it. File ownership: copied files are owned by the user `kubectl cp` runs as inside the container (non-root uid 10001): fine for the ingest Job (same uid/gid via `fsGroup`).

---

## 9. "Which Kubernetes object carries which RAGOps responsibility" (short answer (f); draft)

| RAGOps responsibility | Object(s) | How |
|---|---|---|
| Ingestion runs once and ends | **Job** `ingest` | `restartPolicy: OnFailure`, `backoffLimit`, exit code |
| Scheduled re-ingestion | **CronJob** `ingest` | `concurrencyPolicy: Forbid`, same image/args as the Job |
| **Only one writer to the vector store** | **Job + CronJob (`Forbid`, `parallelism: 1`) + lock file on the PVC + NetworkPolicy + boundary tests + no API token** | layered, because Chroma has no auth (D-15); not "Kubernetes makes it read-only" |
| Data lake, quarantine, archive survive restarts | **PVC** `ragops-data` | RWO claim mounted only where needed (rw for the Job, ro for eval) |
| Vector index survives restarts | **StatefulSet** `chroma` + `volumeClaimTemplates` | stable identity + its own PVC |
| Traces survive and are readable | **PVC** `ragops-traces` + stdout (`kubectl logs`) | per-pod files |
| Thresholds editable without a rebuild | **ConfigMap** `ragops-gate` | mounted file read at Job start |
| Offline test as a gate | **Job** `eval` | `backoffLimit: 0`, exit code = gate verdict |
| Result files outlive the Job | **PVC** `ragops-results` | `kubectl cp` to the repo |
| Candidate isolated from live users | **Deployment** `api-candidate` + **Service** + own collection + own label | different selector, no Ingress, cache off |
| Zero-downtime release | **Deployment** `RollingUpdate` (`maxSurge 1`, `maxUnavailable 0`) + **readiness probe** | the pin check keeps a bad pod out of the Service |
| Rollback | **ReplicaSet** history, `kubectl rollout undo` | release identity lives in the pod template |
| Availability/scale | **HPA** 3–8, probes, resource requests | `kubectl get hpa` shows numbers, not `<unknown>` |
| Isolation | **NetworkPolicy**, **ServiceAccounts** | default-deny + explicit flows |
| Reaching metrics | **Service**/`kubectl port-forward` | `/metrics` |

---

## 10. F5 — resources from measurements

Requests/limits for **api, chroma, candidate, the Jobs (ingest, eval, coverage)** must come from what you measured, with the numbers in the report.

**Method (repeat per workload, ≈ 15 min each):**
1. Start a sampler *before* the workload: `while true; do date -u +%FT%TZ; kubectl top pods -n rahbar --containers --no-headers; sleep 5; done | tee docs/a3-evidence/top-<workload>.txt` (metrics-server must be on — A2 `make cluster` enables it; its window is ≈ 15–60 s so short Jobs need the loop running).
2. Run the real workload: serving under the suite's `/api/ask` load; the full ingest of Batch A (OCR peak!); Batch B; the eval Job; the candidate under load.
3. Extract **peak and steady** CPU/memory from the file (a 10-line script). Record the table below.
4. Set `requests` ≈ typical steady usage (memory) / p50 (CPU), `limits.memory` ≈ peak × 1.3–1.5 (memory limit breach = exit 137 `OOMKilled`; confirm with `kubectl describe pod`), `limits.cpu` ≥ peak. The API CPU **request** is also the HPA denominator — keep it > 0.
5. Re-run once with the final values to confirm no OOM and no throttling-induced timeout.

| Workload | Measured peak CPU / mem | Steady CPU / mem | request | limit | Source file |
|---|---|---|---|---|---|
| api (live) | MEASURE | MEASURE | | | `docs/a3-evidence/top-api.txt` |
| api-candidate | | | | | |
| chroma | | | | | |
| ingest Job | | | | | (A2 measured 1268m / 910Mi for the old indexer — verification and doc vectors add to it) |
| eval Job | | | | | |
| coverage Job | | | | | |

A2's measured numbers (api 100m/96Mi request, 500m/256Mi limit; chroma 25m/64Mi, 500m/512Mi; indexer 1 CPU/1Gi, 2/1536Mi) are **the starting points to re-measure**, not values to copy without checking the new workloads.

---

## 11. Observability on the cluster (F4)

| Requirement | How | Check |
|---|---|---|
| Traces on stdout as JSON lines | trace logger prints `"type":"trace"` lines | `kubectl logs deploy/api -n rahbar --since=5m | grep '"type":"trace"' | tail -1 | jq .` |
| Traces on a volume | `/traces/<pod>.jsonl` | `kubectl exec deploy/api -- ls -l /traces` / loader pod `ls` |
| Metrics via port-forward | `/metrics` | `kubectl port-forward -n rahbar deploy/api 8000:8000` + `curl -s localhost:8000/metrics | grep -E 'rahbar_(top1|stage|injection|cache)'` |
| Report scripts read the volume | `ragops.trace.summary --traces-dir /traces` as a Job or on the laptop after `kubectl cp` | summary output |

Note for `kubectl logs deploy/api`: it reads **one** pod; use `kubectl logs -l app=api --tail=… --prefix` to see all three.

---

## 12. `k8s/README.md` (required by the PDF) — contents

1. Prerequisites (versions you tested): Docker, minikube + Calico, kubectl, kustomize, Ollama on the host with `OLLAMA_HOST` reachable from the cluster, models pulled (`nomic-embed-text`, `llama3.2:3b`, candidate models).
2. **Fresh-cluster order** (every extra command, in order):
   ```bash
   make cluster                         # minikube --cni=calico, metrics-server, ingress
   ollama pull nomic-embed-text llama3.2:3b <candidate models>; make ollama-host   # host Ollama reachable at host.minikube.internal
   make images TAG=dev                  # builds + loads api, indexer, ui, ragops
   kubectl apply -k k8s/overlays/dev    # namespace, storage, config, services, chroma, redis, api, ui, cronjob, policies, hpa
   kubectl apply -f k8s/ingest-job.yaml # first ingestion (seeds the inbox, verifies, indexes)
   kubectl -n rahbar wait --for=condition=complete job/ingest --timeout=3600s
   kubectl -n rahbar rollout status deployment/api
   make eval-baseline                   # runs k8s/eval-job.yaml against the live Service; then promote the baseline
   ```
3. How to run each part (A–F), the Job/ConfigMap switches (`ragops-eval-target`), loader pod usage, how to pull results.
4. Limits: single-node RWO, host Ollama dependency, no TLS, no auth on Chroma, demo-scale resources.
5. Teardown/reset: `kubectl delete ns rahbar` (deletes PVCs) vs `kubectl delete job …`.

The clean-cluster rehearsal (T58) proves this README from a **wiped** minikube, and its timing goes in the plan.

---

## 13. CI additions (small; do not run the full suite in GitHub Actions — 03 C-13)

* `manifests` job: `kustomize build k8s/overlays/{dev,prod,incluster} | kubeconform -strict` **and** `kubeconform -strict k8s/*.yaml` for the standalone manifests (Jobs, candidate, loader, coverage).
* Unit tests for the new code run in the existing `test` job (coverage ≥ 60% for each package as in A2).
* Trivy scan the new `rahbar-ragops` image (HIGH/CRITICAL with fixes) — same gate as A2.
* Build the new image in `build`; `cd.yml` pushes it with the commit SHA tag like the others (A2's no-`:latest` rule).

---

## 14. Pitfalls

| Pitfall | Consequence | Defence |
|---|---|---|
| Release values left in the shared ConfigMap | undo does not restore the collection/embedding | explicit `env` in the pod template |
| Applying a Job twice | `field is immutable` error | `kubectl delete job X --ignore-not-found` first (Makefile targets do it) |
| `ttlSecondsAfterFinished` small on `eval` | logs vanish before the screenshot | omit it (or ≥ 1 day) |
| Eval Job retrying | a failed gate turns into a pass on retry | `backoffLimit: 0`, `restartPolicy: Never` |
| CronJob and a manual Job overlapping | two writers | `Forbid` + the ledger lock + `release.sh` precondition |
| PVC permission denied (non-root) | pod CrashLoop on first write | `fsGroup`; test the first mount on a fresh cluster |
| `kubectl top` shows nothing for a Job | metrics-server window | run the sampler loop first |
| Default-deny blocks the new pods | eval cannot reach `api`/Ollama | §7 policies; test before the demo |
| Image not loaded into minikube | `ErrImagePull` | `minikube image load`, `imagePullPolicy: IfNotPresent` (A2 trap) |
| `kubectl cp` into a read-only mount | fails | copy into the loader pod's rw mounts only |
| Port-forwarded `/metrics` represents one pod | misleading totals | aggregate from traces |
| Wrong Ollama host IP in policy | embeddings time out only in the Job | reuse the A2 overlay patch for the host IP |
