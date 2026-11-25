#!/bin/sh
# The ingestion Job's entry point (docs/a3-ragops/10 section 5.1, contract 14 section 1).
#
# 1. Wait for Chroma. The Job and the Chroma StatefulSet are applied together, and a pod that starts first used to
#    fail with "connection refused", leave a half-written index, and exhaust its retries before Chroma was up (the
#    first A3 CI runs). CHROMA_WAIT_SECONDS=0 skips the wait (unit tests); on timeout we run anyway and let the
#    pipeline report the real error.
# 2. `pipeline.run` exits 1 when it finished but quarantined documents. For a Job that is a success (quarantine is
#    the pipeline doing its job); any other non-zero code stays a failure so Kubernetes retries it (backoffLimit) or
#    marks it Failed: 3 fatal, 2 usage, 4 unknown target.
WAIT=${CHROMA_WAIT_SECONDS:-300}
if [ "$WAIT" -gt 0 ] 2>/dev/null; then
  python - "$WAIT" <<'PY'
import os, sys, time, urllib.request
deadline = time.time() + int(sys.argv[1])
url = f"http://{os.environ.get('CHROMA_HOST', 'chroma')}:{os.environ.get('CHROMA_PORT', '8000')}/api/v2/heartbeat"
while time.time() < deadline:
    try:
        urllib.request.urlopen(url, timeout=3).read()
        print('{"logger":"rahbar.indexer","msg":"chroma is up"}', flush=True)
        break
    except Exception:
        time.sleep(3)
else:
    print('{"logger":"rahbar.indexer","msg":"chroma did not answer in time: running anyway"}', flush=True)
PY
fi
python -m pipeline.run "$@"
rc=$?
if [ "$rc" -eq 1 ]; then
  echo '{"logger":"rahbar.indexer","msg":"finished with quarantined documents: exit 1 mapped to 0"}'
  exit 0
fi
exit "$rc"
