#!/usr/bin/env bash
# Break one pipeline stage at a time on the live stack, measure it, restore it
# (case study 5.5, docs/FAILURE-ANALYSIS.md). Every break is a configuration change, so it
# is reproducible and reversible; outputs go to docs/evidence/failures/.
#
#   scripts/failure-experiments.sh retrieval      # A (OCR off) and B (100/0) re-index; C, E on the API
#   scripts/failure-experiments.sh generation     # F (temperature 1.2), real model, slow
#
# Needs: the stack up (make apply), a completed index, the api on LLM_PROVIDER=stub for
# the retrieval set (recall is a retrieval property), the real provider for F.
set -euo pipefail
NS=rahbar
IP=${INGRESS_IP:-$(minikube ip)}
OUT=docs/evidence/failures
SIZE=${SIZE:-400}
OVERLAP=${OVERLAP:-60}
mkdir -p "$OUT"

reindex() {   # reindex <name> <json patch for the ConfigMap>
  kubectl patch configmap rahbar-config -n $NS --type merge -p "$2"
  local job="fail-$(echo "$1" | tr "[:upper:]" "[:lower:]")-$(date +%s)"   # names are lowercase
  kubectl create job --from=cronjob/reindex "$job" -n $NS
  kubectl wait --for=condition=complete "job/$job" -n $NS --timeout=3600s
  kubectl logs -n $NS "job/$job" -c indexer > "$OUT/$1-indexer.log"
  sleep 8                                   # the API follows the registry every 5 s
}

api_env() {   # api_env KEY=VALUE ... (a rollout; maxUnavailable 0 keeps serving)
  kubectl set env deployment/api -n $NS "$@"
  kubectl rollout status deployment/api -n $NS --timeout=600s
}

evaluate() {  # evaluate <name>
  python eval/run_eval.py --api "http://$IP" --host rahbar.local \
    --out "$OUT/$1-results.json" --baseline /dev/null/none | tee "$OUT/$1-eval.txt" | tail -8 || true
}

case "${1:-retrieval}" in
retrieval)
  api_env LLM_PROVIDER=stub          # recall is a retrieval property: no slow generation
  # B · chunking: 100-token chunks, no overlap
  reindex B-chunk-100-0 '{"data":{"CHUNK_SIZE":"100","CHUNK_OVERLAP":"0"}}'
  evaluate B-chunk-100-0
  # A · extraction: index the scanned PDFs without OCR
  reindex A-no-ocr "{\"data\":{\"CHUNK_SIZE\":\"$SIZE\",\"CHUNK_OVERLAP\":\"$OVERLAP\",\"OCR_ENABLED\":\"false\"}}"
  evaluate A-no-ocr
  # restore A and B: the shipped settings, OCR on (this is the production index)
  reindex restored "{\"data\":{\"CHUNK_SIZE\":\"$SIZE\",\"CHUNK_OVERLAP\":\"$OVERLAP\",\"OCR_ENABLED\":\"true\"}}"
  evaluate restored
  # C · retrieval: top_k 1
  api_env TOP_K=1
  evaluate C-top-k-1
  api_env TOP_K-
  # E · source: no superseded filter
  api_env SUPERSEDED_FILTER=false
  evaluate E-no-superseded-filter
  api_env SUPERSEDED_FILTER-
  ;;
generation)
  # F · generation: temperature 1.2 against 0.2, same questions, real model
  api_env LLM_PROVIDER-              # back to the ConfigMap's ollama-host
  for t in 0.2 1.2; do
    api_env TEMPERATURE=$t REDIS_URL=     # cache off: every repeat must reach the model
    python scripts/repeat_questions.py --api "http://$IP" --runs 2 \
      --out "$OUT/F-temperature-$t.json" | tee "$OUT/F-temperature-$t.txt"
    # the hard cases: two must-abstain questions and the two weakest answers
    python scripts/repeat_questions.py --api "http://$IP" --runs 2 --ids a01,a02,q09,e01 \
      --out "$OUT/F-hard-temperature-$t.json" | tee "$OUT/F-hard-temperature-$t.txt"
  done
  api_env TEMPERATURE- REDIS_URL-
  ;;
esac
