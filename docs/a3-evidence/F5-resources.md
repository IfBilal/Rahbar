# F5 resources from measurements

Method: `docs/a3-ragops/10-KUBERNETES.md` section 10. Request ~ steady memory and p50 CPU; memory limit ~ peak x 1.3-1.5
(never below x 1.3); CPU limit >= peak; the api CPU request is the HPA denominator and stays > 0.
Numbers are the exact output of `python scripts/ragops/top_summary.py <file>` (CPU in millicores, memory in MiB; steady = median
of the busy samples, peak = maximum). Files: **ING** = `docs/a3-evidence/top-ingest.txt` (first real ingest, 9 documents / 532
chunks, 10 s samples); **EVAL** = `docs/a3-evidence/top-eval-drift.txt` (83-minute evaluation Job over Batch A+B against the live
API, API under load). A2 files: `docs/evidence/kubectl-top-indexer-run.txt`, `docs/evidence/hpa.txt`.

Ollama runs on the host, outside the cluster, so no model memory or CPU appears in any number here.

## Raw script output

```
ING  workload/container  samples peak_cpu steady_cpu peak_Mi steady_Mi
api/api                  282   37    3     71    71
chroma/chroma            94    5     2     43    31
ingest/indexer           92    1377  1219  1206  824
ragops-loader/loader     94    4     2     1     1
redis/redis              94    10    9     7     3
ui/ui                    94    1     1     2     2

EVAL
api-candidate/api        504   4     3     72    69
api/api                  1512  9     3     75    72
chroma/chroma            504   8     2     99    97
eval/eval                493   36    20    30    23
ragops-loader/loader     498   40    14    10    1
redis/redis              504   19    12    9     4
ui/ui                    504   1     1     2     2
```

## Final table

| Workload | Source | Measured peak (CPU m / Mi) | Steady (CPU m / Mi) | Request before | Limit before | Rule | Request now | Limit now |
|---|---|---|---|---|---|---|---|---|
| api | EVAL (+A2 hpa.txt) | 9 / 75 (A2 startup peak 151 / 74) | 3 / 72 | 100m / 96Mi | 500m / 256Mi | mem request ~ steady; CPU request kept (HPA denominator); CPU limit >= 151m | 100m / 80Mi | 500m / 256Mi (kept) |
| chroma | EVAL, ING | 8 / 99 (ING: 5 / 43) | 2 / 97 (ING: 2 / 31) | 25m / 64Mi | 500m / 512Mi | mem request ~ steady, CPU request ~ p50 | 10m / 96Mi | 500m / 512Mi (kept) |
| redis | EVAL | 19 / 9 | 12 / 4 | 20m / 32Mi | 250m / 256Mi | mem request ~ steady with headroom; CPU request ~ p50 to peak | 20m (kept) / 16Mi | 250m / 256Mi (kept) |
| ui | EVAL | 1 / 2 | 1 / 2 | 5m / 16Mi | 100m / 64Mi | already request >= steady | unchanged | unchanged |
| ingest Job (indexer) | ING | 1377 / 1206 | 1219 / 824 | 1 CPU / 1Gi | 2 CPU / 1536Mi | request ~ steady; mem limit = peak x 1.49 (old limit was x 1.27); CPU limit >= peak | 1250m / 896Mi | 2 CPU / 1792Mi |
| eval Job | EVAL | 36 / 30 | 20 / 23 | 250m / 256Mi | 1 CPU / 768Mi | request ~ steady | 50m / 64Mi | 1 CPU / 768Mi (kept) |
| loader (pod) | EVAL, ING | 40 / 10 | 14 / 1 | 10m / 32Mi | 200m / 256Mi | request already covers steady; peak 40m < limit | unchanged | unchanged |
| api-candidate | EVAL (idle) | 4 / 72 | 3 / 69 | 100m / 96Mi | 500m / 256Mi | same image and code as the api, sized like the api | 100m / 80Mi | 500m / 256Mi (kept) |
| coverage Job | none | not measured | not measured | 100m / 128Mi | 500m / 384Mi | none | unchanged | unchanged |

Memory limit / peak: api 3.4x, chroma 5.2x, redis 28x, ui 32x, indexer 1.49x (was 1.27x), eval 25x, loader 25x. None is below x 1.3.

## Per workload

- **api**: the serving window shows 3m / 72Mi steady and 75Mi peak. The CPU request stays 100m: it is the HPA denominator
  (70 percent target) and the A2 startup peak of 151m (`docs/evidence/hpa.txt`) is not in the A3 sample; the 256Mi limit and 500m
  CPU limit from A2 still hold (3.4x peak). Only the memory request moves from 96Mi to 80Mi, closer to the 72Mi steady value.
- **chroma**: steady memory grew from 31Mi (532 vectors, ING) to 97Mi (EVAL, after more ingests and Batch B), so the request
  rises from 64Mi to 96Mi to match what it actually holds; CPU request drops from 25m to 10m (p50 is 2m). The 512Mi limit is
  kept for HNSW growth (5.2x the measured peak).
- **redis**: 4Mi steady and 9Mi peak, so the memory request drops from 32Mi to 16Mi; the 256Mi limit stays because it is sized
  for `maxmemory 200mb` plus an AOF rewrite, which this window did not reach. CPU request 20m stays (peak 19m).
- **ui**: 1m / 2Mi; the current 5m / 16Mi request and 100m / 64Mi limit already hold.
- **ingest Job**: the one workload with real load in ING (OCR on 9 documents). Steady 1219m / 824Mi, peak 1377m / 1206Mi. The old
  1536Mi limit was only x 1.27 the peak and would have been the first thing to OOM on a larger document, so it rises to 1792Mi
  (x 1.49); the request follows the steady values. The CPU limit of 2 stays (>= peak 1377m). The two small init containers
  (50m / 64Mi, 500m / 256Mi) were not separately sampled and keep their values. The CronJob uses the same container and gets the
  same block.
- **eval Job**: honest limitation: the pod measured in EVAL only waits on HTTP calls to the live API (36m / 30Mi peak), not
  model work (the models run on the host Ollama). The request drops to what was measured; the 1 CPU / 768Mi limits are kept
  because no sample exercised anything that could need them.
- **loader**: 40m / 10Mi peak while copying data; the existing 10m / 32Mi request and 200m / 256Mi limit hold. Kept.
- **api-candidate**: same image and code as the api, so it is sized like the api. The EVAL file does contain an api-candidate
  row, but it is an idle pod (4m / 72Mi), not a measurement under load, so it only confirms the api numbers.
- **coverage Job**: no sample exists. Values kept: 100m / 128Mi request, 500m / 384Mi limit, "not measured, small by
  construction".

## Not measured

- coverage Job, the two ingest init containers, api CPU under sustained load beyond A2 (EVAL peak is only 9m), redis near its
  `maxmemory`, the eval Job doing model work, Ollama (host, out of scope).
- Per section 10 step 5, a re-run with the final values to confirm no OOMKilled and no throttling is still to be done when the
  cluster is free.
