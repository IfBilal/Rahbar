#!/usr/bin/env bash
# Run one ingestion operation as a Job named ingest-<action>-<timestamp> (docs/a3-ragops/10 5.1).
# The Job is the base ingest Job with its arguments replaced, so it has the same image, volumes,
# resources and NetworkPolicy as the scheduled one; it is still the only writer.
#
#   scripts/ragops/job.sh sync                         # verify + update (same as the CronJob)
#   scripts/ragops/job.sh restore -- restore academic-rules@2023-08
#   scripts/ragops/job.sh count  -- count --json
#   scripts/ragops/job.sh build-index -- build-index --collection rahbar-cand-mxbai --embed-model mxbai-embed-large
# Environment: TAG (image tag, default dev), NS (default rahbar), WAIT=0 to skip waiting.
set -euo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd)
action=${1:?usage: job.sh <action> [-- <pipeline.run arguments>]}
shift
if [ "${1:-}" = "--" ]; then shift; fi
args=("$@"); [ ${#args[@]} -gt 0 ] || args=("$action")
NS=${NS:-rahbar}; TAG=${TAG:-dev}
name="ingest-${action}-$(date -u +%m%d%H%M%S)"
ARGS_JSON=$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1:]))' "${args[@]}")
python3 - "$here/k8s/base/ingest-job.yaml" "$name" "$TAG" "$ARGS_JSON" <<'PY' | kubectl apply -f -
import json, sys, yaml
path, name, tag, args = sys.argv[1:5]
job = yaml.safe_load(open(path))
job["metadata"]["name"] = name
spec = job["spec"]["template"]["spec"]
spec["containers"][0]["args"] = json.loads(args)
for c in spec.get("initContainers", []) + spec["containers"]:
    if ":" not in c["image"]:
        c["image"] += ":" + tag
print(yaml.safe_dump(job))
PY
echo "job/$name"
if [ "${WAIT:-1}" = "1" ]; then
  # wait for Complete OR Failed (a plain --for=condition=complete would sit out the whole timeout on a failure)
  done=0
  for _ in $(seq 1 "${WAIT_STEPS:-1800}"); do
    st=$(kubectl get "job/$name" -n "$NS" -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null || true)
    case "$st" in 1/*) done=1; break ;; */1) kubectl logs -n "$NS" "job/$name" --all-containers --tail=40; echo "job/$name FAILED" >&2; exit 1 ;; esac
    sleep 2
  done
  [ "$done" = 1 ] || { echo "timed out waiting for job/$name" >&2; exit 1; }
  kubectl logs -n "$NS" "job/$name" -c indexer --tail=3
fi
