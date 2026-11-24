"""The two services the suite talks to: Ollama (embeddings, judge) and the RAHBAR API.

Both are thin so tests can replace them with fakes that have the same methods. No retries are
hidden here: a failure is a failure the result file must show (06 section 11).
"""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx


class InfrastructureError(RuntimeError):
    """Ollama or the API is unreachable or returned garbage (suite exit code 3)."""


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Judge(Protocol):
    model: str

    def generate_json(self, prompt: str, seed: int) -> str: ...


class Api(Protocol):
    def retrieve(self, question: str, k: int) -> dict[str, Any]: ...
    def ask(self, question: str, headers: dict[str, str], timeout: float) -> dict[str, Any]: ...
    def target_info(self) -> dict[str, Any]: ...


class OllamaEmbedder:
    def __init__(self, url: str, model: str, timeout: float = 120.0) -> None:
        self.url, self.model = url.rstrip("/"), model
        self.http = httpx.Client(timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            r = self.http.post(f"{self.url}/api/embed", json={"model": self.model, "input": texts})
            r.raise_for_status()
            vectors = r.json().get("embeddings") or []
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError(f"embedding service failed: {exc}") from exc
        if len(vectors) != len(texts):
            raise InfrastructureError(f"asked for {len(texts)} vectors, got {len(vectors)}")
        return [[float(x) for x in v] for v in vectors]


class OllamaJudge:
    def __init__(self, url: str, model: str, temperature: float = 0.0, timeout: float = 600.0):
        self.url, self.model, self.temperature = url.rstrip("/"), model, temperature
        self.http = httpx.Client(timeout=timeout)

    def generate_json(self, prompt: str, seed: int) -> str:
        body = {"model": self.model, "prompt": prompt, "stream": False, "format": "json",
                "options": {"temperature": self.temperature, "seed": seed}}
        try:
            r = self.http.post(f"{self.url}/api/generate", json=body)
            r.raise_for_status()
            return str(r.json().get("response", ""))
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError(f"judge call failed: {exc}") from exc


class HttpApi:
    def __init__(self, url: str, timeout: float = 900.0) -> None:
        self.url = url.rstrip("/")
        token = os.environ.get("EVAL_TOKEN", "")        # the API's shared secret for /api/retrieve and X-Eval-*
        self.http = httpx.Client(timeout=timeout, headers={"X-Eval-Token": token} if token else {})

    def retrieve(self, question: str, k: int) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            r = self.http.post(f"{self.url}/api/retrieve", json={"question": question, "k": k})
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError(f"/api/retrieve failed: {exc}") from exc
        body["_seconds"] = time.perf_counter() - t0
        return dict(body)

    def ask(self, question: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        """Return the response body plus `_seconds`, `_headers` and `_error`. A timeout or a
        5xx is returned as an error row, not raised: the question counts at the timeout."""
        t0 = time.perf_counter()
        try:
            r = self.http.post(f"{self.url}/api/ask", json={"question": question},
                               headers=headers, timeout=timeout)
            elapsed = time.perf_counter() - t0
            if r.status_code >= 400:
                return {"_seconds": elapsed, "_error": f"http {r.status_code}", "_headers": {}}
            body = r.json()
            body["_seconds"] = elapsed
            body["_headers"] = {k.lower(): v for k, v in r.headers.items()}
            return dict(body)
        except httpx.TimeoutException:
            return {"_seconds": timeout, "_error": "timeout", "_headers": {}}
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError(f"/api/ask unreachable: {exc}") from exc

    def target_info(self) -> dict[str, Any]:
        """Which release and collection this API is serving (from /readyz `checks`)."""
        try:
            r = self.http.get(f"{self.url}/readyz", timeout=30.0)
            body = r.json() if r.content else {}
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError(f"{self.url}/readyz unreachable: {exc}") from exc
        checks = body.get("checks") or {}
        return {"url": self.url, "release_id": checks.get("release_id"),
                "collection": checks.get("collection"), "revision": checks.get("revision"),
                "embed_model": checks.get("embed_model"), "embed_version": checks.get("embed_version"),
                "app_version": r.headers.get("x-rahbar-version")}
