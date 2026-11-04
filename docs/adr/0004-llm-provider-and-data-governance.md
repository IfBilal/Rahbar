# ADR 0004: Pluggable LLM provider, the embedding pin, and data governance

## Status
Accepted · 4 November 2026 · `ollama-host` fully supported; `hosted` implemented and
unit-tested; `stub` for tests and CI

## Context
The generator must be swappable without touching the pipeline. It must produce
schema-valid JSON every time, at low temperature, with citations. The embedding model
must be identical for the indexer and the API: vectors from two models are not
comparable, and the failure is silent. The corpus is public, but documents and
questions are untrusted text. Our laptop has no GPU and runs minikube in 6 GB.

## Decision
**Provider behind one interface.** `LLMProvider.generate(question, passages,
retry_reason)` in `api/app/providers/llm/base.py`, selected by `LLM_PROVIDER` in the
ConfigMap. A new provider is one file:
- `ollama-host` (default): Ollama on the laptop, reached at `host.minikube.internal:11434`,
  model `llama3.2:3b`. Decoding is constrained with Ollama's `format` set to the `Answer`
  JSON schema. Temperature 0.2. Context 4096 tokens.
- `hosted`: any OpenAI-compatible endpoint (Groq, OpenRouter, ...), JSON mode via
  `response_format`, key from the `rahbar-secret` Secret created on the command line.
- `stub`: deterministic, no network. Every unit test and the CI gate use it.

**Enforce, then validate.** The schema constrains decoding, then `Answer.model_validate_json`
checks the result, then `services/guard.py` checks what a schema cannot: every citation
must name a passage retrieved for this request, evidence markers must point at real
passages, and a grounded answer must cite something. One retry with the rejection reason
fed back, then a canned answer. A user never sees a 500.

**Temperature 0.2** (ConfigMap, with a one-line reason): facts and JSON want
near-deterministic decoding, and 0 does not cure hallucination when evidence is absent.

**The embedding pin.** `EMBED_MODEL` (`nomic-embed-text`) is one ConfigMap key read by the
indexer Job and the API. The indexer records the model name and the observed vector
dimension (768) in the collection metadata. The API compares them with its own setting at
startup (logged) and on every `/readyz` (503 on mismatch, the pod stays 0/1 READY), and
compares the query vector's dimension on every request. The nomic task prefixes
(`search_document:` / `search_query:`) derive from the model name on both sides, so they
cannot drift either.

**Data governance.**
- Corpus: public FAST-NUCES pages and PDFs only, never SLATE, Flex or anything behind a
  login. We commit `corpus/MANIFEST.md` (URL + SHA-256) and the fetch script, never the PDFs.
- Untrusted text: retrieved passages and the question are wrapped in `<evidence>` and
  `<question>` tags, `<` inside them is neutralised so no tag can be closed from inside,
  and instruction-like spans ("ignore all previous instructions ...") are replaced with a
  marker before the model sees them. Output is never passed to `eval` or used to build a
  query.
- Logs carry chunk ids, scores and flags, never the question text, the passage text or
  the model's `reasoning`. The API key never appears in the settings `repr`.
- No personal data is collected; the API has no user accounts or sessions.

**Contract changes** (STARTER.md asks for an ADR for these). All are additive, with
defaults, so the UI, `eval/run_eval.py` and the starter tests are unaffected:
`AskResponse.cached: bool = False` (drives the UI's cache chip); `Passage.doc_version` and
`Passage.superseded` (the prompt labels passages current or superseded);
`LLMProvider.generate(..., retry_reason=None)`; `extract(..., ocr=True)` (failure
experiment A).

## Options considered
- **ollama-incluster**: needs 8 GB for minikube and a startupProbe with failureThreshold 30
  while weights load. Our 6 GB laptop budget goes to the three API replicas instead.
- **A hosted model as default**: faster, but our corpus questions would leave the machine,
  and CI would depend on a third party.
- **No `format`, parse prose**: works most of the time, which is the problem.

## Consequences
- Easier: the provider is one config key; CI is deterministic; schema failures cost one
  retry, never an error page.
- Harder: on our CPU, a 3B model answers in minutes. We cut the prompt to the best three
  passages and sized every timeout for it (Ingress 600 s, provider 600 s).
- Watch: a 3B model can still misjudge whether evidence answers the question. Abstention
  therefore has two layers (relevance floor, then the model) and the eval gates it at 100%.
