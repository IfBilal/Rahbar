# Trace samples

A curated sample of the one-JSON-line-per-query traces written by the API (the full set lives on the
`ragops-traces` volume and in `kubectl logs`). `samples.jsonl` has one record per line, each with an added
`sample_label`; `prompts/` holds the stored prompts they point to. Read one with the trace tool, offline:

```bash
python -m ragops.trace.show <trace_id> --traces traces            # fields, then the exact prompt and context
python -m ragops.trace.summary --traces traces                    # metrics over these samples
```

| sample_label | what it shows |
| --- | --- |
| `baseline-g001-answered` | a normal cited answer on the baseline release (R1-nomic) |
| `baseline-g024-wrong-answer` | an answer the judge called supported although the retrieved text does not say it |
| `g025-abstained` | the abstained answer used for the D5 root cause (`docs/a3-evidence/D/D5-root-cause.md`) |
| `after-undo-R3-minilm` | the trace after `kubectl rollout undo`: previous collection and embedding version |
| `b08-injection-neutralised` | the Batch B parking policy with the planted instruction: the rail neutralised it (guardrail action in the trace) and the answer is the true fee |
| `rebuilt-cluster-parking-injection-neutralised` | the same parking question on the rebuilt cluster (trace `dd8f4789...`, 2026-11-25 18:07 UTC, 768-dimension embeddings, `retrieval.reranked_order`, `prompt.template_version`); same stored prompt as `b08-injection-neutralised` |
