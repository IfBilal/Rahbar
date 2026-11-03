# End-to-end workflow, integration gates, risk and done criteria

This is the **execution control plane** for the pair. A PR is neither complete nor unblocking until the *consumer* verifies its contract at the next gate. Use `G0` → `G8` as go/no-go decisions, log real results in PRs and `docs/evidence/` after you create that directory, and stop if a prerequisite fails. For task-level dependencies see `CRITICAL-PATH.md`, for instructions by phase see `PHASES.md`.

### Non-negotiable definition of verified
Code exists in the expected path; focused tests and applicable `make test`/`make lint` pass; consumer has run the integration command; no secrets/contract drift; relevant metrics/evidence captured and linked; reviewer approves; downstream `Txx` can now proceed. **Do not update a baseline merely to clear a failing quality gate.**

---

<!-- This file consolidates related plans. Any unchecked boxes, MEASURE placeholders or example values require actual implementation and evidence. -->

<a id="merged-docs-16-integration-plan-md"></a>

## Cross-track integration gates and handoffs


Integration is **contract-first** and proceeds in gates. Both developers have to sign off on a gate before using it as a predecessor of a dependent WBS task.

| Gate | Trigger | Producer | Consumer verifies | Pass evidence |
|---|---|---|---|---|
| G0 frozen contracts | T01+T02 | Both | check existing Python signatures and env keys | short review in PR |
| G1 independent setup | T03+T04+T07 | A corpus/golden; B images | A checks /corpus delivery; B checks source manifests readable | checksum and Docker build logs |
| G2 stub cluster | T05+T06 | B | A can reach Chroma Service and invoke dummy Job; stub `/api/ask` through Ingress | pods/services/PVCs+curl |
| G3 secure pathways | T08/T09 and T11/T20 | A chunks; B probes/UI | B proves healthy vs failed /readyz; A views returned UI citations | logs and test outputs |
| G4 real index contract | T10+T12 | A | B confirms Chroma metadata/readiness, API uses same `EMBED_MODEL` | Job+collection dump + mismatch test |
| G5 grounded API contract | T13+T14+T15 | A | B runs API behind Ingress against chosen provider, checks error outputs | sample answer, absent answer, eval CLI |
| G6 CI/CD | T17+T18+T19 | B | A verifies fixture e2e actually indexes fixtures and evaluates retrieval, not just stubs | CI links, SHA image tags |
| G7 verification | T21–T23 | Both | pair reruns golden, rollouts, fault tests | measured results+screenshots |
| G8 release | T24+T25 | Both | clean-clone evaluator perspective | checker, submission links |

### Producer-consumer handoff packet
Every handoff includes `consumer task ID; producer commit; env/URL/path; actual example output; known failure cases; test command; rollback plan`. Post in `TWO-DEVELOPER-PLAN.md` and task PR. Handoff is **accepted** only when the consumer runs at least one integration check.

### Integration smoke sequence (after G4)
1. Check Job Complete and its logs have chunk count >0.
2. Confirm collection metadata `embed_model=EMBED_MODEL`, integer dimension, nonempty count and `superseded` in chunks.
3. `kubectl get endpoints -n rahbar` shows at least 3 ready API endpoints after readiness is wired.
4. Curl `/api/ask` through Ingress with real answerable question; verify each citation occurs in retrieved.
5. Curl absent-topic question; verify `answered_from_context:false`.
6. Trigger manual re-index from CronJob; verify new generation and old cache refusal.
7. Run `eval/run_eval.py` through Ingress; record raw JSON and exit code.
8. Simulate model pin mismatch and confirm 0/1 READY; restore before further tests.

### Blocking condition examples
A may develop `embed.py` before B's cluster exists, but may not mark T10 integrated until Chroma Job works. B may implement CI YAML before A's evaluator, but may not mark e2e working until real fixture indexing + gate report. No other code may be introduced to paper over an unmet gate; report the dependency honestly.

---

<a id="merged-docs-17-risk-register-md"></a>

## Risk register and mitigation priorities


