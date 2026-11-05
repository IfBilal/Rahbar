# AI usage

We used AI heavily, and we say so specifically. Honest attribution is the rule in section 8
of the case study, and this file is that attribution. Everything listed here was run,
measured and reviewed by us; we can explain every line of it.

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| **Claude Code (Anthropic, Claude Opus model), as a coding agent in the terminal**, directed by Taimoor | Most of the implementation: the five indexer stages, the Chroma retriever, Ollama and hosted providers, prompt, citation guard, semantic cache, readiness and metrics; `eval/run_eval.py`'s four functions; all Dockerfiles, Kubernetes manifests, the two workflows and the helper scripts; the test suites (about 250 tests); first drafts of the ADRs and of these reports. | The agent's first versions were wrong in ways that only running the system showed. Each change below is in the git history with the measurement that forced it. |
| An AI chat assistant, used by Bilal for planning (the planning pack committed in `f0f080c`) | The 25 planning guides in `docs/` (`AGENTS.md`, `PRD.md`, `PHASES.md`, `CRITICAL-PATH.md`, `INTERFACE-CONTRACTS.md`, ...): the requirement traceability R01–R30, the work breakdown, the two-developer split, candidate chunk settings (300/40, 400/60, 550/80), the generation-pointer idea for safe re-indexing. | We used the plans as checklists, not as truth: every candidate value was measured before use, and the PDF overruled the plans where they differed. The draft ADRs were moved to their required paths and rewritten as accepted decisions. The plan's "versioned collections + registry pointer" proposal was implemented and tested. |
| **OpenAI Codex**, directed by Bilal | Reviewed the release, configured branch protection, diagnosed the CD smoke-test failure, and implemented the CD and retrieval-ranking fixes with a regression test. | The team must review the changes and validate the new deployment and real-model evaluation; existing measurements predate these fixes. |
| GitHub Copilot | Not reported as used. | |

## What we changed after running it (AI output → measured fix)

1. **Embeddings collapsed capitalised words.** Retrieval missed "Rector's List" and the
   Islamabad faculty table. Our cache-threshold experiment then showed cosine **1.0000**
   between "Rector's List" and "Dean's List", and between BS and MS fee questions. Ollama
   0.17 feeds nomic-embed-text, an uncased model, without lowercasing, so every capitalised
   word became `[UNK]`. We now lowercase on both sides as part of the embedding pin
   (`indexer/pipeline/embed.py::prepare_document`, `api/app/retrieval/embedder.py::prepare_query`)
   and re-measured everything (`docs/evidence/cache-threshold-before-lowercase-fix.txt`).
2. **The semantic cache served answers made under old settings.** After a ConfigMap change
   (new relevance floor, different provider), cached answers kept coming back
   (`cached: true` on a question that should now abstain). The cache scope now includes a
   digest of every answer-shaping setting.
3. **Chroma crashed on start**: `invalid type: found string "tcp://10.96.96.97:8000",
   expected u16 for key "PORT"`. Kubernetes injects `CHROMA_PORT=tcp://...` for a Service
   named `chroma`, and Chroma reads `CHROMA_*` as its own config. Fixed with
   `enableServiceLinks: false` on every pod, with a test.
4. **API pods were killed by the startup probe while Chroma was down.** The Chroma client
   uses `httpx.Client(timeout=None)`, so the startup pin check hung forever against a
   Service with no ready endpoint. We added a 2 s heartbeat, a 5 s client timeout, and moved
   the startup check into a thread.
5. **The 3B model obeyed the planted injection** in about one reply in five ("attendance
   is optional for students repeating a course"). It also wrote `"answer": "low"`. We spelled
   out the JSON shape in the prompt, repeated the rule after the question, and added a
   deterministic layer that removes instruction-like spans from evidence before the model
   sees them. Measured afterwards: 0 obedient replies in 10 runs.
6. **The chunker silently lost its overlap** when a unit filled the whole budget, and the
   cleaner would have deleted clause lines that repeat on every page. Both were caught by
   tests written first, then fixed (`indexer/tests/test_chunk.py`, `test_clean.py`).
7. **Extraction was reading invisible text.** The handbooks carry the facing page's text
   off the page box, and the prospectus is three columns. Both garbled clauses until the
   extractor kept only the page box and split columns at empty gutters.
8. **Trivy failed the api and indexer images** on fixable HIGH CVEs in the starter's pins
   (starlette via fastapi 0.115, pypdf 5.4, pdfminer via pdfplumber 0.11.6, and the
   setuptools copy that pip vendors).
   We bumped the pins and removed pip from the runtime images.

9. **Numbered evidence collided with numbered rules.** In the first real-model evaluation
   the model cited `[6]` and `[12]` with three passages in front of it: it was copying
   clause and list numbers from the text. The guard rejected those replies, so an
   answerable question fell back to the canned answer. Evidence is now labelled A, B, C.
10. **The cache outlived a prompt change.** The second evaluation was served the first
    run's answers (`docs/evidence/eval-run2-cache-hits.json`, 15 hits in about 0.1 s each)
    because the cache key did not include the prompt. It does now.

## What we did not let the AI decide
- The corpus choice and the absent topic. Every golden answer was read off the source
  documents before any tuning; the golden set was committed before the chunk sweep.
- Every tuned number (chunk size, relevance floor, cache threshold, resource limits) comes
  from a measurement committed under `docs/evidence/`.
- What counts as passing. The CI gate thresholds are the case study's, unchanged.
