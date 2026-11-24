#!/bin/sh
# The ingestion Job's entry point (docs/a3-ragops/10 section 5.1, contract 14 section 1).
# `pipeline.run` exits 1 when it finished but quarantined documents. For a Job that is a
# success (quarantine is the pipeline doing its job); any other non-zero code stays a failure
# so Kubernetes retries it (backoffLimit) or marks it Failed: 3 fatal, 2 usage, 4 unknown target.
python -m pipeline.run "$@"
rc=$?
if [ "$rc" -eq 1 ]; then
  echo '{"logger":"rahbar.indexer","msg":"finished with quarantined documents: exit 1 mapped to 0"}'
  exit 0
fi
exit "$rc"
