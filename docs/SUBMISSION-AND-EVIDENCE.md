> **Status (5 November 2026):** evidence collected under `docs/evidence/`; the release sign-off below is filled in. This guide is kept as the plan of record.

# Submission package, evidence register and demo procedure

Due **2026-11-08 23:59 PKT**, one team entry. Must submit (1) GitHub repository URL (public or instructor access), (2) successful `cd.yml` run link proving test/publish/deploy, (3) Docker Hub SHA-tagged image links, and (4) committed `eval/results.json` and `eval/baseline.json`. Run `python scripts/check_submission.py` from repo root; it is only a mechanical precheck, not grading proof.

**Automatic deductions are severe:** secrets in Git history (-20), real base64 Secret in committed YAML (-15), API-startup indexing (-10), invalid citations (-10), missing abstention (-10), missing PVC/exposed data services (-8), silent embedding drift (-8), missing resource requests/unknown HPA (-6), publishing without `needs:`/using `latest` (-6), default namespace (-5), broken clean-clone apply order (-5), direct main push (-4). Verify every item; record screenshot paths and URLs only once they actually exist.

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-26-release-and-submission-md"></a>

## Submission command center — due 2026-11-08 23:59 PKT


### Required upload / links
Submit **one entry per pair** to Google Classroom:
1. GitHub repository URL (public, or private with both instructors added).
2. Successful `cd.yml` workflow run URL demonstrating test -> publish -> deploy.
3. Docker Hub image pages for API/UI/indexer showing immutable git SHA tags.
4. `eval/results.json` + `eval/baseline.json` **committed** from actual runs.

### Final day run
```bash
make test
make lint
python scripts/check_submission.py
# after actually deployed:
kubectl get pods,sts,deploy,job,cronjob,pvc,svc,ingress,hpa -n rahbar
kubectl get endpoints api -n rahbar
python eval/run_eval.py --api http://<INGRESS_IP> --host rahbar.local
```
Check that all test commands ran in correct environment and outputs were captured. Run README instructions from a **fresh clone**, not the current working tree, to catch hidden local assumptions.

### Documentation audit
- `CORPUS-PLAN.md`: all 7 conditions backed by real source/page/hash proof.
- `PIPELINE-IMPLEMENTATION.md`: OCR/table example, clean rules, 3 chunk experiments and chosen result, vector model/dimension, 2–3 cache thresholds with false-hit rationale.
- `FAILURE-EXPERIMENTS.md`: 4 deliberate experiments with real symptoms, metrics, diagnosis and remedy.
- `ENGINEERING-NOTES-GUIDE.md`: 7 answers, each own code line references and measured evidence, real >1h failure description.
- `AI-ASSISTANCE-PLAYBOOK.md`: genuine tool assistance and human review; attribution.
- `docs/adr/0001`..`0004` present and approved; architecture updated to match implemented code.
- `README.md`: reproducible setup, apply order, source rights, images and eval instructions.

### Deduction guardrail
No secret in **any Git history** (rotate if one entered), no base64 live Secret committed, no API-startup indexing, no citation outside retrieved, no must-abstain false answer, Chroma PVC/StatefulSet and Redis PVC/ClusterIP, pinned model/dimension, CPU requests/HPA data, `needs` on publishing/deploy jobs, SHA tag only, namespace `rahbar`, runnable apply order, no direct main push.

### Release sign-off (fill, not pre-approved)
| Item | Developer A | Developer B | Proof |
|---|---|---|---|
| Real corpus and golden quality | PENDING | PENDING | `docs/CORPUS.md`; `eval/results.json` (recall@5 0.906, citations 100%, abstention 100%) |
| Indexer, provider, safety and cache | PENDING | PENDING | `docs/PIPELINE.md`; `api/tests/test_injection.py`; `docs/evidence/cache-threshold.txt` |
| Cluster, network, probes, rollout | PENDING | PENDING | `docs/evidence/networkpolicy-tests.txt`, `pin-mismatch.txt`, `rollout-and-endpoints.txt`, `chroma-outage-probes.txt` |
| CI/CD and real eval gate | PENDING | PENDING | CI green on `dev`; gate red/green on PR #1 (`docs/evidence/gate-demo.txt`); **cd.yml needs the owner's Docker Hub secrets and a reviewed merge** |
| Clean clone + README + checker | PENDING | PENDING | `docs/evidence/clean-clone.txt`, `docs/evidence/check-submission.txt` |
| Submitted before deadline | PENDING | PENDING | Google Classroom (by the team) |

### Submission data template
`Repository: <URL> | CD run: <URL> | Docker Hub API: <URL> | UI: <URL> | Indexer: <URL> | results commit: <SHA> | baseline commit: <SHA> | submitted timestamp PKT: <actual>`.

---

<a id="merged-docs-27-demo-script-md"></a>

## Assessor demo script — 12–18 minute target, adaptable


**Only run after implementation.** The demo is a proof plan; any result below requires on-screen actual output.

### Opening (1 minute)
Explain why general LLMs may invent university policy, why a document-grounded answer requires version-aware citations and abstention, and why indexing is a separate Job. Introduce developer ownership with one meaningful contribution each.

### Infrastructure (3 minutes, B leads)
Show namespace `rahbar`; 3 API pods and >2 endpoint IPs, nginx UI pod, Chroma StatefulSet/PVC, Redis PVC, one-shot Job and weekly CronJob, HPA, Ingress, deny-default NetworkPolicies. Explain liveness vs readiness and startup probe. Display images tagged SHA, not `latest`.

