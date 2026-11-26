#!/usr/bin/env bash
# Recovered from the session transcript (only absolute paths adjusted) that produced docs/a3-evidence/F/F6-bad-release-and-undo.txt (it was a throwaway /tmp/s3.sh at the time).
# Run from anywhere with KUBECONFIG set; capture with: scripts/ragops/capture.sh F6-bad-release-and-undo docs/a3-evidence/F -- bash scripts/ragops/s3-bad-release-undo.sh
set -u
cd /home/dns/Desktop/scd-assignment2-se-b-24i3015-24i3166
scripts/ragops/rollout-probe.sh start
echo "--- bad release: CHROMA_COLLECTION typo (pods can never become Ready)"
kubectl -n rahbar set env deployment/api RELEASE_ID=R5-bad-typo CHROMA_COLLECTION=rahbar-cand-minil
kubectl -n rahbar annotate deployment/api kubernetes.io/change-cause="release R5-bad-typo (collection name typo, deliberately broken for the rollback demo)" --overwrite
echo "--- kubectl rollout status --timeout=75s"
kubectl -n rahbar rollout status deployment/api --timeout=75s; echo "rollout status exit=$?"
kubectl -n rahbar get pods -l app=api
kubectl -n rahbar get endpoints api
echo "--- kubectl rollout undo"
kubectl -n rahbar rollout undo deployment/api
kubectl -n rahbar rollout status deployment/api --timeout=300s; echo "rollout status exit=$?"
kubectl -n rahbar rollout history deployment/api
scripts/ragops/rollout-probe.sh stop
