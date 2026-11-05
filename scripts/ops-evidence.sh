#!/usr/bin/env bash
# Operational demonstrations from the case study, on the live stack:
#   scripts/ops-evidence.sh pin       > docs/evidence/pin-mismatch.txt          (4.4)
#   scripts/ops-evidence.sh rollout   > docs/evidence/rollout-and-endpoints.txt (4.6)
# Needs rahbar-api:v2 loaded into minikube (built with --build-arg APP_VERSION=v2).
set -uo pipefail
NS=rahbar
IP=${INGRESS_IP:-$(minikube ip)}
run() { echo; echo "\$ $*"; "$@" 2>&1; }

version() {   # the X-Rahbar-Version of whichever pod answers (a 422 is instant: no model call)
  curl -s -o /dev/null -w '%{http_code} %header{x-rahbar-version}' -X POST "http://$IP/api/ask" \
    -H 'Host: rahbar.local' -H 'Content-Type: application/json' -d '{"question":"hi"}'
}

probe_during() {   # request every 0.5 s until the rollout settles; count anything but 422
  local total=0 bad=0 seen=""
  while kubectl rollout status deployment/api -n $NS --timeout=1s >/dev/null 2>&1; [ $? -ne 0 ]; do
    r=$(version); total=$((total + 1))
    [ "${r%% *}" = "422" ] || bad=$((bad + 1))
    case " $seen " in *" ${r#* } "*) ;; *) seen="$seen ${r#* }";; esac
    sleep 0.5
  done
  echo "requests during the rollout: $total, failed (anything but the expected 422): $bad, versions seen:$seen"
}

case "${1:-}" in
pin)
  echo "# 4.4 embedding pin: EMBED_MODEL changed in the ConfigMap, API restarted, index NOT rebuilt ($(date -u +%FT%TZ))"
  run kubectl get pods -n $NS -l app=api
  run kubectl patch configmap rahbar-config -n $NS --type merge -p '{"data":{"EMBED_MODEL":"mxbai-embed-large"}}'
  run kubectl rollout restart deployment/api -n $NS
  run kubectl rollout status deployment/api -n $NS --timeout=90s
  echo "(expected: the rollout does not complete; the new pod never becomes ready)"
  run kubectl get pods -n $NS -l app=api
  new=$(kubectl get pods -n $NS -l app=api --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
  run kubectl logs -n $NS "$new" --tail=20
  echo; echo "\$ kubectl exec -n $NS $new -- python -c 'GET /readyz'"
  kubectl exec -n $NS "$new" -- python -c "
import urllib.request, urllib.error
try: urllib.request.urlopen('http://localhost:8000/readyz', timeout=5)
except urllib.error.HTTPError as e: print(e.code, e.read().decode())"
  run kubectl get endpoints api -n $NS
  echo "(the three old pods keep serving: maxUnavailable 0)"
  echo; echo "## restore the pin"
  run kubectl patch configmap rahbar-config -n $NS --type merge -p '{"data":{"EMBED_MODEL":"nomic-embed-text"}}'
  run kubectl rollout restart deployment/api -n $NS
  run kubectl rollout status deployment/api -n $NS --timeout=600s
  run kubectl get pods -n $NS -l app=api
  ;;
rollout)
  echo "# 4.6 rollout and rollback, zero-downtime check, endpoints ($(date -u +%FT%TZ))"
  run kubectl get deployment api -n $NS -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
  echo "version answering now: $(version)"
  run kubectl set image deployment/api -n $NS api=rahbar-api:v2
  probe_during
  run kubectl rollout status deployment/api -n $NS
  echo "version answering now: $(version)"
  run kubectl rollout history deployment/api -n $NS
  run kubectl rollout undo deployment/api -n $NS
  probe_during
  run kubectl rollout status deployment/api -n $NS
  echo "version answering now: $(version)"
  run kubectl get deployment api -n $NS -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
  echo; echo "## scale to 4: the Service finds the new pod by its label, untouched"
  run kubectl scale deployment api -n $NS --replicas=4
  run kubectl rollout status deployment/api -n $NS --timeout=300s
  run kubectl get endpoints api -n $NS -o wide
  run kubectl get pods -n $NS -l app=api -o wide
  run kubectl scale deployment api -n $NS --replicas=3
  run kubectl get hpa api -n $NS
  ;;
*) echo "usage: $0 pin|rollout"; exit 2 ;;
esac
