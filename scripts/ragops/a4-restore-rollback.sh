#!/usr/bin/env bash
# Recovered from the session transcript (only absolute paths adjusted) that produced docs/a3-evidence/A/A4-restore-rollback-demo.txt (it was a throwaway /tmp/a4.sh at the time).
# Run from anywhere with KUBECONFIG set; needs EVAL_TOKEN and `kubectl -n rahbar port-forward svc/api 8003:8000` running (the original session set both up before calling it).
cd "$(dirname "$0")/../.."
FE=faculty-entrepreneurship-and-technical-start-ups-policy
st() { scripts/ragops/job.sh status -- status 2>&1 | grep '^{"batches"' | python3 -c "
import sys,json
d=json.loads(sys.stdin.read()); print('  ledger:', d['documents']['$FE'], '| index revision', d['indexes']['rahbar']['revision'], 'chunks', d['indexes']['rahbar']['count'])"; }
ask() { sleep 6; curl -s -X POST localhost:8003/api/retrieve -H "X-Eval-Token: $EVAL_TOKEN" -H 'content-type: application/json' -d '{"question":"What share of equity does the university take in a start-up that uses its facilities?","k":8}' | python3 -c "
import sys,json
d=json.load(sys.stdin); print('  /api/retrieve versions returned:', sorted({c['doc_version'] for c in d['candidates'] if 'faculty' in c['doc_id']}), 'at index revision', d['collection']['revision'])"; }
echo '### 1. normal state'; st; ask
echo '### 2. rollback: restore the archived 2022-05 version'; scripts/ragops/job.sh restore -- restore $FE@2022-05 2>&1 | tail -1 | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print('  restored:', d.get('restored'), '| archived:', d.get('archived'), '| chunks_embedded:', d['chunks_embedded'])"; st; ask
echo '### 3. back to normal: restore 2026-11'; scripts/ragops/job.sh restore -- restore $FE@2026-11 2>&1 | tail -1 | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print('  restored:', d.get('restored'), '| archived:', d.get('archived'), '| chunks_embedded:', d['chunks_embedded'])"; st; ask
