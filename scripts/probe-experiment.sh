#!/usr/bin/env bash
# Engineering note 2, measured: Chroma unavailable for 90 s, with the probes as built and
# then with liveness and readiness swapped. Chroma is "slowed" by scaling its StatefulSet to
# 0 (its PVC stays, so the index comes back with it). Samples api READY, RESTARTS and the
# Service's endpoints every 10 s.   scripts/probe-experiment.sh > docs/evidence/chroma-outage-probes.txt
set -uo pipefail
NS=rahbar

sample() {   # sample <label> <seconds>
  local end=$((SECONDS + $2))
  while [ $SECONDS -lt $end ]; do
    local eps
    eps=$(kubectl get endpoints api -n $NS -o jsonpath='{.subsets[*].addresses[*].ip}' | wc -w)
    printf '%s  %-14s endpoints=%s  ' "$(date -u +%T)" "$1" "$eps"
    kubectl get pods -n $NS -l app=api --no-headers \
      -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,STATE:.status.containerStatuses[0].state \
      | awk '{printf "[%s ready=%s restarts=%s] ", substr($1,length($1)-4), $2, $3}'
    echo
    sleep 10
  done
}

outage() {   # outage <label>: 90 s without Chroma, then 120 s of recovery
  echo "== $1: scale chroma to 0 at $(date -u +%T)"
  kubectl scale statefulset chroma -n $NS --replicas=0 >/dev/null
  sample "$1:outage" 90
  echo "== $1: chroma back at $(date -u +%T)"
  kubectl scale statefulset chroma -n $NS --replicas=1 >/dev/null
  sample "$1:recovery" 150
}

echo "# Chroma unavailable for 90 s ($(date -u +%FT%TZ)); api has 3 replicas"
kubectl get deployment api -n $NS -o jsonpath='{range .spec.template.spec.containers[0]}liveness={.livenessProbe.httpGet.path} readiness={.readinessProbe.httpGet.path}{"\n"}{end}'
sample "before" 20
outage "as-built"

echo
echo "## SWAPPED: liveness -> /readyz, readiness -> /healthz"
kubectl patch deployment api -n $NS --type json -p '[
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/readyz"},
  {"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/healthz"}]' >/dev/null
kubectl rollout status deployment/api -n $NS --timeout=300s
kubectl get deployment api -n $NS -o jsonpath='{range .spec.template.spec.containers[0]}liveness={.livenessProbe.httpGet.path} readiness={.readinessProbe.httpGet.path}{"\n"}{end}'
sample "swapped:before" 20
outage "swapped"

echo
echo "## restore the shipped probes"
kubectl patch deployment api -n $NS --type json -p '[
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/healthz"},
  {"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/readyz"}]' >/dev/null
kubectl rollout status deployment/api -n $NS --timeout=600s
kubectl get pods -n $NS -l app=api
