#!/usr/bin/env bash
# Copy a curated sample of traces out of the traces volume into the repository (PDF: "trace samples ...
# committed under traces/"). Usage:  scripts/ragops/export_traces.sh <label>=<trace_id> ...
# Writes traces/samples.jsonl (one record per line, with a "sample_label" key added) and, for each record that
# reached the model, the stored prompt traces/prompts/<sha256>.json that `python -m ragops.trace.show` reads
# with  --traces traces .
set -euo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd); NS=${NS:-rahbar}
mkdir -p "$here/traces/prompts"
: > "$here/traces/samples.jsonl.new"
for pair in "$@"; do
  label=${pair%%=*}; id=${pair#*=}
  line=$(kubectl exec -n "$NS" ragops-loader -- sh -c "grep -h '\"trace_id\":\"$id\"' /traces/*.jsonl | head -1")
  [ -n "$line" ] || { echo "trace $id not found" >&2; exit 1; }
  printf '%s' "$line" | python3 -c 'import json, sys
rec = json.loads(sys.stdin.read()); rec["sample_label"] = sys.argv[1]
print(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))' "$label" >> "$here/traces/samples.jsonl.new"
  sha=$(printf '%s' "$line" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); print((r.get('prompt') or {}).get('sha256') or '')")
  if [ -n "$sha" ]; then
    kubectl exec -n "$NS" ragops-loader -- cat "/traces/prompts/$sha.json" > "$here/traces/prompts/$sha.json"
  fi
  echo "exported $label ($id)"
done
cat "$here/traces/samples.jsonl.new" >> "$here/traces/samples.jsonl"; rm "$here/traces/samples.jsonl.new"
