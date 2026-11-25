# Running RAHBAR + RAGOps on Kubernetes

Everything here is applied with `kubectl`; nothing runs from `docker run` or Compose. Tested on
Ubuntu 24.04, Docker, minikube v1.39 (Calico), kubectl, kustomize, Ollama 0.17.

## Fresh cluster to a working pipeline

```bash
make cluster                       # minikube --cni=calico --memory=8g --cpus=4, metrics-server, ingress
ollama pull nomic-embed-text llama3.2:3b mxbai-embed-large all-minilm
make ollama-host                   # Ollama on the minikube gateway; runs in the FOREGROUND: leave it, use a second terminal
make images TAG=dev                # builds api, indexer, ui and ragops, loads them into minikube
make apply                         # creates the eval-token Secret (random, at run time), applies k8s/overlays/dev
kubectl -n rahbar wait --for=condition=complete job/ingest --timeout=3600s   # first ingestion: seed, verify, index
kubectl -n rahbar rollout status deployment/api
```

`kubectl apply -k k8s/overlays/dev` creates: the namespace, storage (3 PVCs), config (4 ConfigMaps),
Services, Chroma (StatefulSet), Redis, API (3 replicas, HPA 3-8), UI, Ingress, the ingest **Job**
and **CronJob**, and the NetworkPolicies. The standalone manifests in `k8s/` are applied on demand:

| File | What | Apply |
| --- | --- | --- |
| `eval-job.yaml` | the Part B suite + release gate; exits with the gate's code | `kubectl delete job eval -n rahbar --ignore-not-found; kubectl apply -f k8s/eval-job.yaml` |
| `candidate.yaml` | a second API Deployment + Service on its own collection | `scripts/ragops/candidate.sh cand-mxbai` |
| `loader-pod.yaml` | copy files into and out of the volumes; in-cluster tool shell | `kubectl apply -f k8s/loader-pod.yaml` |
| `coverage-job.yaml` | Part E coverage check, non-zero exit below the threshold | `kubectl delete job coverage -n rahbar --ignore-not-found; kubectl apply -f k8s/coverage-job.yaml` |

Jobs are not in the kustomization because a finished Job's pod template is immutable: delete the
Job, then apply it again (the ingest Job in the base is the exception; it runs once per `apply`).

## What runs each part

| Part | Command | Object |
| --- | --- | --- |
| A ingest, verify, update | `scripts/ragops/job.sh sync` (or `kubectl create job --from=cronjob/ingest ingest-manual-1 -n rahbar`) | Job / CronJob `ingest` |
| A report, count, restore, delete | `scripts/ragops/job.sh count -- count`, `... restore -- restore <doc>@<ver>`, `... delete -- delete <doc>` | Job `ingest-<action>-<ts>` |
| B suite | `make eval-suite LABEL=baseline` | Job `eval` (`MODE=suite`) |
| C gate | `make eval-gate LABEL=cand-mxbai`; thresholds: `kubectl edit configmap ragops-gate -n rahbar` | Job `eval`, ConfigMap `ragops-gate` |
| C/F3 release | `scripts/ragops/release.sh cand-mxbai`; undo: `kubectl rollout undo deployment/api -n rahbar` | Deployments `api`, `api-candidate` |
| D traces | `kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.show <trace_id> --traces /traces --lake /data`; `... ragops.trace.summary --traces /traces` | PVC `ragops-traces`, loader pod |
| D metrics | `kubectl port-forward -n rahbar deploy/api 8000:8000` then `curl localhost:8000/metrics` | Service / port-forward |
| E coverage | `kubectl apply -f k8s/coverage-job.yaml` | Job `coverage` |
| Getting files in and out | `python corpus/batch-b/build.py --out /tmp/batch-b-out` then `kubectl cp /tmp/batch-b-out/batch-b rahbar/ragops-loader:/data/inbox/`; `kubectl cp rahbar/ragops-loader:/results/. eval/results/` | loader pod |

