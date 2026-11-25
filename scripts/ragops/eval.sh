#!/usr/bin/env bash
# Run the evaluation Job against a target (docs/a3-ragops/10 section 5.3).
#
#   scripts/ragops/eval.sh <mode> <label> [--target URL] [--suite-args "..."] [--baseline FILE] [--candidate FILE]
#     mode: suite | suite+gate | gate
# Examples:
#   scripts/ragops/eval.sh suite baseline --suite-args "--batches A --repeat 2"
#   scripts/ragops/eval.sh suite+gate cand-mxbai --target http://api-candidate:8000
#   scripts/ragops/eval.sh gate cand-minilm --candidate /results/20261126T101010Z_cand-minilm.json
# It rewrites the ConfigMap ragops-eval-target, deletes the previous Job, applies k8s/eval-job.yaml,
# waits for Complete or Failed, prints the logs and exits like the Job (0 pass/done, 1 gate fail, 3 infra).
set -euo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd)
NS=${NS:-rahbar}
mode=${1:?usage: eval.sh <suite|suite+gate|gate> <label> [options]}; label=${2:?label}; shift 2
target="http://api:8000"; sargs="--batches A"; baseline=""; candidate=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target) target=$2; shift 2 ;;
    --suite-args) sargs=$2; shift 2 ;;
    --baseline) baseline=$2; shift 2 ;;
    --candidate) candidate=$2; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
case "$mode" in suite|suite+gate|gate) ;; *) echo "bad mode $mode" >&2; exit 2 ;; esac
kubectl create configmap ragops-eval-target -n "$NS" --dry-run=client -o yaml \
  --from-literal=TARGET_URL="$target" --from-literal=LABEL="$label" --from-literal=MODE="$mode" \
  --from-literal=BASELINE_RESULT="$baseline" --from-literal=CANDIDATE_RESULT="$candidate" \
  --from-literal=SUITE_ARGS="$sargs" \
  --from-literal=GIT_SHA="$(git -C "$here" rev-parse --short HEAD)" | kubectl apply -f - >/dev/null
kubectl delete job eval -n "$NS" --ignore-not-found >/dev/null
kubectl apply -f "$here/k8s/eval-job.yaml" >/dev/null
echo "job/eval started: mode=$mode label=$label target=$target"
# wait for either terminal condition
for _ in $(seq 1 "${EVAL_WAIT_STEPS:-4320}"); do
  s=$(kubectl get job eval -n "$NS" -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null || true)
  case "$s" in
    1/*) kubectl logs -n "$NS" job/eval --tail="${TAIL:-40}"; exit 0 ;;
    */1) kubectl logs -n "$NS" job/eval --tail="${TAIL:-40}"
         last=$(kubectl logs -n "$NS" job/eval --tail=1)      # no pipe into grep -q: SIGPIPE would change the code
         case "$last" in *RESULT=GATE_FAIL*) exit 1 ;; *) exit 3 ;; esac ;;
  esac
  sleep 5
done
echo "timed out waiting for job/eval" >&2; exit 3
