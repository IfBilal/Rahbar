"""Runtime configuration, read once from environment variables.

On the cluster these variables come from your ConfigMap and Secret (section 4.1).
Nothing here is baked into the image, so one image runs in every environment.
Add your own keys (relevance floor, cache settings, ...) the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Which implementations to load. "stub" needs no cluster, no model, no network.
    retriever: str = "stub"          # RETRIEVER: stub | chroma
    llm_provider: str = "stub"       # LLM_PROVIDER: stub | ollama-host | ollama-incluster | hosted

    # The embedding pin (section 4.4). The indexer reads the same ConfigMap key.
    embed_model: str = "nomic-embed-text"

    # Vector store
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    collection: str = "rahbar"

    # Retrieval and generation
    top_k: int = 5
    temperature: float = 0.2
    llm_model: str = "llama3.2:3b"
    ollama_url: str = "http://host.minikube.internal:11434"
    hosted_base_url: str = ""        # e.g. an OpenAI-compatible endpoint
    llm_api_key: str = field(default="", repr=False)   # from the Secret; never log it

    log_level: str = "INFO"

    # Grounding (3.4): the best retrieved similarity must reach this or the API abstains.
    relevance_floor: float = 0.55
    # Exact-term assist (5.2 / note 5): pull chunks that literally contain a clause number
    # or course code named in the question to the front of the dense results.
    exact_term_assist: bool = True
    llm_timeout: float = 120.0       # seconds; generation on a laptop CPU is slow

    # Semantic cache (3.3). Disabled when REDIS_URL is empty (make dev, unit tests).
    redis_url: str = ""
    cache_threshold: float = 0.95
    cache_max_entries: int = 500
    cache_ttl_seconds: int = 7 * 24 * 3600


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def get_settings() -> Settings:
    return Settings(
        retriever=os.environ.get("RETRIEVER", "stub"),
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=_int("CHROMA_PORT", 8000),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        top_k=_int("TOP_K", 5),
        temperature=_float("TEMPERATURE", 0.2),
        llm_model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        hosted_base_url=os.environ.get("HOSTED_BASE_URL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        relevance_floor=_float("RELEVANCE_FLOOR", 0.55),
        exact_term_assist=_bool("EXACT_TERM_ASSIST", True),
        llm_timeout=_float("LLM_TIMEOUT_SECONDS", 120.0),
        redis_url=os.environ.get("REDIS_URL", ""),
        cache_threshold=_float("CACHE_THRESHOLD", 0.95),
        cache_max_entries=_int("CACHE_MAX_ENTRIES", 500),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 7 * 24 * 3600),
    )