## Which object carries which responsibility

| Responsibility | Object |
| --- | --- |
| Ingestion runs once and ends; scheduled re-ingestion | Job `ingest`; CronJob `ingest` (`concurrencyPolicy: Forbid`) |
| **Only one writer to the vector store** | the Job/CronJob (`Forbid`), a lock file on the PVC, NetworkPolicy (only `app=indexer` and the candidate reach Chroma; the eval Job cannot), no Kubernetes API token anywhere, and `tests/test_boundaries.py` (no Chroma write call in the API or in `ragops`) |
| Data lake, quarantine, archive, ledger survive restarts | PVC `ragops-data` (rw only for the Job and loader; eval mounts it read-only) |
| Vector index survives restarts | StatefulSet `chroma` with a `volumeClaimTemplate` |
| Traces survive and are readable | PVC `ragops-traces` (`/traces/<pod>.jsonl`) and stdout (`kubectl logs`) |
| Thresholds change without a rebuild | ConfigMap `ragops-gate`, read by the Job when it starts |
| Offline test as a gate | Job `eval` (`backoffLimit: 0`, exit code = gate verdict) |
| Candidate isolated from users | Deployment `api-candidate` + Service, own collection, own label, no Ingress, cache off |
| Zero-downtime release; rollback | `RollingUpdate` (`maxSurge: 1`, `maxUnavailable: 0`) + readiness probe; ReplicaSet history and `kubectl rollout undo` |
| Release identity restored by undo | the release-scoped env (`RELEASE_ID`, `CHROMA_COLLECTION`, `EMBED_MODEL`, `EMBED_VERSION`, `RELEVANCE_FLOOR`, `TOP_K`) lives in the API **pod template**, not a shared ConfigMap |
| Isolation | default-deny NetworkPolicy plus explicit flows; ServiceAccounts without tokens |

## Notes

* **Exit codes.** `pipeline.run` exits 1 when it finished but quarantined documents; `indexer/job_entry.sh` maps that to 0 so the Job is Complete. 3 (fatal) and 4 (unknown target) stay failures.
* **Eval token.** `/api/retrieve` and the `X-Eval-*` headers need `X-Eval-Token`, read from the Secret `ragops-eval-token`, which `scripts/ragops/eval-token.sh` creates with a random value. The Ingress sends `/api/retrieve` to the UI.
* **Ollama host.** If `host.minikube.internal` is not 192.168.49.1, change the `ipBlock` entries in `k8s/base/networkpolicy.yaml` and `k8s/base/ragops-networkpolicy.yaml`.

## A release is not in Git

`scripts/ragops/release.sh` changes the live Deployment with `kubectl set env`, because the release identity must
live in the pod template for `kubectl rollout undo` to restore it. The manifests in Git still say `R1-nomic`, so
re-running `kubectl apply -k k8s/overlays/dev` (or `make apply`) after a release **rolls the release back** to the
committed values. To keep a release, commit the new values in `k8s/base/api.yaml` (and `rahbar-config`), through a pull
request. The ingest Job and the API must agree on `EMBED_VERSION`; `tests/test_manifests.py` checks that.

## Limits

The in-cluster Ollama bonus overlay (`k8s/overlays/incluster`) patches the API and indexer policies only: the eval Job, the candidate and the coverage Job still point at the host Ollama there. Single node: `ReadWriteOnce` here means one node, so several pods share a claim; on a multi-node
cluster the data and traces volumes would need `ReadWriteMany` or a log-shipping sidecar. Ollama
runs on the host (no GPU on the measurement laptop, see `docs/a3-evidence/host.md`). No TLS, no
authentication on Chroma (it is isolated by NetworkPolicy only), demo-scale resources.

## Reset

`kubectl delete ns rahbar` removes everything including the PVCs. On minikube the hostpath
provisioner reuses its old directory, so a truly clean start also needs
`minikube ssh "sudo rm -rf /tmp/hostpath-provisioner/rahbar"`.
