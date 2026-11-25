#!/usr/bin/env bash
# Prove a rolling release drops no requests (docs/a3-ragops/07 section 8, F3-02).
#   scripts/ragops/rollout-probe.sh start     # an in-cluster pod GETs the Service api every 0.5 s
#   ... run the release / kubectl rollout status ...
#   scripts/ragops/rollout-probe.sh stop      # prints how many requests got each status code
# It runs inside the cluster, because a `kubectl port-forward` to a Service pins one pod and would break
# the moment that pod is replaced. The pod carries the label app=ragops-eval, the one NetworkPolicy allows
# to reach the API. It asks /readyz (cheap, and it is the endpoint the Service's readiness is built on).
set -euo pipefail
NS=${NS:-rahbar}; TAG=${TAG:-dev}
case "${1:-}" in
  start)
    kubectl delete pod rollout-probe -n "$NS" --ignore-not-found >/dev/null
    kubectl run rollout-probe -n "$NS" --restart=Never --image="rahbar-ragops:$TAG" --image-pull-policy=IfNotPresent \
      --labels=app=ragops-eval --command -- python -u -c '
import time, urllib.request, urllib.error
while True:
    t = time.strftime("%H:%M:%S")
    try:
        code = urllib.request.urlopen("http://api:8000/readyz", timeout=3).status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        code = type(e).__name__
    print(t, code, flush=True)
    time.sleep(0.5)' >/dev/null
    kubectl wait --for=condition=Ready pod/rollout-probe -n "$NS" --timeout=60s >/dev/null
    echo "probe running" ;;
  stop)
    kubectl logs -n "$NS" rollout-probe > /tmp/rollout-probe.log
    kubectl delete pod rollout-probe -n "$NS" --wait=false >/dev/null
    echo "requests by status:"; awk '{print $2}' /tmp/rollout-probe.log | sort | uniq -c
    echo "first: $(head -1 /tmp/rollout-probe.log)"; echo "last:  $(tail -1 /tmp/rollout-probe.log)"
    grep -v " 200$" /tmp/rollout-probe.log | head -5 | sed 's/^/non-200: /' || true ;;
  *) echo "usage: rollout-probe.sh start|stop" >&2; exit 2 ;;
esac
