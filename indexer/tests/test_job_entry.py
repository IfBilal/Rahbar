"""indexer/job_entry.sh: the exit-code mapping and the wait for Chroma (docs/a3-ragops/14 section 1)."""

from __future__ import annotations

import os
import stat
import sys
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "job_entry.sh"


def run(tmp_path: Path, python_exit: int, wait: str = "0") -> subprocess.CompletedProcess[str]:
    """Run the script with a fake `python` that records its arguments and exits with `python_exit`."""
    fake = tmp_path / "python"
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> {tmp_path}/calls\nexit {python_exit}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "CHROMA_WAIT_SECONDS": wait}
    return subprocess.run(["sh", str(SCRIPT), "sync"], capture_output=True, text=True, env=env, timeout=30)


def test_quarantine_exit_1_is_success_and_other_codes_stay_failures(tmp_path: Path) -> None:
    assert run(tmp_path, 0).returncode == 0
    r = run(tmp_path, 1)
    assert r.returncode == 0 and "exit 1 mapped to 0" in r.stdout
    assert run(tmp_path, 3).returncode == 3          # fatal: Chroma/Ollama down, lock held
    assert run(tmp_path, 4).returncode == 4          # unknown restore/delete target
    assert "-m pipeline.run sync" in (tmp_path / "calls").read_text()


def test_it_waits_for_chroma_before_writing_and_runs_anyway_on_timeout(tmp_path: Path) -> None:
    """With nothing listening, a 1 s wait times out, says so, and still runs the pipeline (which then reports the
    real error); the point is that the heartbeat probe runs BEFORE the pipeline."""
    env_port = {**os.environ, "CHROMA_HOST": "127.0.0.1", "CHROMA_PORT": "9"}
    # the probe must run with the real python, but `-m pipeline.run` must not run for real: shim by argument
    shim = tmp_path / "python"
    shim.write_text(f"#!/bin/sh\ncase \"$1\" in -m) echo \"$@\" >> {tmp_path}/calls; exit 0;; *) exec {sys.executable} \"$@\";; esac\n")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    env = {**env_port, "PATH": f"{tmp_path}:{os.environ['PATH']}", "CHROMA_WAIT_SECONDS": "1"}
    r = subprocess.run(["sh", str(SCRIPT), "sync"], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0
    assert "chroma did not answer in time" in r.stdout
    assert (tmp_path / "calls").read_text().strip() == "-m pipeline.run sync"
