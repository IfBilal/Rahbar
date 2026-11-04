# ADR 0001: The indexer is a Job, and the API only reads

## Status
Accepted · 4 November 2026 · implemented and verified on minikube (see Consequences)

## Context
Two things happen in RAHBAR at very different rates. Indexing (download, OCR, clean,
chunk, embed, write) happens once, and again only when the documents change. Querying
happens on every question. The obvious shortcut, building the index when the API process
starts, ties the slow, rare, memory-hungry thing to the fast, frequent, replicated thing.

With three API replicas and one Chroma volume, indexing on startup breaks in four ways:

1. **Three writers race one volume.** Each replica starts writing the same collection,
   each half-way through a different PDF. What ends up in Chroma is an index that no
   single run produced: duplicated chunks, missing chunks, mixed generations.
2. **Every restart pays the full cost again.** A rolling update, an OOMKill or a node
   drain re-OCRs 34 scanned pages and re-embeds 486 chunks. On our laptop that is 13
   minutes per pod (measured: `"indexer finished", "seconds": 797.9`).
3. **Readiness becomes a lie.** Either a pod says ready before its index exists and serves
   empty retrievals, or it takes 13 minutes to say ready and the startup probe
   (30 × 2 s = 60 s) kills it half-way, so a rollout swaps three working pods for three
   that are still chunking.
4. **Re-indexing needs a redeploy.** New documents would mean a new rollout of the API,
   which is the "configuration change that needs a rebuild" failure.

## Decision
- Indexing runs in a Kubernetes **Job** (`k8s/base/indexer-job.yaml`, `restartPolicy:
  OnFailure`, `backoffLimit: 3`, `activeDeadlineSeconds: 3600`) and weekly in a
  **CronJob** (`k8s/base/reindex-cronjob.yaml`) with the same image, arguments and pod
  template (`concurrencyPolicy: Forbid`, so two writers never overlap). A manual re-index
  is one command with no redeploy:
  `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`.
- The Job's init container downloads the corpus from the committed `corpus/sources.yaml`
  and **fails closed** if the bytes differ from the committed `corpus/MANIFEST.md`, so a
  silently changed web page cannot reach the index without a reviewed commit.
- The API process **only reads** Chroma. Its lifespan (`api/app/main.py`) builds read
  adapters and checks the embedding pin in a background thread; it never calls the
  pipeline. `tests/test_boundaries.py` fails the build if any API module calls a Chroma
  write method or imports the indexer.
- `/readyz` returns 503 until Chroma is reachable, the active collection exists and is
  **non-empty**, its embedding model matches `EMBED_MODEL`, and Redis answers
  (`api/app/routes/health.py`). A pod is withheld from the Service until there is
  something to retrieve.

**What happens to the old index while the API serves from it.** The indexer never
touches the collection the API is reading. Each run writes a new generation
`rahbar-g<timestamp>-<digest>`, checks that it holds every chunk, and only then points the
registry collection `rahbar-registry` at it (one metadata write). The API re-reads that
pointer every 5 s, so all replicas switch at once, with no restart and no window where the
collection is half-written. The previous generation is kept for rollback; older ones are
garbage-collected. A run that dies half-way leaves an unpublished generation that nothing
reads (`indexer/pipeline/store.py`).

## Options considered
- **Index in API startup** (rejected for the four reasons above).
- **An init container on the API Deployment**: still once per replica, still on every
  restart, still three writers.
- **A long-running indexer Deployment** watching for changes: always-on memory for a
  weekly task, and it still needs a lock to stay the only writer. A Job exits.
- **Delete and recreate one collection in place** (the starter's dummy writer does this):
  the API would see a missing or half-filled collection for the whole 13-minute run.

## Consequences
- Easier: re-indexing is routine and safe while serving; the API image never changes for
  new documents; indexing memory (peak 910 Mi in `kubectl top`) is paid by one short-lived
  pod with its own limit, not by three serving pods.
- Harder: the documents must reach the Job (we fetch them at start-up), two collections
  live side by side during a re-index (about 2× disk briefly), and a Job's pod template is
  immutable, so changing it means `kubectl delete job indexer` before re-applying.
- Watch: a re-index changes answers, so the semantic cache must not survive it. The cache
  key includes the generation id, and the API deletes the old generation's entries when it
  sees a new one (ADR 0003); the indexer needs no Redis access.
- Verified: a full Job run (`docs/evidence/indexer-job.txt`), API pods held at 0/1 READY
  until the collection existed, then 3/3 (`docs/evidence/rollout-and-endpoints.txt`).
