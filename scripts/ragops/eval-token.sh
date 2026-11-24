#!/usr/bin/env bash
# Create the shared secret that guards /api/retrieve and the X-Eval-* headers (idempotent).
# The API pods, the candidate and the eval Job read it from the Secret ragops-eval-token; the value
# is generated here, at run time, and never written to a file or to Git.
set -euo pipefail
NS=${NS:-rahbar}
kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS" >/dev/null
if kubectl get secret ragops-eval-token -n "$NS" >/dev/null 2>&1; then
  echo "secret/ragops-eval-token already exists"
else
  kubectl create secret generic ragops-eval-token -n "$NS" --from-literal=token="$(head -c 24 /dev/urandom | base64 | tr -d '/+=\n')"
fi
