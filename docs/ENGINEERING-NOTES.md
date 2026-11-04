# Engineering notes

Every answer points at our own files and lines, and every number comes from a run on our
stack (evidence under `docs/evidence/`).

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

**The failure:** three concurrent writers on one index. `k8s/base/api.yaml:9` runs
`replicas: 3`, and Chroma has exactly one volume (`k8s/base/chroma-statefulset.yaml:55`,
`volumeClaimTemplates`, one replica). If indexing ran in the API's lifespan, the three pods
would start together, each downloading the corpus, OCRing 34 pages and writing 486 chunks
into the same collection at the same time. Each would be half-way through a different PDF,
and the result would be an index that no single run produced: duplicate ids overwritten
mid-batch, counts that never settle, one pod's `delete_collection` pulling the floor from
under another. It gets worse from there. Every restart re-pays the full 13 minutes (our Job
log: `"indexer finished", "seconds": 797.9`), and that is far beyond the startup probe's 60 s
(`k8s/base/api.yaml:43-46`, 30 × 2 s). So a rollout would kill pods half-way through
indexing, forever. Re-indexing would also need a redeploy.

**The object that prevents it:** the indexer is a **Job** (`k8s/base/indexer-job.yaml:4`,
`kind: Job`, `restartPolicy: OnFailure` at line 16, `backoffLimit: 3` at line 10), and the
weekly **CronJob** shares its pod template with `concurrencyPolicy: Forbid`
(`k8s/base/reindex-cronjob.yaml:11`), so there is exactly one writer at a time. The API side
cannot write: its lifespan (`api/app/main.py:32-54`) only builds read adapters, and
`tests/test_boundaries.py::test_the_api_never_writes_to_chroma` fails the build if an API
module calls a Chroma write method. The writer itself never mutates the collection being
served. It builds a new generation and flips the registry pointer
(`indexer/pipeline/store.py:81-88`), so the three readers switch together.

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

As built, liveness asks only "is the process alive" (`api/app/routes/health.py:24`,
`/healthz` returns a constant) and readiness asks about dependencies (`health.py:29-58`).
Measured on our cluster with Chroma made unavailable for 90 s
(`docs/evidence/chroma-outage-probes.txt`): @@MEASURE: as-built outcome@@.

**Swapped** (liveness on `/readyz`, readiness on `/healthz`), the same 90 s does this. The
liveness probe (`k8s/base/api.yaml:47-50`: every 20 s, failureThreshold 3) fails on all
three pods at once, because they share the one Chroma. After 3 × 20 s = 60 s, the kubelet
kills and restarts **all three** containers. Meanwhile the swapped readiness probe still
says "ready", so the Service keeps routing questions to pods that cannot retrieve and are
about to be killed. The restarted pods need Chroma to pass liveness, Chroma is still slow,
so they are killed again: CrashLoopBackOff with growing back-off. When Chroma recovers at
90 s, the pods are sitting in back-off (10 s, 20 s, 40 s, ...), so the outage outlives its
cause. Measured: @@MEASURE: swapped outcome@@. A dependency that was only slow becomes a
cluster-wide restart storm, which is why `/healthz` must never touch Chroma, Redis or the
LLM.

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

The HPA (`k8s/base/hpa.yaml:11-17`, 3–8 replicas, 70% of `requests.cpu`) divides the
api containers' CPU by their 100m request (`k8s/base/api.yaml:60`). While a question is
being answered, an api pod spends almost all its time **waiting**: on the Ollama host for
generation (one to four minutes per answer on our laptop CPU), and briefly on Chroma and
the embedder. Generation burns the *host's* CPU, not the pod's. The pod's own CPU is JSON
parsing, a cosine scan and a prompt string. Measured while the 19-question evaluation ran against
the real model (`docs/evidence/hpa.txt`, sampled every 15 s): each api pod used **3m CPU
and about 70 Mi** with a question in flight, and the HPA read **`cpu: 3%/70%`** the whole
time. One request takes one to four minutes, and the HPA saw a service at rest. (Right after
a rollout it briefly showed `<unknown>/70%` until metrics-server had a sample from every
new pod.) So the HPA measures how
busy Python is between waits. It reads near-idle precisely when the service is saturated:
every worker thread blocked on the model, requests queueing, latency climbing. It will
scale on a burst of cheap cache hits, and not on a queue of expensive generations.

