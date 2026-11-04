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


def test_the_embedding_prefix_rule_is_the_same_on_both_sides() -> None:
    import importlib.util

    def load(path: Path, name: str):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        return mod

    q = load(ROOT / "api/app/retrieval/embedder.py", "q_embedder")
    for model in ("nomic-embed-text", "nomic-embed-text:latest", "mxbai-embed-large"):
        d = (ROOT / "indexer/pipeline/embed.py").read_text()
        uses_prefix = model.startswith("nomic-embed-text")
        assert bool(q.query_prefix(model)) == uses_prefix
        assert 'startswith("nomic-embed-text")' in d
