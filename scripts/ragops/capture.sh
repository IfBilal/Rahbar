#!/usr/bin/env bash
# Run a command, keep its raw output as evidence, and render the report screenshot from it.
#
#   scripts/ragops/capture.sh <LABEL> <evidence-dir> -- <command ...>
#   scripts/ragops/capture.sh A1 docs/a3-evidence/A -- kubectl exec -n rahbar ragops-loader -- cat /data/reports/verification/x.md
#
# Writes <evidence-dir>/<LABEL>.txt (the command line, a UTC timestamp, the full combined output and
# the exit code) and <evidence-dir>/screenshots/<LABEL>.png. The exit code of the command is returned.
set -uo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd)
label=${1:?label}; dir=${2:?evidence dir}; shift 2
[ "${1:-}" = "--" ] && shift
mkdir -p "$dir/screenshots"
txt="$dir/$label.txt"
{
  printf '$ %s\n' "$*"
  "$@" 2>&1
  rc=$?
  printf '\n[exit %s at %s UTC]\n' "$rc" "$(date -u +%Y-%m-%dT%H:%M:%S)"
} > "$txt"
rc=$(tail -1 "$txt" | sed -n 's/.*exit \([0-9]*\) at.*/\1/p')
cat "$txt"
"${PYTHON:-$here/.venv/bin/python}" "$here/scripts/ragops/shot.py" --label "$label" --transcript "$txt" --out "$dir/screenshots/$label.png" >/dev/null
exit "${rc:-0}"
