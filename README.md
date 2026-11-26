# RAHBAR: grounded answers about FAST-NUCES rules, on Kubernetes

[![ci](https://github.com/IfBilal/Rahbar/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/IfBilal/Rahbar/actions/workflows/ci.yml)
[![cd](https://github.com/IfBilal/Rahbar/actions/workflows/cd.yml/badge.svg?branch=main)](https://github.com/IfBilal/Rahbar/actions/workflows/cd.yml)

A student wants to know whether they can still withdraw from a course. The answer is in
clause 4.25 of a PDF on the university website, and an older edition of the same rules,
with a different deadline, is still online next to it. A general chatbot answers
confidently from some other university's rules. **RAHBAR answers only from FAST-NUCES's
own public documents.** It quotes the current edition unless you ask about the old one,
cites the source, section and page of every claim, and says plainly when its documents do
not cover a question (try asking about hostel fees). It runs on Kubernetes: an indexing Job
builds the vector index, three read-only API replicas serve questions, and a CI gate fails
the build when retrieval quality drops.

Assignment 02, CS4032 · Team: Taimoor Shaukat (24I-3015), Muhammad Bilal Tahir (24I-3166)

![RAHBAR answering a question through the Ingress, with citations](docs/evidence/ui-screenshot.png)

## Architecture

```mermaid
flowchart LR
  U[Browser] -->|rahbar.local| ING[Ingress]
  ING -->|/| UI[ui · nginx]
  ING -->|/api| API[api · FastAPI × 3<br/>HPA 3..8]
  API -->|reads| CH[(chroma StatefulSet + PVC)]
  API <-->|semantic cache| R[(redis + PVC)]
  API -->|embed + generate| OL[Ollama on the host]
  JOB[indexer Job / weekly CronJob] -->|only writer| CH
  JOB -->|embed| OL
  CM[ConfigMap: EMBED_MODEL pin] -.-> API
  CM -.-> JOB
```

The indexer is a **Job**, never part of API startup (`docs/adr/0001-indexer-as-job.md`).
Each run writes a new index *generation* and then flips a pointer, so re-indexing happens
while the API keeps serving. The API reads, checks that the index was built with the same
embedding model (`EMBED_MODEL`), and stays out of the Service (`0/1 READY`) until it was.
Full design: `docs/ARCHITECTURE.md`.

| Measured on our stack | Value | Where |
| --- | --- | --- |
| Corpus | 9 public documents, 279 PDF pages + 2 web pages, 532 chunks | `docs/CORPUS.md` |
| recall@3 / recall@5 (19-question golden set) | 0.969 / 0.969 (ordinary 1.0, version 1.0, exact terms 0.833) | `eval/results.json` |
| Citation validity / must-abstain correctness | 100% / 100%; all 16 answerable answers correct on review (q09 fixed by the numeric table assist) | `eval/results.json`, `docs/PIPELINE.md` |
| Chunking shipped | 300 tokens, 40 overlap (best recall@3 of three measured settings) | `docs/PIPELINE.md` |
| Semantic cache threshold | 0.95, the lowest with zero false hits | `docs/evidence/cache-threshold.txt` |
| Indexer peak memory | 910 Mi (limit 1536 Mi) | `docs/evidence/kubectl-top-indexer-run.txt` |

## From a clean clone to an answered question

Tested on Ubuntu 24.04 with Docker, minikube v1.39, kubectl, kustomize and Ollama. On
macOS or Windows with the docker driver, run `minikube tunnel` and use `127.0.0.1` where
this guide says `$(minikube ip)`.

```bash
git clone https://github.com/IfBilal/Rahbar.git && cd Rahbar
make install                         # .venv with the api, indexer and test dependencies
make test                            # 250+ tests, no cluster, no model, no network

# 1. A cluster whose network plugin enforces NetworkPolicy (Calico), plus ingress and metrics
make cluster        # minikube start --driver=docker --cni=calico --memory=8192 --cpus=4
                    # minikube addons enable metrics-server ; minikube addons enable ingress

# 2. The models, on the laptop (ollama-host mode). Ollama must listen where pods can reach it.
ollama pull llama3.2:3b && ollama pull nomic-embed-text   # Assignment 03 candidates also need: mxbai-embed-large all-minilm
OLLAMA_HOST=0.0.0.0 ollama serve     # leave it running; use a second terminal for the rest (or: make ollama-host)

# 3. Images: build api, ui, indexer and ragops locally and load them into minikube
make images                          # TAG=dev

# 4. Apply (one command, see the order below), then wait for the index and the rollout
kubectl apply -k k8s/overlays/dev
kubectl wait --for=condition=complete job/ingest -n rahbar --timeout=40m
kubectl rollout status deployment/api -n rahbar

# 5. Ask through the Ingress
make ask Q="What is the deadline to withdraw from a course?"
make ask Q="What is the monthly hostel fee?"             # declines: not in the corpus
# or open the chat UI: add "$(minikube ip) rahbar.local" to /etc/hosts, browse http://rahbar.local
```

**Bonus: Ollama inside the cluster.** `kubectl apply -k k8s/overlays/incluster`, then
`kubectl rollout restart deployment/api -n rahbar`. This adds an Ollama Deployment with
a PVC for the weights; its init container pulls both models once, and its startupProbe
allows 30 × 10 s for loading. It switches `LLM_PROVIDER` to `ollama-incluster` and points
the API and the indexer at `http://ollama:11434` through NetworkPolicy. Verified on
minikube (`docs/evidence/ollama-incluster.txt`). The case study recommends
`--memory=8192` for this mode.

**Embeddings go through the same host Ollama.** In ollama-host mode both the indexer Job
and the API call `http://host.minikube.internal:11434` for `nomic-embed-text` embeddings as
well as `llama3.2:3b` generation; the model is pinned by `EMBED_MODEL` in the ConfigMap.

The first indexer run takes about 10 minutes on a laptop CPU: it downloads the corpus,
OCRs 32 scanned pages and embeds 532 chunks (the clean-clone run took 7 minutes,
`docs/evidence/clean-clone.txt`). Until it finishes, the API pods correctly
report `0/1 READY`.

### The apply order

`kubectl apply -k k8s/overlays/dev` renders `k8s/base` and applies it in a safe order:
kubectl creates the Namespace first, and every workload waits on what it needs through its
probes. Applied file by file, the equivalent order is:

```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/serviceaccounts.yaml -f k8s/base/configmap.yaml
scripts/ragops/eval-token.sh          # A3: the run-time Secret the API, the candidate and the eval Job read (pods wait for it)
# hosted LLM only; never from a file:
#   kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY="$LLM_API_KEY"
kubectl apply -f k8s/base/networkpolicy.yaml -f k8s/base/services.yaml
kubectl apply -f k8s/base/ragops-storage.yaml -f k8s/base/ragops-config.yaml -f k8s/base/ragops-gate.yaml -f k8s/base/ragops-networkpolicy.yaml
kubectl apply -f k8s/base/chroma-statefulset.yaml -f k8s/base/redis.yaml
kubectl apply -f k8s/base/ingest-job.yaml -f k8s/base/ingest-cronjob.yaml
kubectl apply -f k8s/base/api.yaml -f k8s/base/ui.yaml -f k8s/base/hpa.yaml -f k8s/base/ingress.yaml
```

(The dev overlay also pins the local image tags; applying `k8s/base` by hand needs
`kubectl set image` or the overlay.)

### Common operations

| Task | Command |
| --- | --- |
| Re-index now, no redeploy | `kubectl create job --from=cronjob/ingest ingest-manual-1 -n rahbar` (or `make index`) |
| Change the Job's template | `kubectl delete job ingest -n rahbar` first: a Job's pod template is immutable |
| Evaluate through the Ingress | `make eval` (writes `eval/results.json`, exits 1 if the gate fails) |
| Smoke test | `python3 scripts/smoke.py --api http://$(minikube ip)` |
| Live system checks | `make system-test` (pin, policy, abstention, pod deletion) |
| Hosted LLM key | `export LLM_API_KEY=...; make secret` |
| Ollama not on 192.168.49.1 | `minikube ssh "grep host.minikube.internal /etc/hosts"`; if it differs, change the two `ipBlock` entries in `k8s/base/networkpolicy.yaml` |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/ask` | `{"question": "..."}` (3–500 chars) → answer, citations, `answered_from_context`, confidence, retrieved passages with scores, provider, `cached`. 422 on a bad question. |
| GET | `/healthz` | Liveness: the process is alive. Touches nothing else. |
| GET | `/readyz` | Readiness: Chroma reachable, active collection non-empty, its embedding model equal to `EMBED_MODEL`, Redis reachable. 503 names the failed check. |
| GET | `/metrics` | Prometheus: requests and latency per route, retrieval and generation latency, cache lookups/hits/ratio, abstentions, fallbacks, tokens in/out per request. |

Every response carries `X-Request-ID` (yours, or generated), and every log line for that
request carries the same id.

## Corpus

Nine public FAST-NUCES documents: the June 2026 Academic Rules Handbook and the August 2023
edition it superseded, the 2026 Prospectus rules, the Student Handbook, two annual reports,
the fee and grading web pages, and a scanned ORIC policy. **We do not commit the documents.**
`corpus/MANIFEST.md` records each URL and SHA-256, and `corpus/fetch.py` downloads them.
The indexer Job runs that fetch at start-up and refuses bytes that differ from the manifest.
Hostel rules are deliberately absent. Details: `docs/CORPUS.md`.

## Repository map

```
api/        FastAPI service: reads the index, never writes it   (Dockerfile, tests/)
indexer/    the Job's image: extract, clean, chunk, embed, store (Dockerfile, tests/)
ui/         chat page served by nginx                            (Dockerfile, nginx.conf)
corpus/     fetch.py, sources.yaml, MANIFEST.md (no documents)
eval/       golden.yaml (19 questions), run_eval.py, baseline.json, results.json, fixtures/
k8s/        base/, overlays/{dev,prod,ci,incluster}/, components/, and the standalone eval-job, candidate, loader-pod, coverage-job
tests/      architecture tests over rendered manifests and code boundaries; system/ live checks
scripts/    check_submission.py, e2e-kind.sh, smoke.py, chunk-sweep.sh, cache_threshold.py
docs/       CORPUS, PIPELINE, FAILURE-ANALYSIS, ENGINEERING-NOTES, AI-USAGE, ARCHITECTURE,
            adr/0001..0004, evidence/, TRACEABILITY
.github/    workflows/ci.yml (lint, test, manifests, build, scan, e2e-eval), cd.yml
```

## CI/CD

`ci.yml` runs on every pull request to `main` and every push to `dev`: ruff and mypy;
pytest with ≥ 60% coverage on stubs (we are at 96%); `kustomize build | kubeconform
-strict`; image builds (never pushed); Trivy failing on fixable HIGH/CRITICAL; and
**e2e-eval**, which builds a kind cluster, deploys everything, runs the indexer Job on the
fixture corpus with the real embedding and generation models, and enforces the evaluation gate (recall@5
within 5 points of `eval/fixtures/baseline.fixture.json`, every must-abstain question
declined, ≥ 95% citation validity, and no answer repeating the planted instruction in
the fixture's poisoned chunk).

`cd.yml` runs on every push to `main`: test → build and push the three images to Docker
Hub tagged with the commit SHA (`needs: test`) → deploy them to an ephemeral kind cluster
with the real corpus and the real model (`llama3.2:3b` on the runner, ollama-host mode),
wait for `rollout status`, and smoke-test through the Ingress: a cited answer and a declined
absent topic (`needs: build-push`). The first run (41967840446) deployed and served but
failed the smoke test: it still generated with the CI stub, which cannot decline a topic
whose passages clear the relevance floor. The deploy now uses the real model. It deploys by SHA, never `:latest`. It needs the repository secrets
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (an access token, not a password).

`main` is protected: pull request, passing CI and one approval. Work happens on `dev`.
One commit reached `main` before protection existed: `f0f080c`, the planning pack, pushed on
the first day. Every change since then has gone through a reviewed pull request.

## Assignment 03: RAGOps

CS4032 Assignment 03 adds the RAGOps layer (reference paper: Xu et al., 2026) on top of RAHBAR: a verify-and-update
data lifecycle, a three-level offline suite, a release gate, traces and metrics, a coverage check, and a controlled
release, all on Kubernetes. Team: Taimoor Shaukat (24I-3015), Muhammad Bilal Tahir (24I-3166). Report:
`docs/a3-report/report.pdf`. The fresh-cluster order and the object-by-object responsibilities are in
[`k8s/README.md`](k8s/README.md); design and plan in [`docs/a3-ragops/`](docs/a3-ragops/README.md); raw outputs
behind every number and screenshot in [`docs/a3-evidence/`](docs/a3-evidence/host.md). Requirement-by-requirement status, caveats and what only a member can do:
[`docs/a3-ragops/16-RUBRIC-TRACEABILITY.md`](docs/a3-ragops/16-RUBRIC-TRACEABILITY.md).

```bash
make cluster                                   # see k8s/README.md (8 GB minikube, Calico)
make ollama-host                               # runs in the foreground: leave it and use a second terminal
make images && make apply
kubectl apply -f k8s/loader-pod.yaml && kubectl wait --for=condition=Ready pod/ragops-loader -n rahbar --timeout=180s
kubectl exec -n rahbar ragops-loader -- mkdir -p /results/baselines     # the gate reads its baseline from here
kubectl cp eval/results/baseline-live.json rahbar/ragops-loader:/results/baselines/live.json
kubectl -n rahbar wait --for=condition=complete job/ingest --timeout=3600s
```

| Part | Command | Output |
| --- | --- | --- |
| A ingest, verify, update | `scripts/ragops/job.sh sync` | the last log line is the run summary (`chunks_embedded`); `/data/reports/verification/<run>.md` and `.json` on the `ragops-data` volume |
| A Batch B | `python corpus/batch-b/build.py --out /tmp/batch-b-out`, then `kubectl cp /tmp/batch-b-out/batch-b rahbar/ragops-loader:/data/inbox/` (the folder name `batch-b` tags the files as batch B), then `scripts/ragops/job.sh sync` | verification report with a pass or fail and a reason per check; quarantined files under `/data/quarantine/` |
| A counts, restore, delete | `scripts/ragops/job.sh count -- count`, `... restore -- restore <doc>@<ver>`, `... delete -- delete <doc>` | chunk count per document id, orphans, archived and restored versions |
| B suite | `make eval-suite LABEL=baseline` (or `scripts/ragops/eval.sh suite baseline --suite-args "--batches A --repeat 2"`) | `/results/<timestamp>_<label>.json` with a summary table; committed under `eval/results/` |
| B stochasticity | `python -m ragops.suite.stochasticity run1.json run2.json` | per-metric difference between two runs |
| C gate | `make eval-gate LABEL=cand-mxbai` (suite then gate); thresholds in `ragops/config/gate.yaml`, served as ConfigMap `ragops-gate` | `<timestamp>_<label>.decision.json`; the Job fails when the gate fails |
| C candidate and release | `scripts/ragops/job.sh build-index -- build-index --collection rahbar-cand-mxbai --embed-model mxbai-embed-large`, `scripts/ragops/candidate.sh cand-mxbai`, `scripts/ragops/release.sh cand-mxbai`, undo with `kubectl rollout undo deployment/api -n rahbar` | `kubectl rollout status` output; the next trace shows the collection and embedding version |
| D traces | `kubectl exec -n rahbar ragops-loader -- python -m ragops.trace.show <trace_id> --traces /traces --lake /data`; summary: `... python -m ragops.trace.summary --traces /traces` | the exact context and prompt behind an answer; metrics over a window |
| D metrics | `kubectl port-forward -n rahbar deploy/api 8000:8000`, `curl localhost:8000/metrics` | Prometheus text |
| E coverage | `kubectl delete job coverage -n rahbar --ignore-not-found && kubectl apply -f k8s/coverage-job.yaml` | `<timestamp>_coverage.json`; exit 1 below the threshold |
| F | `kubectl get all,pvc,configmap,cronjob,job -n rahbar` | see `k8s/README.md` |

`eval/golden.jsonl` (frozen in the commit `golden: freeze v1`), `eval/pairs.jsonl`, `eval/live_queries.jsonl`, the
Batch B fixtures in `corpus/batch-b/` and the committed result files in `eval/results/` are the data behind the report.
The evaluation endpoint `/api/retrieve` and the `X-Eval-*` headers need the run-time token created by
`scripts/ragops/eval-token.sh`; they are not reachable through the Ingress.

## Documents

| File | What it answers |
| --- | --- |
| `docs/CORPUS.md` | The seven corpus properties, document by document |
| `docs/PIPELINE.md` | Extraction, cleaning, chunking (three measured settings), embedding pin, cache threshold, evaluation method |
| `docs/FAILURE-ANALYSIS.md` | Stages broken on purpose, one at a time, and how each shows up |
| `docs/ENGINEERING-NOTES.md` | The seven engineering questions, with file and line references |
| `docs/adr/` | Indexer as a Job; chunking; cache store; provider and data governance |
| `docs/AI-USAGE.md` | Which AI tools we used, for what, and what we changed |
| `docs/TRACEABILITY.md` | Every requirement in the case study → code → test → evidence |
| other `docs/*.md` (`PRD.md`, `PHASES.md`, `TWO-DEVELOPER-PLAN.md`, ...) | The planning pack written before the build (`f0f080c`), kept as the plan of record. These are not deliverables; their `PENDING` / `TO FILL` cells are planning templates. |