| ID | Risk / early signal | Likelihood / Impact | Owner | Prevention | Contingency |
|---|---|---|---|---|---|
| K01 | 2023 policy URL dead or not same policy revision | high/high | A | verify early; snapshot URL+SHA; compare content | identify another proven revision pair; update golden |
| K02 | scanned PDF OCR quality poor | med/high | A | detect text layer, test OCR at 300dpi, manually compare page | document unrecoverable content honestly; use another scan |
| K03 | 40+ pages OOMs indexer | med/high | A+B | process pages incrementally, batched embeddings, measure `kubectl top` | raise *measured* limits, reduce batch, split document work |
| K04 | host Ollama inaccessible from minikube | high/high | B | test host route with minimal curl and egress early | hosted provider with secret, or documented host fix |
| K05 | Chroma client/server version mismatch | med/high | B | pin both to 1.0.12, smoke heartbeat/query | tested pair update in one PR |
| K06 | NetworkPolicy blocks DNS or Ollama | high/high | B | Calico, port53 TCP/UDP, host CIDR allow | temporary diagnostic policy on dev only; restore least privilege |
| K07 | API indexes on restart or destructive live re-index | low/critical | A | no startup write; staging publish + tests | rollback active generation; disable CronJob |
| K08 | stale semantic cache after re-index | high/high | A | generation-scoped cache, invalidate upon publish | disable cache and rebuild from fresh corpus |
| K09 | model returns malformed JSON / fabricated cite | high/critical | A | schema mode, Pydantic, retry once, citation guard | safe abstention/fallback, log count |
| K10 | false cache hit from low similarity | med/high | A | threshold sweep, zero false hits on test set | raise threshold or disable cache temporarily |
| K11 | CI e2e too heavy or non-deterministic | high/high | B | tiny fixture index and deterministic fixture-only embedding | keep unit/static CI green, diagnose e2e and document |
| K12 | rubric scores unsupported by baseline | high/critical | A | golden created before tuning; record runner outputs | no fabricated baseline; fix implementation/quality |
| K13 | secret leaked to Git, even if later deleted | med/critical | Both | .gitignore, credential scan, Secret via CLI | rotate immediately, 2-line incident disclosure |
| K14 | time lost in shared-file merge conflicts | med/high | Both | ownership map, freeze contract and one editor | pair-rebase and scope freeze |
| K15 | wrong namespace/apply order/hpa unknown | med/high | B | clean-clone test, requests.cpu, metrics-server | follow troubleshooting, reproduce from scratch |

### P0 risk response
Any high/critical risk triggers immediate cross-developer notification with a command/log proving symptom. Choose fallback that preserves assignment core (Chroma/Redis/Job/gate). Never change rubric gates or fabricate evidence to compensate for a blocked component.

### Open issues to close early
Check actual external PDF URLs, provider host connectivity, local hardware (>=6 GB recommended minikube plus host model), Docker Hub access, branch-protection permissions and workflow tokens. Record the result as VERIFIED or BLOCKED, not assumed.

---

<a id="merged-docs-18-definition-of-done-md"></a>

## Definition of Done (DoD) — task, phase and release


### Every task
- [ ] Task ID, owner and blocking dependencies are clear; consumer knows this change exists.
- [ ] Implemented in its allowed files with the public contract unchanged or a reviewed ADR.
- [ ] Tests include normal, boundary and at least one realistic failure scenario.
- [ ] Ruff/mypy/pytest or relevant Docker/kustomize checks actually executed and results copied into PR.
- [ ] No credentials or downloaded prohibited documents in Git; no new P0 regressions.
- [ ] Docs and code comments name real behavior, not optimistic plan claims.
- [ ] Other developer reviewed and a consumer integration smoke passed where relevant.

### Every phase / G gate
- [ ] Specific commands listed in `PHASES.md` executed against correct environment.
- [ ] Generated artifacts appear at documented paths with actual values.
- [ ] At least one negative/failure test completed; any outstanding warning documented.
- [ ] Gate marked VERIFIED with commit SHA, environment and evidence.
- [ ] Next-phase dependency tasks unblocked and owner notified in the task PR handoff section.

### Final release (strict)
- [ ] All mandatory objects in namespace `rahbar` with probes, PVCs, resources, ServiceAccounts, NetworkPolicies, HPA.
- [ ] Live 3-replica API with valid Ingress answer, cited sources, no-answer behavior; tested pod deletion and model mismatch.
- [ ] Real indexer Job, weekly CronJob, model/dimension pin, safe refresh/semantic-cache invalidation.
- [ ] Measured 3 chunk pairs, 2–3 cache thresholds, real recall@3/@5 per type; baseline and results committed.
- [ ] >=15 golden questions in exact mix; citation validity >=95%, must-abstain 100%; CI enforces gates.
- [ ] >=60% test coverage, lint/static, manifest validation, images built, Trivy scan, kind/k3d e2e CI, SHA-only CD deploy.
- [ ] Demonstrated rollback, endpoints count, HPA, security negative test, four failures and observed metrics.
- [ ] Docs/CORPUS, PIPELINE, FAILURE-ANALYSIS, ENGINEERING-NOTES (7 real code-line citations), AI-USAGE (honest) complete.
- [ ] Clean clone README succeeds; `python scripts/check_submission.py` clean; no secret anywhere in history.
- [ ] Final repo/CD/Docker Hub/eval links submitted by 2026-11-08 23:59 PKT.

**Do not mark checked from intent or source inspection.** The README initially says implementation pending until genuinely complete.

---

