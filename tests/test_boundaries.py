"""Design tests: the single-writer architecture is enforced by the code layout, not trust.

The API reads the index and never writes it (4.2); the indexer is the only writer; the
API never imports the indexer; liveness touches no dependency (4.3); no eval() on text.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = sorted((ROOT / "api" / "app").rglob("*.py"))
INDEXER = sorted((ROOT / "indexer" / "pipeline").rglob("*.py"))
WRITES = re.compile(r"\.(add|upsert|update|delete|create_collection|get_or_create_collection|"
                    r"delete_collection|modify)\s*\(")


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


def test_the_api_never_writes_to_chroma() -> None:
    chroma_files = [p for p in API if "retrieval" in p.parts or p.name in ("main.py", "health.py")]
    for path in chroma_files:
        bad = _calls(path) & {"add", "upsert", "delete_collection", "create_collection",
                              "get_or_create_collection", "modify"}
        assert not bad, f"{path.relative_to(ROOT)} writes to Chroma: {bad}"


def test_the_indexer_is_the_writer() -> None:
    store = (ROOT / "indexer" / "pipeline" / "store.py").read_text()
    assert WRITES.search(store)


def test_the_api_never_imports_the_indexer() -> None:
    for path in API:
        assert "pipeline" not in path.read_text(encoding="utf-8").split("import"), path


def test_api_startup_does_no_indexing() -> None:
    main = (ROOT / "api" / "app" / "main.py").read_text()
    lifespan = main[main.index("async def lifespan"):main.index("yield")]
    for verb in ("chunk(", "extract(", "embed(", ".add(", "store(", "run_pipeline"):
        assert verb not in lifespan


def test_liveness_handler_touches_nothing() -> None:
    src = (ROOT / "api" / "app" / "routes" / "health.py").read_text()
    body = src[src.index("def healthz"):src.index("def readiness_checks")]
    assert re.search(r"return \{\"status\": \"alive\"\}", body)
    for dep in ("retriever", "cache", "redis", "chroma", "state", "httpx"):
        assert dep not in body.split('"""')[-1], dep


def test_no_eval_or_exec_on_model_or_document_text() -> None:
    for path in API + INDEXER:
        assert not ({"eval", "exec"} & {n.func.id for n in ast.walk(ast.parse(path.read_text()))
                                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}), path


def test_both_sides_prepare_text_identically_for_the_pinned_model() -> None:
    """The pin is more than a model name: prefix and casing must match too, or vectors
    from the indexer and the API stop being comparable without any error."""
    import importlib
    import importlib.util

    def load(path: Path, name: str):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        return mod

    import sys

    query = load(ROOT / "api/app/retrieval/embedder.py", "q_embedder")
    sys.path.insert(0, str(ROOT / "indexer"))
    doc = importlib.import_module("pipeline.embed")
    suite = load(ROOT / "ragops/suite/prep.py", "suite_prep")
    # one table, three copies (separate images): they must be identical, or writer and reader drift
    assert query.EMBED_PROFILES == doc.EMBED_PROFILES == suite.EMBED_PROFILES
    assert set(query.EMBED_PROFILES) == {"nomic-embed-text", "mxbai-embed-large", "all-minilm"}
    for model in ("nomic-embed-text", "nomic-embed-text:latest", "mxbai-embed-large", "all-minilm"):
        for text in ("Rector's List of Honors", "BS fee per credit hour", "clause 1.21"):
            q = query.prepare_query(model, text)
            d = doc.prepare_document(model, text)
            # identical apart from the task prefix
            assert q.removeprefix(query.query_prefix(model)) == d.removeprefix(doc.document_prefix(model))
            assert suite.prepare_query(model, text) == q


# ---------------------------------------------------------------- Assignment 03 (docs/a3-ragops/14 section 10)
RAGOPS = sorted(p for p in (ROOT / "ragops").rglob("*.py") if "tests" not in p.parts)
WRITERS = {"store.py", "incremental.py", "ops.py", "index.py", "dummy.py"}
CHROMA_WRITE = {"upsert", "create_collection", "get_or_create_collection", "delete_collection",
                "modify"}


def test_the_ragops_tools_never_import_chroma_or_the_indexer() -> None:
    """The suite, gate, coverage and trace tools read results and call the API; only the
    ingestion Job writes the vector store, and the tools have no way to reach it."""
    for path in RAGOPS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                 for a in n.names}
        names |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                  if isinstance(n, ast.ImportFrom)}
        assert not names & {"chromadb", "pipeline"}, f"{path.relative_to(ROOT)} imports {names}"


def test_only_the_designated_indexer_modules_write_to_chroma() -> None:
    """Writes to the vector store live in index.py (the adapter) and the modules that drive
    it; verify/lake/ledger/catalog/report never call a Chroma write method."""
    for path in INDEXER:
        if path.name in WRITERS:
            continue
        bad = _calls(path) & CHROMA_WRITE
        assert not bad, f"{path.relative_to(ROOT)} calls Chroma write methods: {bad}"


def test_the_api_has_no_ingestion_code_paths() -> None:
    for path in API:
        text = path.read_text(encoding="utf-8")
        assert "pipeline.incremental" not in text and "pipeline.ops" not in text
