#!/bin/sh
# The evaluation Job's entry point (docs/a3-ragops/10 section 5.3): suite -> result file -> gate ->
# exit with the gate's code, so a failing gate is a Failed Job. The last log line is always
# machine readable:  RESULT=GATE_PASS|GATE_FAIL|SUITE_DONE|INFRA_ERROR ...
#
# Environment (from the ragops-eval-target ConfigMap and the Job):
#   MODE              suite+gate (default) | suite | gate (re-apply the gate to CANDIDATE_RESULT)
#   TARGET_URL        the Service under test, e.g. http://api:8000 or http://api-candidate:8000
#   LABEL             names the result file: <timestamp>_<LABEL>.json
#   BASELINE_RESULT   defaults to /results/baselines/live.json
#   CANDIDATE_RESULT  only for MODE=gate
#   SUITE_ARGS        extra run_suite arguments, e.g. "--batches A --repeat 2"
#   GATE_CONFIG, RESULTS_DIR, OLLAMA_URL
set -u
MODE=${MODE:-suite+gate}
RESULTS_DIR=${RESULTS_DIR:-/results}
GATE_CONFIG=${GATE_CONFIG:-/config/gate.yaml}
BASELINE_RESULT=${BASELINE_RESULT:-$RESULTS_DIR/baselines/live.json}
LABEL=${LABEL:-run}
mkdir -p "$RESULTS_DIR"

finish() { echo "RESULT=$1 ${2:-}"; exit "$3"; }

CANDIDATE=${CANDIDATE_RESULT:-}
if [ "$MODE" != "gate" ]; then
  STARTED=$(mktemp)                       # only a result written AFTER this point may be gated
  # shellcheck disable=SC2086
  python -m ragops.suite.run_suite --api "$TARGET_URL" --ollama "${OLLAMA_URL:-}" --label "$LABEL" \
      --ledger /data/ledger/ledger.json --lake /data --traces /traces --out "$RESULTS_DIR" ${SUITE_ARGS:-}
  rc=$?
  if [ "$rc" -ne 0 ]; then finish INFRA_ERROR "suite_exit=$rc" "$rc"; fi
  CANDIDATE=$(find "$RESULTS_DIR" -maxdepth 1 -name "*_$LABEL.json" -newer "$STARTED" 2>/dev/null | sort | tail -1)
  [ -n "$CANDIDATE" ] || finish INFRA_ERROR "no result file for label $LABEL" 3
  echo "result file: $CANDIDATE"
  [ "$MODE" = "suite" ] && finish SUITE_DONE "file=$CANDIDATE" 0
fi

[ -n "$CANDIDATE" ] || finish INFRA_ERROR "MODE=gate needs CANDIDATE_RESULT" 2
DECISION="${CANDIDATE%.json}.decision.json"
python -m ragops.gate.apply --baseline "$BASELINE_RESULT" --candidate "$CANDIDATE" \
    --config "$GATE_CONFIG" --decision-out "$DECISION" --git-sha "${GIT_SHA:-}"
rc=$?
case "$rc" in
  0) finish GATE_PASS "decision=$DECISION" 0 ;;
  1) finish GATE_FAIL "decision=$DECISION" 1 ;;
  *) finish INFRA_ERROR "gate_exit=$rc" "$rc" ;;
esac
