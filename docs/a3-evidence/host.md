# Host record (A3 measured runs)

Every reported A3 number is produced on this one machine (Taimoor's laptop), one heavy
run at a time. Raw command output: `host/step1-raw.txt` (captured 24 Nov 2026).

| Item | Value |
|---|---|
| CPU | 13th Gen Intel Core i7-1355U, 10 cores / 12 threads |
| RAM | 32 GB (about 21 GB available at capture) |
| GPU | **None usable.** Intel Iris Xe only; `nvidia-smi` not installed |
| Ollama | 0.17.6 on the host, `OLLAMA_HOST=192.168.49.1:11434` (the minikube gateway), `OLLAMA_KEEP_ALIVE=30m` |
| Processor in use | `ollama ps` says **100% CPU** for `llama3.2:3b` |
| Models | `llama3.2:3b`, `nomic-embed-text`, `mxbai-embed-large`, `all-minilm` |
| Power | on AC, `powerprofilesctl` = performance |
| Cluster | minikube, docker driver, Calico, 8 GB, 4 CPUs, Kubernetes v1.37.0 |

## Deviation from the hand-off

`docs/a3-ragops/15-HANDOFF-TAIMOOR.md` assumed a GPU laptop. This one has no GPU, so
generation and the judge run on CPU. Consequences, stated rather than hidden:

* Absolute latencies are slower than a GPU run would give. The `p95_latency` gate
  threshold is derived from baseline runs on this same machine, so the gate is
  consistent with itself; it is not comparable to Bilal's CPU laptop or to any GPU.
* Runs are sequential (one Ollama, one heavy job at a time) so p95 is not distorted by
  contention.
