"""Text preparation, identical to the pipeline's (docs/a3-ragops/06 section 4).

The suite must embed text exactly the way the live API embeds a query, otherwise the
module-level numbers describe a different system. This mirrors `api/app/retrieval/embedder.py`
(`prepare_query`); a test compares the two so they cannot drift apart. It is a copy rather
than an import because the `rahbar-ragops` image does not ship the API package.
"""

from __future__ import annotations


# How text is prepared for each embedding model (docs/a3-ragops/07 section 3.1). The same table is
# kept in the three places that prepare text, because they ship in separate images:
# api/app/retrieval/embedder.py, indexer/pipeline/embed.py and ragops/suite/prep.py.
# tests/test_boundaries.py fails if they differ, so the writer, the reader and the suite cannot drift.
#   doc_prefix / query_prefix: the task instruction the model was trained with
#   lowercase: the model has an uncased vocabulary and Ollama 0.17 does not lowercase for it. Measured
#   (docs/a3-evidence/C/casing-check.txt): true for nomic-embed-text only; mxbai and minilm lowercase themselves.
EMBED_PROFILES: dict[str, dict[str, object]] = {
    "nomic-embed-text": {"doc_prefix": "search_document: ", "query_prefix": "search_query: ",
                         "lowercase": True},
    "mxbai-embed-large": {"doc_prefix": "",
                          "query_prefix": "Represent this sentence for searching relevant passages: ",
                          "lowercase": False},
    "all-minilm": {"doc_prefix": "", "query_prefix": "", "lowercase": False},
}
NO_PROFILE: dict[str, object] = {"doc_prefix": "", "query_prefix": "", "lowercase": False}


def embed_profile(model: str) -> dict[str, object]:
    for name, profile in EMBED_PROFILES.items():
        if model.startswith(name):
            return profile
    return NO_PROFILE


def query_prefix(model: str) -> str:
    return str(embed_profile(model)["query_prefix"])


def prepare_query(model: str, text: str) -> str:
    profile = embed_profile(model)
    return str(profile["query_prefix"]) + (text.lower() if profile["lowercase"] else text)
