"""System tests against a running RAHBAR (make system-test). Skipped unless RAHBAR_SYSTEM=1.

They exercise what only a real cluster can show: the Ingress routes, NetworkPolicy really
enforced by Calico, readiness behaviour, and the service surviving a deleted pod. The
disruptive ones (pin mismatch) also need RAHBAR_DISRUPTIVE=1 and restore the cluster after.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RAHBAR_SYSTEM") != "1",
                                reason="needs a running cluster: RAHBAR_SYSTEM=1")
NS = "rahbar"
IP = os.environ.get("INGRESS_IP", "")


def kubectl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, check=check,
                          timeout=600)


def ask(question: str) -> dict:
    req = urllib.request.Request(f"http://{IP}/api/ask", json.dumps({"question": question}).encode(),
                                 {"Host": "rahbar.local", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def pod(label: str) -> str:
    return kubectl("get", "pod", "-n", NS, "-l", f"app={label}", "--field-selector",
                   "status.phase=Running", "-o", "jsonpath={.items[0].metadata.name}").stdout


def test_ingress_serves_the_ui_and_the_api() -> None:
    req = urllib.request.Request(f"http://{IP}/", headers={"Host": "rahbar.local"})
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.status == 200 and b"<html" in r.read().lower()
    r = ask("What minimum CGPA does an undergraduate need to avoid academic warning?")
    retrieved = {(x["source"], x["section"], x["page"]) for x in r["retrieved"]}
    assert r["retrieved"]
    assert all((c["source"], c["section"], c["page"]) in retrieved for c in r["citations"])


def test_the_absent_topic_is_declined() -> None:
    r = ask("Are hostel residents allowed to have guests stay overnight?")
    assert r["answered_from_context"] is False and r["citations"] == []


def test_three_api_endpoints_behind_the_service() -> None:
    ips = kubectl("get", "endpoints", "api", "-n", NS,
                  "-o", "jsonpath={.subsets[*].addresses[*].ip}").stdout.split()
    assert len(ips) >= 3


def _reach(from_label: str, url: str) -> bool:
    """Run an HTTP GET from inside a pod with `from_label`; True if it connects."""
    name = pod(from_label)
    if from_label == "ui":     # nginx alpine: busybox wget
        cmd = ["wget", "-T", "4", "-q", "-O", "-", url]
    else:                      # python images
        cmd = ["python", "-c", f"import urllib.request as u; u.urlopen('{url}', timeout=4)"]
    return kubectl("exec", "-n", NS, name, "--", *cmd, check=False).returncode == 0


def test_network_policy_blocks_ui_to_chroma_and_allows_api_to_chroma() -> None:
    assert not _reach("ui", "http://chroma:8000/api/v2/heartbeat")
    assert _reach("api", "http://chroma:8000/api/v2/heartbeat")


def test_network_policy_blocks_ui_to_redis() -> None:
    assert not _reach("ui", "http://redis:6379/")


def test_deleting_an_api_pod_does_not_interrupt_answers() -> None:
    victim = pod("api")
    question = "What is the deadline to withdraw from a course?"
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        futures = [ex.submit(ask, question) for _ in range(4)]
        kubectl("delete", "pod", victim, "-n", NS, "--wait=false")
        futures += [ex.submit(ask, question) for _ in range(4)]
        results = [f.result() for f in futures]
    assert all(r["retrieved"] for r in results)
    kubectl("rollout", "status", "deployment/api", "-n", NS, "--timeout=300s")


@pytest.mark.skipif(os.environ.get("RAHBAR_DISRUPTIVE") != "1",
                    reason="changes the ConfigMap; set RAHBAR_DISRUPTIVE=1")
def test_changing_the_embedding_model_on_the_api_only_blocks_readiness() -> None:
    original = kubectl("get", "configmap", "rahbar-config", "-n", NS,
                       "-o", "jsonpath={.data.EMBED_MODEL}").stdout
    try:
        kubectl("set", "env", "deployment/api", "-n", NS, "EMBED_MODEL=mxbai-embed-large")
        # the rollout must NOT complete: the new pod stays unready (expected timeout)
        stuck = kubectl("rollout", "status", "deployment/api", "-n", NS, "--timeout=90s",
                        check=False)
        assert stuck.returncode != 0
        pods = json.loads(kubectl("get", "pods", "-n", NS, "-l", "app=api", "-o", "json").stdout)
        new = [p for p in pods["items"]
               if any(e.get("value") == "mxbai-embed-large"
                      for c in p["spec"]["containers"] for e in c.get("env", []))]
        assert new, "no pod with the changed model was created"
        for p in new:
            ready = [c["ready"] for c in p["status"].get("containerStatuses", [])]
            assert ready == [False]
            logs = kubectl("logs", "-n", NS, p["metadata"]["name"]).stdout
            assert "embedding model mismatch" in logs and original in logs
        # maxUnavailable: 0 kept the three good pods serving the whole time
        ips = kubectl("get", "endpoints", "api", "-n", NS,
                      "-o", "jsonpath={.subsets[*].addresses[*].ip}").stdout.split()
        assert len(ips) >= 3
    finally:
        kubectl("set", "env", "deployment/api", "-n", NS, "EMBED_MODEL-")
        kubectl("rollout", "status", "deployment/api", "-n", NS, "--timeout=600s")
