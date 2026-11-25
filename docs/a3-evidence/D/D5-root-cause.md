# D5: root cause of one abstained answer, from its trace only

Question g025 (baseline run 1, trace `d08cce5a76644beeab76f8b4eaa149b6`, `docs/a3-evidence/D/D5-root-cause-g025-trace.txt`):
"How does the last date for pulling out of a course differ between the 2023 rules and the 2026 handbook?"

1. The trace says `status=abstained`, `abstain_reason=model_declined`: retrieval worked, the model declined to answer.
2. All 5 retrieved candidates are 2026 documents (`academic-rules@2026-06`, `prospectus@2026`, `student-handbook@2026-06`); none is the 2023 rules.
3. The filter in the trace is `{"superseded_filter": true}` with no `history_requested`: the 2023 version is archived (`superseded=true`) and was excluded by metadata.
4. The history switch did not fire: the API turns it on for words such as older, previous, earlier or "before 20xx" (`wants_history` in `api/app/retrieval/chroma.py`), and "the 2023 rules" contains none of them.
5. With only 2026 passages in the prompt the model could not compare the versions and said so. The cause is the version filter plus the trigger vocabulary, not retrieval quality or the model. Fix: also trigger on a year earlier than the document set's current version, or let a question that names two versions search both.
