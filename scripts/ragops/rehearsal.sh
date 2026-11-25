#!/usr/bin/env bash
# Clean-cluster rehearsal (T58): from a fresh clone and a wiped minikube to a working pipeline, using only the
# commands of README.md and k8s/README.md, with a timestamp per step. Output goes to stdout: run it through scripts/ragops/capture.sh to keep it.
#   scripts/ragops/rehearsal.sh [source-repo-dir]
# DESTRUCTIVE for the local cluster: it runs `minikube delete`. Results and traces already copied into the repository
# are unaffected. Needs Ollama with the models pulled (llama3.2:3b, nomic-embed-text, ...).
set -uo pipefail
SRC=${1:-$(cd "$(dirname "$0")/../.." && pwd)}
DIR=${REHEARSAL_DIR:-$HOME/rahbar-rehearsal}
START=$(date +%s)
ts() { printf '\n######## [+%4ds] %s (%s UTC)\n' "$(( $(date +%s) - START ))" "$*" "$(date -u +%H:%M:%S)"; }
export KUBECONFIG=$HOME/.kube/config

ts "0. a fresh clone of $(git -C "$SRC" rev-parse --short HEAD) into $DIR"
rm -rf "$DIR"; git clone -q "$SRC" "$DIR" && cd "$DIR" && git log --oneline -1
ts "1. make install"; make install >/tmp/rehearsal-install.log 2>&1; tail -2 /tmp/rehearsal-install.log
ts "2. make test (no cluster, no model, no network)"; make test 2>&1 | grep -E "passed|failed|skipped" | tail -6
ts "3. wipe: minikube delete"; minikube delete 2>&1 | tail -1
ts "4. make cluster (minikube + Calico + metrics-server + ingress)"
make cluster 2>&1 | tail -4 || true
kubectl wait --for=condition=Ready node/minikube --timeout=300s 2>&1 | tail -1
ts "5. Ollama on the minikube gateway (README step 2)"
pid=$(ss -ltnp 2>/dev/null | awk '/192.168.49.1:11434/ {match($0,/pid=[0-9]+/); print substr($0,RSTART+4,RLENGTH-4)}' | head -1)
[ -n "$pid" ] && kill "$pid" 2>/dev/null; sleep 2
OLLAMA_HOST=192.168.49.1:11434 OLLAMA_MODELS=${OLLAMA_MODELS:-/usr/share/ollama/.ollama/models} OLLAMA_KEEP_ALIVE=30m nohup ollama serve >/tmp/rehearsal-ollama.log 2>&1 &
sleep 5; curl -s -m 5 192.168.49.1:11434/api/version; echo
ts "6. make images (real Dockerfiles: api, indexer, ui, ragops)"; make images 2>&1 | grep -E "^#.*(naming|DONE)|error|Error|ERROR" | tail -6; docker images --format '{{.Repository}}:{{.Tag}}' | grep -c '^rahbar-.*:dev'
ts "7. make apply (token Secret + kubectl apply -k k8s/overlays/dev)"; make apply 2>&1 | grep -E "created|Error|error" | tail -12
ts "8. wait for the first ingestion Job (seed from the committed sources, verify, index)"
kubectl wait --for=condition=complete job/ingest -n rahbar --timeout=3600s 2>&1 | tail -1
kubectl logs -n rahbar job/ingest -c indexer --tail=1 | cut -c1-420
ts "9. rollout status deployment/api"; kubectl rollout status deployment/api -n rahbar --timeout=600s 2>&1 | tail -1
ts "10. ask a question and a decline (port-forward to the Service: the Ingress controller image may still be downloading)"
kubectl -n rahbar port-forward svc/api 8003:8000 >/dev/null 2>&1 & PF=$!; sleep 4
for q in "What is the deadline to withdraw from a course?" "What is the monthly hostel fee?"; do
  curl -s -m 600 -X POST localhost:8003/api/ask -H 'content-type: application/json' -d "{\"question\":\"$q\"}" | python3 -c "
import sys,json; d=json.load(sys.stdin); print('Q:', '$q'); print('  answered_from_context:', d['answered_from_context'], '| release', d.get('release_id'), '|', d['answer'][:140])"
done; kill $PF 2>/dev/null
ts "11. the loader pod, then the baseline back onto the results volume and a reduced evaluation Job (make eval-demo)"
kubectl apply -f k8s/loader-pod.yaml >/dev/null; kubectl wait --for=condition=Ready pod/ragops-loader -n rahbar --timeout=180s | tail -1
kubectl exec -n rahbar ragops-loader -- mkdir -p /results/baselines
kubectl cp "$SRC/eval/results/baseline-live.json" rahbar/ragops-loader:/results/baselines/live.json
make eval-demo 2>&1 | tail -22 | cut -c1-200
ts "12. namespace overview"; kubectl get all,pvc,configmap,cronjob,job -n rahbar 2>&1 | head -50
ts "DONE: $(( $(date +%s) - START )) seconds from a fresh clone to a working pipeline"
