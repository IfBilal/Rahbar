# What went wrong on the machine, 25 Nov (so the numbers can be read honestly)

All measurements come from one CPU-only laptop. Three things happened to it during the work; none changed a quality
metric, but they affect timings.

1. **Suspend, 24-25 Nov.** On battery, the laptop went to sleep overnight in the middle of baseline run 2. That run was
   discarded and repeated (`docs/a3-evidence/B/run2-stalled-by-suspend.md`). Sleep was blocked afterwards with
   `systemd-inhibit`.
2. **Reboot and full disk, 25 Nov about 18:50 PKT.** The battery ran out during the E4 work. After the reboot the disk was
   at 99 percent (2 GB free), which blocked `minikube start`. Space was freed by deleting unused Docker images of other
   projects (re-downloadable; nothing a running container used was touched) and minikube was started with `--force`. The
   cluster volumes survived: the ledger, the 14 quarantined files, the archive and Chroma's 558 chunks were intact
   (`docs/a3-evidence/F/F8-pvc-survival.txt` shows the same property after deleting pods).
3. **Battery power during the E4-only suite.** Part of that run was on battery, so its latency (p95 736 s) is far above the
   baseline's 153-177 s. Latency from that run must not be compared with the gate's 225 s limit. The quality metrics of
   the run are deterministic (seeded, temperature 0) and are not affected.
