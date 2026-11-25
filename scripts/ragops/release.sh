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
dry=0
spec="$here/ragops/config/candidates/$name.yaml"
refuse() { echo "REFUSED: $*" >&2; exit 1; }
case "${2:-}" in "") ;; --dry-run) dry=1 ;; *) refuse "unknown argument '$2' (the only option is --dry-run)" ;; esac
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || refuse "candidate name '$name' has characters outside [A-Za-z0-9._-]"
[ -f "$spec" ] || refuse "no candidate spec $spec"

# Values from the candidate spec end up in kubectl arguments: allow only a strict character set,
# and never build a command string (no eval).
vals=$(python3 - "$spec" <<'PY'
import re, sys, yaml
s = yaml.safe_load(open(sys.argv[1]))
out = []
for k in ("release_id", "collection", "embed_model", "embed_version", "relevance_floor", "top_k"):
    v = s.get(k)
    if v in (None, ""):
        sys.exit(f"{sys.argv[1]}: {k} is not filled in")
    v = str(v)
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", v):
        sys.exit(f"{sys.argv[1]}: {k}={v!r} has characters outside [A-Za-z0-9._:-]")
    out.append(v)
print("\n".join(out))
PY
) || refuse "$vals"
{ read -r RELEASE_ID; read -r COLLECTION; read -r EMBED_MODEL; read -r EMBED_VERSION; read -r RELEVANCE_FLOOR; read -r TOP_K; } <<<"$vals"

# The loader pod is how we read the results volume.
kubectl get pod ragops-loader -n "$NS" >/dev/null 2>&1 || {
  kubectl apply -f "$here/k8s/loader-pod.yaml" >/dev/null && kubectl wait --for=condition=Ready pod/ragops-loader -n "$NS" --timeout=120s >/dev/null; }
rx() { kubectl exec -n "$NS" ragops-loader -- "$@"; }

# 1. a passing gate decision for exactly this candidate, newer than its result file
latest_result=$(rx sh -c 'ls -1t /results/*_"$1".json 2>/dev/null | head -1' _ "$name")
[ -n "$latest_result" ] || refuse "no result file for $name: run the suite first"
decision="${latest_result%.json}.decision.json"
rx test -f "$decision" || refuse "no gate decision for $latest_result: run the gate"
# The decision is only as good as what it was made from: it must be for this exact candidate, for the result
# of the system that is serving the candidate collection now (a collection rebuilt after the evaluation, or a
# different embedding version, is a different system), and must compare the candidate with a DIFFERENT baseline.
{ read -r overall; read -r rid; read -r cfile; read -r bfile; read -r rcoll; read -r rver; } < <(
  { rx cat "$decision"; echo "@@@@"; rx cat "$latest_result"; } | python3 -c '
import json, sys
dec, res = sys.stdin.read().split("@@@@", 1)
d, r = json.loads(dec), json.loads(res)
t = r.get("target", {})
print(d.get("overall")); print(d.get("candidate", {}).get("release_id")); print(d.get("candidate", {}).get("file"))
print(d.get("baseline", {}).get("file")); print(t.get("collection")); print(t.get("embed_version"))')
[ "$overall" = "pass" ] || refuse "gate decision for $name is '$overall', not pass ($decision)"
[ "$rid" = "$RELEASE_ID" ] || refuse "decision is for release '$rid', not '$RELEASE_ID'"
[ "$(basename "$latest_result")" = "$(basename "$cfile")" ] || refuse "decision is stale: it was made for $cfile, newer result is $latest_result"
[ "$(basename "$bfile")" != "$(basename "$cfile")" ] || refuse "the decision compared the candidate with itself ($bfile)"
case "$rcoll" in *"$COLLECTION"*) ;; *) refuse "the evaluated result was for collection '$rcoll', not '$COLLECTION': re-run the suite" ;; esac
[ "$rver" = "$EMBED_VERSION" ] || refuse "the evaluated result used embedding version '$rver', the spec says '$EMBED_VERSION': re-run the suite"

# 2. the candidate is Ready and serves the candidate collection
ready=$(kubectl get deploy api-candidate -n "$NS" -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
[ "${ready:-0}" -ge 1 ] || refuse "api-candidate is not Ready"
cur=$(kubectl get deploy api-candidate -n "$NS" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' | grep '^CHROMA_COLLECTION=' | cut -d= -f2)
[ "$cur" = "$COLLECTION" ] || refuse "api-candidate serves '$cur', not '$COLLECTION'"

# 3. no ingest Job is running (single writer; never release mid-update)
jobs=$(kubectl get jobs -n "$NS" -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{"\n"}{end}') || refuse "cannot list the Jobs: not releasing blind"
active=$(printf '%s\n' "$jobs" | grep '^ingest' || true)
[ -z "$active" ] || refuse "an ingest Job is running ($active)"

sha=$(rx sha256sum "$decision" | cut -c1-12)
cause="release $RELEASE_ID (gate decision $sha)"
annotate=(kubectl -n "$NS" annotate deployment/api "kubernetes.io/change-cause=$cause" --overwrite)
setenv=(kubectl -n "$NS" set env deployment/api "RELEASE_ID=$RELEASE_ID" "CHROMA_COLLECTION=$COLLECTION"
        "EMBED_MODEL=$EMBED_MODEL" "EMBED_VERSION=$EMBED_VERSION" "RELEVANCE_FLOOR=$RELEVANCE_FLOOR" "TOP_K=$TOP_K")
status=(kubectl -n "$NS" rollout status deployment/api --timeout=900s)
if [ "$dry" = 1 ]; then
  printf 'DRY RUN, gate passed (%s). Would run:\n' "$decision"
  for c in setenv annotate status; do declare -n arr=$c; printf '  '; printf '%q ' "${arr[@]}"; printf '\n'; unset -n arr; done
  exit 0
fi
echo "gate decision: $decision (pass); releasing $RELEASE_ID"
# set env first (it creates the new revision), THEN annotate: the change-cause is copied to the ReplicaSet
# that is current at that moment, so annotating first would relabel the revision being replaced
for c in setenv annotate status; do
  declare -n arr=$c
  printf '+ '; printf '%q ' "${arr[@]}"; printf '\n'
  "${arr[@]}" || { echo "ROLLOUT FAILED at '$c' (not undone: kubectl rollout undo deployment/api -n $NS)" >&2; exit 2; }
  unset -n arr
done
kubectl -n "$NS" rollout history deployment/api
echo "released $RELEASE_ID"
