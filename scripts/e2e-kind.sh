#!/usr/bin/env bash
# Bring the whole stack up on a throwaway kind cluster and wait until it serves.
# Used by ci.yml (e2e-eval) and cd.yml (deploy), and locally:
#
#   scripts/e2e-kind.sh ci                 # fixture corpus, images rahbar-*:ci from local docker
#   PRELOADED=0 scripts/e2e-kind.sh prod   # Docker Hub SHA images (cd.yml)
#
# Needs Ollama on this host listening on the kind network gateway (or 0.0.0.0) with the
# embedding model pulled. Leaves `kubectl port-forward` to the ingress controller on
# localhost:${INGRESS_PORT:-8080}; ask with  -H 'Host: rahbar.local'.
set -euo pipefail
OVERLAY=${1:-ci}
CLUSTER=${CLUSTER:-rahbar-e2e}
TAG=${TAG:-ci}
INGRESS_NGINX=${INGRESS_NGINX:-controller-v1.13.3}
export KUBECONFIG=${KUBECONFIG_E2E:-$HOME/.kube/rahbar-e2e.config}
here=$(cd "$(dirname "$0")/.." && pwd)

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --config "$here/scripts/kind-config.yaml" --wait 180s
fi
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$INGRESS_NGINX/deploy/static/provider/kind/deploy.yaml"
kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=240s

gateway=$(docker network inspect kind --format '{{range .IPAM.Config}}{{.Gateway}} {{end}}' \
          | tr ' ' '\n' | grep -E '^[0-9]+\.' | head -1)
echo "Ollama for the cluster: http://$gateway:11434"
curl -sf "http://$gateway:11434/api/version" >/dev/null || {
  echo "Ollama is not listening on $gateway:11434"; exit 1; }

if [ "${PRELOADED:-1}" = "1" ]; then
  for image in api ui indexer; do kind load docker-image "rahbar-$image:$TAG" --name "$CLUSTER"; done
fi
kustomize build "$here/k8s/overlays/$OVERLAY" | sed "s/OLLAMA_HOST_IP/$gateway/g" | kubectl apply -f -

kubectl wait -n rahbar --for=condition=complete job/indexer --timeout="${INDEX_TIMEOUT:-900s}" || {
  kubectl get pods -n rahbar; kubectl logs -n rahbar job/indexer --all-containers --tail=50; exit 1; }
kubectl logs -n rahbar job/indexer --tail=5
kubectl rollout status -n rahbar deployment/api --timeout=300s
kubectl rollout status -n rahbar deployment/ui --timeout=120s
kubectl get pods,endpoints -n rahbar

kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller "${INGRESS_PORT:-8080}:80" >/tmp/rahbar-port-forward.log 2>&1 &
for _ in $(seq 1 30); do
  curl -sf -H 'Host: rahbar.local' "http://localhost:${INGRESS_PORT:-8080}/" >/dev/null && break; sleep 2
done
echo "stack ready on http://localhost:${INGRESS_PORT:-8080} (Host: rahbar.local)"