The signal that should scale a generation service is **concurrency and latency of work
in flight**: requests currently waiting on generation per pod (or queue depth), and p95
of `rahbar_generation_seconds` / `rahbar_request_seconds`. To use it we would need:
1. An in-flight gauge (`rahbar_inflight_generations`, incremented around
   `answer.py:130 generate_checked`); the latency histograms already exist
   (`api/app/routes/metrics.py`).
2. Prometheus scraping `/metrics`, plus the Prometheus Adapter (or KEDA) to expose that
   gauge through the custom metrics API.
3. An HPA with a `type: Pods` metric, for example average in-flight generations per pod
   = 2, instead of CPU.
And, honestly, scaling the API only helps if the model scales too. With one Ollama on one
laptop, more API pods just queue at the same model; the bottleneck is the generator's
capacity. That is an argument for ollama-incluster with GPU nodes, or a hosted provider.

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

`kubectl top pods`, sampled every 10 s across a full index of the real corpus
(`docs/evidence/kubectl-top-indexer-run.txt`): peak **910 Mi**, during OCR of the scanned
PDFs (pdf2image holds a 300 dpi page bitmap, then Tesseract runs on it) and while
pdfplumber parses the 85-page annual report. Steady embedding sat at about 460 Mi. Limit:
**1536 Mi** (`k8s/base/indexer-job.yaml:70`, same in the CronJob), request 512 Mi (line 69).
Margin: 1536 − 910 = **626 Mi, about 41% above the measured peak**. We keep that margin
because peak memory grows with the largest page we OCR and the largest PDF we parse, and
the website can publish a bigger one. Compare the serving pods: about 72 Mi each, limit
384 Mi (`k8s/base/api.yaml:60-61`). Indexing is the memory-hungry path, which is one more
reason it is not in the API.

Set the limit wrong (below 910 Mi) and the kernel's OOM killer ends the container: exit
code **137** (128 + SIGKILL 9), reason `OOMKilled` in `kubectl describe pod`. The Job
retries up to `backoffLimit: 3` and then reports `Failed`; with the same data it fails the
same way every time. The registry pointer only moves after a complete write
(`store.py:72-76`), so a killed indexer never publishes a partial index.

## 5. recall@5 by question type: where is it worst, and why?

Shipped index (300/40), 19 golden questions, through the Ingress
(`docs/evidence/failures/restored-results.json`; the exact-assist-off run is
`docs/evidence/exact-assist-off-results.json`):

| Question type | n | recall@3 | recall@5 | recall@5 with the exact-term assist off |
| --- | ---: | ---: | ---: | ---: |
| version | 3 | 1.000 | 1.000 | 1.000 |
| injection | 1 | 1.000 | 1.000 | 1.000 |
| ordinary | 9 | 0.889 | 0.889 | 0.889 |
| **exact** | 3 | **0.833** | **0.833** | **0.500** |
| overall (answerable) | 16 | 0.906 | 0.906 | 0.844 |

**Worst: exact terms.** Without help they are the worst by far (0.500). e01, "What does
clause 1.21 of the academic rules require?", does not retrieve clause 1.21 at all. An
embedding encodes meaning, and "1.21" carries almost none: as a token sequence it is about
as close to "1.12" or "2.11" as to itself, and the query is dominated by "academic rules
require", which matches dozens of clauses equally well. Fees and table cells blur the same
way. e02 (paper rechecking fee, Rs. 500) ranks the handbook's *clause about* rechecking fees
above the fee table that states the amount. e03 (B- = 2.67) finds the handbook's grade table
but not the grading page's. Our remaining ordinary miss is also a table: q09 asks for one
cell (Islamabad, total faculty: 236) of a numeric grid that embeds as a bag of numbers.

**The technique that addresses it** is lexical matching alongside dense retrieval:
**hybrid retrieval** (BM25 or keyword search fused with the vector ranking), so a query
containing "1.21" gets the chunk that literally contains "1.21". We implemented the
cheapest form: `api/app/retrieval/chroma.py` extracts clause numbers and course codes
(`_EXACT`, line 34) and asks Chroma for chunks that `$contains` them, ranked first
(`retrieve`, lines 151–155). That alone moved exact-term recall@5 from 0.500 to 0.833. A
full BM25 leg would also catch fee names and table labels ("Paper Rechecking Fee"), which
our regex does not look for. Metadata helps too: indexing table rows with their header
cells, so "Islamabad | ... | 236" is embedded as "Islamabad total faculty 236".

## 6. EMBED_MODEL changed on the API only: what does your system do?

