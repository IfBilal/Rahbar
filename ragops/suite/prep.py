"""Text preparation, identical to the pipeline's (docs/a3-ragops/06 section 4).

The suite must embed text exactly the way the live API embeds a query, otherwise the
module-level numbers describe a different system. This mirrors `api/app/retrieval/embedder.py`
(`prepare_query`); a test compares the two so they cannot drift apart. It is a copy rather
than an import because the `rahbar-ragops` image does not ship the API package.
"""

from __future__ import annotations


def query_prefix(model: str) -> str:
    return "search_query: " if model.startswith("nomic-embed-text") else ""


def prepare_query(model: str, text: str) -> str:
    if model.startswith("nomic-embed-text"):
        return query_prefix(model) + text.lower()
    return text
