# Baseline run 2, first attempt: stalled by a laptop suspend (discarded)

`scripts/ragops/eval.sh suite baseline --suite-args "--batches A --repeat 2"` started at 2026-11-24 17:46 UTC.
Run 1 completed (`eval/results/20261124T174636Z_baseline.json`). Run 2 (`suite-20261124T185217Z-2`) had answered
5 questions when the laptop, running on battery, went to sleep at about 19:07 UTC. Ollama's log and the trace file both stop
there, and nothing happened for the next 8.5 hours. The client's timers did not run during the suspend, so the in-flight
request would have returned only a bogus timeout row. That would have distorted run 2's p95, so the attempt was deleted
and run 2 was repeated from the start as a single run, on the same machine and the same code, with sleep inhibited
(`systemd-inhibit --what=sleep:idle:handle-lid-switch`). The 5 traces of the stalled attempt remain in the traces volume
under run id `suite-20261124T185217Z-2`.
