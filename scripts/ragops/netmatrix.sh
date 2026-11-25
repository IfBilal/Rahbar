#!/usr/bin/env bash
# Prove the NetworkPolicies with real connection attempts (docs/a3-ragops/10 section 7).
#   scripts/ragops/netmatrix.sh
# Short-lived pods carrying the labels of the workloads under test try TCP connects (3 s timeout) and
# print allowed or DENIED. Expected: the evaluation pod reaches api and api-candidate (8000) and Ollama
# (11434) but NOT chroma (8000) or redis (6379); the candidate reaches chroma but NOT redis; the UI cannot reach
# chroma (A2 rule, still holding); the API reaches chroma and redis.
set -uo pipefail
NS=${NS:-rahbar}; TAG=${TAG:-dev}
OLLAMA_HOST_IP=${OLLAMA_HOST_IP:-192.168.49.1}
probe() {   # probe <label> <name> host:port ...
  local label=$1 name=$2; shift 2
  local targets="$*"
  kubectl delete pod "nm-$name" -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run "nm-$name" -n "$NS" --restart=Never --image="rahbar-ragops:$TAG" --image-pull-policy=IfNotPresent \
    --labels="app=$label" --command -- python -u -c '
import socket, sys
for t in sys.argv[1:]:
    h, p = t.rsplit(":", 1)
    try:
        socket.create_connection((h, int(p)), timeout=3).close(); print(f"{t:28s} allowed")
    except Exception as e:
        print(f"{t:28s} DENIED ({type(e).__name__})")' $targets >/dev/null
  for _ in $(seq 1 40); do
    phase=$(kubectl get pod "nm-$name" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
    case "$phase" in Succeeded|Failed) break ;; esac; sleep 2
  done
  echo "--- from a pod labelled app=$label"; kubectl logs "nm-$name" -n "$NS"
  kubectl delete pod "nm-$name" -n "$NS" --wait=false >/dev/null 2>&1
}
probe ragops-eval eval api:8000 api-candidate:8000 "$OLLAMA_HOST_IP:11434" chroma:8000 redis:6379 ui:8080
probe api-candidate candidate chroma:8000 redis:6379 "$OLLAMA_HOST_IP:11434" api:8000
probe ui ui chroma:8000 redis:6379 api:8000
probe api api chroma:8000 redis:6379 "$OLLAMA_HOST_IP:11434"
probe ragops-loader loader api:8000 chroma:8000 redis:6379 "$OLLAMA_HOST_IP:11434"
