#!/usr/bin/env bash
# Measure recall@3/@5 for several (CHUNK_SIZE, CHUNK_OVERLAP) settings on the live stack
# (docs/PIPELINE.md, "Chunking"). For each setting: patch the ConfigMap, re-index through
# the CronJob template (no redeploy), wait for the API to follow the new generation, run
# the golden set. Run it with LLM_PROVIDER=stub on the api: recall depends only on what is
# retrieved, and the stub keeps each run to seconds instead of an hour of CPU generation.
#   scripts/chunk-sweep.sh 300:40 400:60 550:80
set -euo pipefail
NS=rahbar
IP=${INGRESS_IP:-$(minikube ip)}
OUT=${OUT:-docs/evidence/chunking}
mkdir -p "$OUT"
for setting in "$@"; do
  size=${setting%%:*}; overlap=${setting##*:}
  echo "== CHUNK_SIZE=$size CHUNK_OVERLAP=$overlap"
  kubectl patch configmap rahbar-config -n $NS --type merge \
    -p "{\"data\":{\"CHUNK_SIZE\":\"$size\",\"CHUNK_OVERLAP\":\"$overlap\"}}"
  job="sweep-$size-$overlap-$(date +%s)"
  kubectl create job --from=cronjob/reindex "$job" -n $NS
  kubectl wait --for=condition=complete "job/$job" -n $NS --timeout=3600s
  kubectl logs -n $NS "job/$job" -c indexer | grep -E '"chunking done"|"indexer finished"' | tee "$OUT/index-$size-$overlap.log"
  sleep 8                                  # the API re-reads the registry every 5 s
  python eval/run_eval.py --api "http://$IP" --host rahbar.local \
    --out "$OUT/results-$size-$overlap.json" --baseline /dev/null/none | tail -8 || true
  # (|| true: with the stub generator the abstention gate fails by design; we want recall)
done
