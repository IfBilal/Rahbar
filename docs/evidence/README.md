# Evidence

Every file here was produced by running the system (minikube with Calico on Ubuntu 24.04,
Ollama on the host, 4–5 November 2026) or by GitHub Actions. None is hand-written. Most
carry the command that produced them and a UTC timestamp.

| File | Proves | Produced by |
| --- | --- | --- |
| `corpus-pdffonts-and-pages.txt` | 9 documents, 279 pages, the two scans, 9/9 SHA-256 matches | `pdfinfo`, `pdffonts`, `corpus/fetch.py --verify` |
| `extraction-before-after.txt` | mangled table and off-page text, before and after our extractor | `extract.py::page_text` vs plain pdfplumber |
| `kubectl-top-indexer-run.txt` | indexer peak memory 910 Mi (limit 1536 Mi) | `kubectl top pods` every 10 s during a full index |
| `hpa.txt` | HPA reads a value (3%/70%) and API CPU stays ~3m while generations are in flight. The first 4 of 110 samples show `<unknown>/70%`: they were taken during a rollout, before metrics-server had a sample from the new pods (`ENGINEERING-NOTES.md`, note 3) | `kubectl top` + `kubectl get hpa` every 15 s during the evaluation |
| `networkpolicy-tests.txt` | ui → chroma and ui → redis denied, api → chroma/redis allowed, ui → api allowed, DNS works | `kubectl exec` connections from inside the pods |
| `pin-mismatch.txt` | changed `EMBED_MODEL`: new pod 0/1 READY, 503 naming the pin, conflict logged, old pods serving | `scripts/ops-evidence.sh pin` |
| `rollout-and-endpoints.txt` | set image → rollout status → undo with 0 failed requests; 4 endpoints after scaling | `scripts/ops-evidence.sh rollout` |
| `chroma-outage-probes.txt` | Chroma gone 90 s: shipped probes vs swapped probes | `scripts/probe-experiment.sh` |
| `system-tests.txt` | live checks: ingress, abstention, endpoints, policy, pod deletion, pin | `make system-test` |
| `metrics.txt`, `api-request-log.txt` | `/metrics` series and one JSON log line per request | `curl /metrics`, `kubectl logs` |
| `ingress-qa.json`, `ingress-abstain.json` | a grounded cited answer and a declined absent-topic answer through the Ingress | `curl -H 'Host: rahbar.local'` |
| `ui-screenshot.png` | the chat UI answering and declining through the Ingress | `scripts/screenshot.py` |
| `cache-invalidation.txt` | after a re-index the old generation's cache keys are deleted and the next answer is regenerated | live `curl` + `redis-cli --scan` |
| `indexer-job.txt` | Job + CronJob; a manual re-index from the CronJob while the same API pods keep serving | `kubectl create job --from=cronjob/reindex` |
| `cache-threshold.txt` (+ `-before-lowercase-fix`) | cache threshold 0.95 chosen with data; the casing bug | `scripts/cache_threshold.py` |
| `retrieval-scores-400-60.txt` | best similarity per golden question (relevance floor) | live API, stub generator |
| `chunking/` | three chunk settings measured (+ the pre-fix run) | `scripts/chunk-sweep.sh` |
| `exact-assist-off-results.json` | exact-term recall 0.5 without the `$contains` assist | `EXACT_TERM_ASSIST=false` |
| `failures/` | five stages broken and restored (A, B, C, E, F) | `scripts/failure-experiments.sh` |
| `eval-run1-…`, `eval-run2-cache-hits.json`, `eval-run3-…` | the evaluation runs before the shipped one (`eval/results.json`) | `eval/run_eval.py` |
| `gate-demo.txt`, `eval-gate-red.png`, `eval-gate-green.png` | the CI eval gate failing on PR #1, then passing after the fix | GitHub Actions runs 41891435694 and 41892555788; screenshots captured 5 November 2026 |
| `ci-runs.txt` | CI run URLs per commit | `gh run list` |
| `ollama-incluster.txt` | bonus: Ollama Deployment + PVC in the cluster; answers and declines through the Ingress, a 532-chunk re-index through it, and weights surviving a pod restart | `kubectl apply -k k8s/overlays/incluster`, `scripts/smoke.py` |
| `cd-run.txt` | successful branch deployment with real model, covered answer and abstention | GitHub Actions run 41969926861 |
| `cd-main.txt` | successful main-branch publication, deployment and Ingress smoke test | GitHub Actions run 41972097173 |
| `branch-protection.json`, `branch-protection.png` | required approvals, status checks and administrator enforcement | GitHub branch protection API and settings page, 5 November 2026 |
| `check-submission.txt` | the starter's checker output on the final tree | `python scripts/check_submission.py` |
| `clean-clone.txt` | README path from a fresh clone to an answered question | the README commands, in a new directory |
| `clean-clone-final.txt` | the same README path on the final `main` (137a97a): 313 tests, 532 chunks, a cited answer and a decline through the Ingress, all 7 live system tests (pin test included), turns stored in Redis, HPA at 6%/70% | the README commands, in a new directory |
| `empty-index-readiness.txt` | with no index at all, the API pods stay 0/1 READY (503 naming the missing collection, no endpoints) until the indexer Job publishes; then 3 endpoints and answers | `kubectl apply -k k8s/overlays/dev` after wiping the namespace and the provisioner's data directory |

The branch-protection settings are recorded in `branch-protection.json` and
`branch-protection.png`. The successful main-branch CD run and Docker Hub links are
recorded in `cd-main.txt`.

The PR #1 red and green screenshots show the actual CI run pages; its historical merge
button was not captured. `merge-blocked.png` captures PR #8 with the required e2e-eval
check failing and merging blocked. It also shows that the branch was behind and required
a review, which were additional blockers at the time. `merge-green.png` captures PR #8
after the floor was restored and all six checks passed; review was still required.