The indexer recorded the model in the collection metadata when it built the index
(`indexer/pipeline/store.py:63-66`: `embed_model`, `dimension`; repeated on the registry at
lines 86-88). The API compares that with its own `EMBED_MODEL` in two places:
- at startup, in a background thread (`api/app/main.py:48`, `_check_pin_at_startup` at
  lines 57-68), which logs `embedding model mismatch: refusing readiness` with both
  model names;
- on every readiness probe (`api/app/routes/health.py:43`, via `pin_problem` in
  `api/app/retrieval/chroma.py:58`), which returns **503** with the conflict, so the pod
  stays **0/1 READY** and never joins the Service. The same check runs per query
  (`chroma.py:141-143`), including the vector dimension.

Because the rollout is `maxUnavailable: 0` (`k8s/base/api.yaml:13`), the three old,
correct pods keep serving while the new pods sit unready, and the rollout stalls instead of
completing. Demonstrated on the cluster (`docs/evidence/pin-mismatch.txt`):
@@MEASURE: pin demo summary@@.

**Without the guardrail** nothing would error. The API would embed questions with the new
model and compare them against vectors from the old one. Two models' spaces are not
aligned, so cosine scores would be noise. If the dimensions happened to match, every query
would "work", return the wrong five passages with plausible scores, and the generator
would answer confidently from irrelevant text or abstain at random. Our own bug showed what
silent drift looks like: when only the *casing* differed between what was indexed and what
was asked, nothing failed, recall just quietly dropped (note 7).

## 7. The failure that cost us more than an hour

**Symptoms.** With the real corpus indexed, recall@5 was 0.72, and the misses had a
pattern: "Which students are placed on the **Rector's** List of Honors?" retrieved the
Foreword (the Rector's welcome letter), not clause 7.3; "How many faculty members did the
**Islamabad** campus have?" retrieved the Peshawar campus page; the fee-table question
missed the fee table.

**What we wrongly believed first.** That this was the known weakness of dense
retrieval: embeddings blur proper nouns and table cells, so a lexical (BM25) leg would fix
it. We checked the usual suspects for stages A and B. Was the faculty table split across
chunks? No: `docs/evidence/extraction-before-after.txt` shows clean rows inside one chunk.
Was the "Rector's List of Honors" heading detected? Yes. Was our golden label wrong? We
re-read the handbook; it was right. Believing the embeddings were merely weak, we went on
building on them: we tuned the relevance floor on those scores and recorded 0.72 as our
recall.

**What told us the truth.** A different experiment. Tuning the cache threshold
(`scripts/cache_threshold.py`) printed:

```text
1.0000  near-miss   What is the tuition fee per credit hour for BS?  |  ... for MS?
1.0000  near-miss   Which students are placed on the Rector's List of Honors?  |  ... Dean's List ...
```

Two different questions with a cosine of exactly 1.0000 cannot be a chunking problem. The
command that settled it was a direct call to the embedder:

```bash
curl -s localhost:11434/api/embed -d '{"model":"nomic-embed-text","input":["Rector"]}'
curl -s localhost:11434/api/embed -d '{"model":"nomic-embed-text","input":["Dean"]}'
# identical vectors; "rector" vs "dean" in lower case: cosine 0.66
```

nomic-embed-text uses an **uncased** BERT vocabulary, and Ollama 0.17 passes text to it
without lowercasing, so every capitalised word (Rector, Dean, Islamabad, Lahore, BS, MS,
most headings) became the same `[UNK]` token. The embedding silently ignored exactly the
words that distinguish our questions. The fix is two lines, lowercasing on both sides
as part of the pin (`indexer/pipeline/embed.py:23`, `api/app/retrieval/embedder.py:21`).
**What it cost** was everything we had built on the broken vectors. The relevance floor,
the cache threshold and the recall numbers were all invalid. We re-indexed the corpus for
each of the three chunk settings (about 75 minutes of indexing on the laptop CPU) and
measured everything again. recall@5 at 400/60 went from **0.719 to 0.906**, exact terms
from 0.50 to 0.83, and the cache threshold that had no safe value now has one (0.95). The
lesson is written into the code: the pin is not just a model name. Prefix and casing must
match too, and
`tests/test_boundaries.py::test_both_sides_prepare_text_identically_for_the_pinned_model`
now enforces it.

(A shorter one, for completeness: Chroma crash-looped on its first deployment with
`invalid type: found string "tcp://10.96.96.97:8000", expected u16 for key "PORT"`.
Kubernetes injects `CHROMA_PORT=tcp://...` for a Service named `chroma`, and Chroma reads
any `CHROMA_*` variable as its own configuration. `kubectl logs chroma-0 --previous`
showed it in one line; `enableServiceLinks: false` fixed it.)