### Product (3 minutes, A leads)
Ask current-policy question through Ingress; inspect answer + cite + retrieved IDs and source. Ask a version-sensitive question; highlight `doc_version` and `superseded` filter. Ask absent hostel question; show `answered_from_context:false`. Show structured schema and citation guard, not a hardcoded mock.

### Failure controls (3 minutes, split)
B deletes one API pod and re-queries; shows availability. Change only API EMBED_MODEL to deliberately mismatch (on dev), show 0/1 READY and diagnostic; restore correct model. A runs manual CronJob index; demonstrates no API redeploy and stale cache invalidation. Never take down grader's primary environment without rollback plan.

### Quality and delivery (3 minutes, A+B)
A opens golden >=15, recall@3/@5, per-type breakdown and citation/abstention gate; demonstrates 3 chunk choices and false cache-hit threshold. B shows CI intentionally blocked PR and fixed green, CD SHA images, rollback. Show 4 failure-analysis experiments and seven engineering notes with actual line references.

### Finish (1 minute)
Open README clean-clone steps, `make check` output, source hashes and AI attribution; provide final GitHub/Actions/Docker Hub/eval links. If a segment cannot be demonstrated, state it as a gap rather than manufacturing a screenshot.

---

<a id="merged-docs-28-traceability-evidence-md"></a>

## Requirement → code → test → evidence linkage procedure


Every row in `PRD.md` should carry a proof bundle, not merely a filename. Suggested append format:

| Requirement ID | Commit | Code file:line | Test function/command | Actual result & date | Evidence artifact | Reviewer |
|---|---|---|---|---|---|---|
| R06 | `TO FILL` | `indexer/pipeline/store.py:LINE` | `TO FILL` | NOT RUN | `docs/evidence/indexer-job.txt` planned | A/B |
| R13 | `TO FILL` | `api/app/services/answer.py:LINE` | `TO FILL` | NOT RUN | `docs/evidence/ingress-qa.json` planned | A/B |
| R18 | `TO FILL` | `api/app/routes/health.py:LINE` | `TO FILL` | NOT RUN | `docs/evidence/embedding-pin-mismatch.txt` planned | A/B |
| R24 | `TO FILL` | `eval/run_eval.py:LINE` | `TO FILL` | NOT RUN | `eval/results.json` planned | A/B |

### Update workflow
After a PR passes, derive exact lines from the final merge commit (`nl -ba <file> | sed -n ...`); attach command outputs and source SHA. For manual screenshots, capture real UI and link PR/check. When code moves, update line references before final grading. For any `NOT RUN`, record blocker and retest plan. An unchecked traceability row is never a claim of compliance.

### Required evidence index
Branch protection, blocked CI merge, fixed CI merge, API endpoints 3, HPA, resource measurements, negative network connectivity, Rollout + undo, Job and CronJob, cache invalidation, model mismatch, sources/HASH, real golden results and baseline, final checker and CD link. `SUBMISSION-AND-EVIDENCE.md` lists concrete filenames.

---

<a id="merged-docs-evidence-readme-md"></a>

## Evidence vault — real proof only


The grader requires visible proof of both functioning features and operational behaviors. This folder starts as a **capture checklist**, not generated evidence. Never invent screenshots, metrics, hashes, successful logs, GitHub URLs, resource figures or evaluator output.

### Required artifacts and naming
| Evidence | Suggested file | Capture method |
|---|---|---|
| Branch protection (`main`) | `branch-protection.png` | GitHub settings screenshot showing no direct pushes, 1 approval and CI gate |
| CI gate intentionally blocks PR | `eval-gate-blocked.png` | PR showing failing e2e-eval/disabled merge |
| CI gate fixed | `eval-gate-green.png` | same PR after genuine fix |
| 3 API endpoints | `api-endpoints.txt` | `kubectl get endpoints api -n rahbar -o wide` |
| API mismatch readiness | `embedding-pin-mismatch.txt` | `kubectl get pods` + `kubectl logs` naming pins |
| CPU and indexer peak memory | `kubectl-top-pods.txt` | `kubectl top pods -n rahbar` with timestamp; collect while Job active |
| HPA working | `hpa.txt` | `kubectl get hpa -n rahbar` with known target, not `<unknown>` |
| Rollout + rollback | `rollout-rollback.txt` | set image SHA, `rollout status`, `rollout undo`, after-rollback curl |
| NetworkPolicy deny UI->Chroma | `networkpolicy-negative.txt` | exec connection attempt, exit status and allowed positive paths |
| Job and weekly CronJob | `indexer-job.txt` | `kubectl get job,cronjob -n rahbar` + logs |
| Real QA and abstain | `ingress-qa.json` and `ingress-abstain.json` | sanitized curl JSON with `Host: rahbar.local` |
| Evaluation | `../eval/results.json`, `../eval/baseline.json` | actual eval runner output; no manual made-up numbers |
| CI and CD | `ci-run-url.txt`, `cd-run-url.txt` | verified Github Actions URLs/SHAs and statuses |
| Clean clone/reproducibility | `clean-clone.txt` | fresh-directory execution with actual exit codes |
| Submission checker | `submission-checker.txt` | `python scripts/check_submission.py` actual stdout |

### For each evidence file
Include UTC/PKT timestamp, git SHA, OS/cluster version, command or UI source, exit code, and relevant text/picture. Never commit API keys, kubeconfig, private logs, personally identifying screenshots, or external PDFs. The second teammate signs off on accuracy in the final PR.

---

