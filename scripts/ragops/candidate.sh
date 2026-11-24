#!/usr/bin/env bash
# Serve a candidate (docs/a3-ragops/07 section 4, 10 section 4): render k8s/candidate.yaml with the
# release-scoped values of ragops/config/candidates/<name>.yaml and apply it. The candidate gets its
# own Deployment, Service and Chroma collection; the collection itself is built beforehand with
#   scripts/ragops/job.sh build-index -- build-index --collection <c> --embed-model <m>
#   scripts/ragops/candidate.sh cand-mxbai [--dry-run]
set -euo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd)
name=${1:?usage: candidate.sh <candidate-name> [--dry-run]}
spec="$here/ragops/config/candidates/$name.yaml"
[ -f "$spec" ] || { echo "no such candidate spec: $spec" >&2; exit 2; }
out=$(python3 - "$here/k8s/candidate.yaml" "$spec" <<'PY'
import sys, yaml
tmpl, spec = sys.argv[1:3]
docs = list(yaml.safe_load_all(open(tmpl)))
s = yaml.safe_load(open(spec))
for key in ("embed_version", "relevance_floor", "collection", "embed_model", "release_id"):
    if s.get(key) in (None, ""):
        sys.exit(f"{spec}: {key} is not filled in yet (calibrate it and commit it first)")
want = {"RELEASE_ID": s["release_id"], "CHROMA_COLLECTION": s["collection"],
        "EMBED_MODEL": s["embed_model"], "EMBED_VERSION": s["embed_version"],
        "RELEVANCE_FLOOR": str(s["relevance_floor"]), "TOP_K": str(s["top_k"])}
env = docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
for e in env:
    if e["name"] in want:
        e["value"] = want[e["name"]]
print(yaml.safe_dump_all(docs))
PY
)
if [ "${2:-}" = "--dry-run" ]; then echo "$out"; exit 0; fi
echo "$out" | kubectl apply -f -
kubectl rollout status deployment/api-candidate -n rahbar --timeout=600s
