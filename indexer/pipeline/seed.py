"""Seed the inbox once (docs/a3-ragops/10 section 5.1, the Job's init step).

    python -m pipeline.seed --inbox /data/inbox [--source /work/corpus/raw]

Copies the downloaded corpus (corpus/fetch.py writes `_index.json` next to the files) into
the inbox and writes `_batch.yaml` with the title, version and series (`doc_id`) of each
document, so Batch A is ingested with a catalog. It does nothing when `.seeded` already
exists, so a re-run never re-copies or re-downloads anything. New documents are dropped into
the inbox by hand (or by the loader pod) and need no catalog at all.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from .catalog import derive_doc_id

MARKER = ".seeded"


def seed(inbox: Path, source: Path, sources_yaml: Path | None = None) -> int:
    """Return the number of files copied (0 if the inbox was already seeded)."""
    inbox.mkdir(parents=True, exist_ok=True)
    if (inbox / MARKER).exists():
        return 0
    index = json.loads((source / "_index.json").read_text(encoding="utf-8"))
    declared: dict[str, dict[str, str]] = {}
    if sources_yaml and sources_yaml.exists():
        for d in yaml.safe_load(sources_yaml.read_text(encoding="utf-8")).get("documents", []):
            declared[str(d.get("name", ""))] = d
    rows = []
    for entry in index:
        src = source / entry["file"]
        if not src.exists():
            continue
        shutil.copyfile(src, inbox / entry["file"])
        meta = declared.get(str(entry.get("name", "")), {})
        title = str(entry.get("name") or meta.get("name") or Path(entry["file"]).stem)
        rows.append({"file": entry["file"], "title": title,
                     "doc_version": str(entry.get("doc_version", "unknown")),
                     "doc_id": str(meta.get("doc_id") or derive_doc_id(title, entry["file"]))})
    (inbox / "_batch.yaml").write_text(yaml.safe_dump({"batch": "A", "documents": rows},
                                                      sort_keys=False), encoding="utf-8")
    (inbox / MARKER).write_text("seeded\n", encoding="utf-8")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the ingestion inbox from the fetched corpus.")
    ap.add_argument("--inbox", type=Path, required=True)
    ap.add_argument("--source", type=Path, default=Path("/work/corpus/raw"))
    ap.add_argument("--sources-yaml", type=Path, default=Path("/app/corpus/sources.yaml"))
    args = ap.parse_args()
    n = seed(args.inbox, args.source, args.sources_yaml)
    print(json.dumps({"type": "seed", "copied": n, "already_seeded": n == 0}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
