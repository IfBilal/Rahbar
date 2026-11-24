#!/usr/bin/env bash
# Release a candidate to the live Deployment (docs/a3-ragops/07 section 7, contract 14 section 7.4).
#
#   scripts/ragops/release.sh <candidate-name> [--dry-run]
#
# Exit codes: 0 released | 1 refused (the gate, or a precondition) | 2 rollout failed or timed out.
# Kubernetes does not know about the gate: THIS script is what keeps a failing candidate from being
# rolled out, by refusing unless all three preconditions hold. There is no --force (it would defeat F3).
# A failed rollout is NOT undone automatically: undoing is a deliberate step (kubectl rollout undo).
set -uo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd)
NS=${NS:-rahbar}
name=${1:?usage: release.sh <candidate-name> [--dry-run]}
dry=0; [ "${2:-}" = "--dry-run" ] && dry=1
spec="$here/ragops/config/candidates/$name.yaml"
refuse() { echo "REFUSED: $*" >&2; exit 1; }
[ -f "$spec" ] || refuse "no candidate spec $spec"

eval "$(python3 - "$spec" <<'PY'
import sys, yaml, shlex
s = yaml.safe_load(open(sys.argv[1]))
for k in ("release_id", "collection", "embed_model", "embed_version", "relevance_floor", "top_k"):
    if s.get(k) in (None, ""):
        print(f'refuse "{sys.argv[1]}: {k} is not filled in"')
        sys.exit(0)
    print(f"{k.upper()}={shlex.quote(str(s[k]))}")
PY
)"

# The loader pod is how we read the results volume.
kubectl get pod ragops-loader -n "$NS" >/dev/null 2>&1 || {
  kubectl apply -f "$here/k8s/loader-pod.yaml" >/dev/null && kubectl wait --for=condition=Ready pod/ragops-loader -n "$NS" --timeout=120s >/dev/null; }
rx() { kubectl exec -n "$NS" ragops-loader -- "$@"; }

# 1. a passing gate decision for exactly this candidate, newer than its result file
latest_result=$(rx sh -c "ls -1t /results/*_${name}.json 2>/dev/null | head -1")
[ -n "$latest_result" ] || refuse "no result file for $name: run the suite first"
decision="${latest_result%.json}.decision.json"
rx test -f "$decision" || refuse "no gate decision for $latest_result: run the gate"
verdict=$(rx cat "$decision" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("overall"), d.get("candidate", {}).get("release_id"), d.get("candidate", {}).get("file"))')
set -- $verdict
overall=$1; rid=$2; cfile=$3
[ "$overall" = "pass" ] || refuse "gate decision for $name is '$overall', not pass ($decision)"
[ "$rid" = "$RELEASE_ID" ] || refuse "decision is for release '$rid', not '$RELEASE_ID'"
[ "$(basename "$latest_result")" = "$(basename "$cfile")" ] || refuse "decision is stale: it was made for $cfile, newer result is $latest_result"

# 2. the candidate is Ready and serves the candidate collection
ready=$(kubectl get deploy api-candidate -n "$NS" -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
[ "${ready:-0}" -ge 1 ] || refuse "api-candidate is not Ready"
cur=$(kubectl get deploy api-candidate -n "$NS" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' | grep '^CHROMA_COLLECTION=' | cut -d= -f2)
[ "$cur" = "$COLLECTION" ] || refuse "api-candidate serves '$cur', not '$COLLECTION'"

# 3. no ingest Job is running (single writer; never release mid-update)
active=$(kubectl get jobs -n "$NS" -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{"\n"}{end}' | grep '^ingest' || true)
[ -z "$active" ] || refuse "an ingest Job is running ($active)"

sha=$(rx sha256sum "$decision" | cut -c1-12)
cmds=("kubectl -n $NS annotate deployment/api kubernetes.io/change-cause='release $RELEASE_ID (gate decision $sha)' --overwrite"
      "kubectl -n $NS set env deployment/api RELEASE_ID=$RELEASE_ID CHROMA_COLLECTION=$COLLECTION EMBED_MODEL=$EMBED_MODEL EMBED_VERSION=$EMBED_VERSION RELEVANCE_FLOOR=$RELEVANCE_FLOOR TOP_K=$TOP_K"
      "kubectl -n $NS rollout status deployment/api --timeout=900s")
if [ "$dry" = 1 ]; then printf 'DRY RUN, gate passed (%s). Would run:\n' "$decision"; printf '  %s\n' "${cmds[@]}"; exit 0; fi
echo "gate decision: $decision (pass); releasing $RELEASE_ID"
for c in "${cmds[@]}"; do echo "+ $c"; eval "$c" || { echo "ROLLOUT FAILED: $c (not undone: kubectl rollout undo deployment/api -n $NS)" >&2; exit 2; }; done
kubectl -n "$NS" rollout history deployment/api
echo "released $RELEASE_ID"
