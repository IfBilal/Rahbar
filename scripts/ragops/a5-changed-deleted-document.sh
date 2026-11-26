#!/usr/bin/env bash
# Recovered from the session transcript (only absolute paths adjusted) that produced docs/a3-evidence/A/A5-changed-and-deleted-document.txt (it was a throwaway /tmp/a5.sh at the time).
# Run from anywhere with KUBECONFIG set; writes two throwaway fixture documents (demo-notice.md, v2) then drives the ingest job.
export DEMO_DIR=${DEMO_DIR:-$(mktemp -d)}
python3 - <<'PY'
import os,tempfile
S=os.environ['DEMO_DIR']+'/'
body1="""---
title: Demo Notice
doc_version: 2026-12
---
# Demo Notice

TEST FIXTURE: a throwaway document used to demonstrate a changed and a deleted document. It is not a rule.

## 1. Notice board

Notices for students are posted on the notice board outside the main office every Monday before nine in the morning. A notice stays up for two weeks. """+" ".join(f"Filler sentence number {i} keeps this section long enough to form a second chunk of text for the demonstration." for i in range(1,30))+"""

## 2. Lost property

Lost property is kept at the main office for thirty days and is then given to charity.
"""
open(S+'demo-notice.md','w').write(body1)
open(S+'demo-notice-v2.md','w').write(body1.replace("every Monday before nine in the morning","every Tuesday before ten in the morning").replace("thirty days","sixty days"))
PY
cd "$(dirname "$0")/../.."
summ() { python3 -c "
import sys,json
for l in sys.stdin:
    if l.startswith('{') and 'ingest_summary' in l:
        d=json.loads(l); print('  ', {k:d[k] for k in ('docs_new','docs_updated','docs_deleted','docs_unchanged','chunks_embedded','chunks_written','chunks_deleted','verification_embeddings') if k in d}, 'revision', d['indexes']['rahbar']['revision'])"; }
cnt() { scripts/ragops/job.sh count -- count 2>&1 | grep '^{"indexes"' | python3 -c "
import sys,json
d=json.loads(sys.stdin.read())['indexes']['rahbar']
others={k:v for k,v in d['per_doc'].items() if not k.startswith('demo-notice')}
print('   chroma_total',d['chroma_total'],'ledger_expected',d['ledger_expected_total'],'orphans',d['orphans'],'| demo-notice chunks:',{k:v for k,v in d['per_doc'].items() if k.startswith('demo-notice')},'| all other documents:',sum(others.values()),'chunks')"; }
echo '### 0. before'; cnt
echo '### 1. a NEW document arrives (inbox/demo/demo-notice.md)'
kubectl exec -n rahbar ragops-loader -- mkdir -p /data/inbox/demo; kubectl cp $DEMO_DIR/demo-notice.md rahbar/ragops-loader:/data/inbox/demo/demo-notice.md
scripts/ragops/job.sh sync 2>&1 | summ; cnt
echo '### 2. the SAME document CHANGES (two sentences edited): only its own chunks are replaced'
kubectl cp $DEMO_DIR/demo-notice-v2.md rahbar/ragops-loader:/data/inbox/demo/demo-notice.md
scripts/ragops/job.sh sync 2>&1 | summ; cnt
echo '### 3. unchanged re-run: nothing is embedded'
scripts/ragops/job.sh sync 2>&1 | summ
echo '### 4. the document is DELETED from the index (and removed from the inbox so it does not come back)'
kubectl exec -n rahbar ragops-loader -- rm /data/inbox/demo/demo-notice.md
scripts/ragops/job.sh delete -- delete demo-notice 2>&1 | grep ingest_summary | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print('  ', {k:d.get(k) for k in ('command','deleted','chunks_deleted','exit')})"; cnt
