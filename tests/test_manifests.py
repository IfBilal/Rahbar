"""Architecture tests: the rendered Kubernetes manifests keep every section 4 promise.

They run `kustomize build` on both overlays (skipped if kustomize is absent) and assert
on the objects, so a manifest edit that breaks a requirement fails CI, not a demo.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("kustomize") is None, reason="needs kustomize")


def render(overlay: str) -> list[dict]:
    out = subprocess.run(["kustomize", "build", str(ROOT / "k8s" / "overlays" / overlay)],
                         check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


@pytest.fixture(scope="module", params=["dev", "prod", "ci"])
def objs(request) -> list[dict]:
    return render(request.param)


def one(objs: list[dict], kind: str, name: str) -> dict:
    found = [o for o in objs if o["kind"] == kind and o["metadata"]["name"] == name]
    assert len(found) == 1, f"{kind}/{name}"
    return found[0]


def pod_spec(o: dict) -> dict:
    if o["kind"] == "CronJob":
        return o["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    return o["spec"]["template"]["spec"]


WORKLOADS = ("Deployment", "StatefulSet", "Job", "CronJob")


def test_every_required_object_exists(objs) -> None:
    for kind, name in [("Namespace", "rahbar"), ("Deployment", "api"), ("Deployment", "ui"),
                       ("StatefulSet", "chroma"), ("Deployment", "redis"),
                       ("PersistentVolumeClaim", "redis-data"), ("Job", "indexer"),
                       ("CronJob", "reindex"), ("Ingress", "rahbar"),
                       ("ConfigMap", "rahbar-config"), ("NetworkPolicy", "default-deny-all"),
                       ("HorizontalPodAutoscaler", "api")]:
        one(objs, kind, name)
    assert sorted(o["metadata"]["name"] for o in objs if o["kind"] == "Service") == \
        ["api", "chroma", "redis", "ui"]


def test_nothing_lands_in_the_default_namespace(objs) -> None:
    for o in objs:
        if o["kind"] != "Namespace":
            assert o["metadata"].get("namespace") == "rahbar", o["metadata"]["name"]


def test_the_secret_placeholder_is_never_applied(objs) -> None:
    assert not [o for o in objs if o["kind"] == "Secret"]
    text = (ROOT / "k8s" / "base" / "secret.placeholder.yaml").read_text()
    assert "REPLACE_ME" in text and not re.search(r"^data:", text, re.M)   # no base64 values


def test_api_has_three_replicas_three_probes_and_zero_unavailable(objs) -> None:
    api = one(objs, "Deployment", "api")
    assert api["spec"]["replicas"] == 3
    assert api["spec"]["strategy"]["rollingUpdate"] == {"maxSurge": 1, "maxUnavailable": 0}
    c = pod_spec(api)["containers"][0]
    assert c["startupProbe"]["httpGet"]["path"] == "/healthz"
    assert c["startupProbe"]["failureThreshold"] == 30
    assert c["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert c["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert c["lifecycle"]["preStop"]["exec"]["command"][0] == "sleep"
    assert pod_spec(api)["terminationGracePeriodSeconds"] > 10


def test_every_container_has_requests_and_limits(objs) -> None:
    for o in (o for o in objs if o["kind"] in WORKLOADS):
        spec = pod_spec(o)
        for c in spec.get("containers", []) + spec.get("initContainers", []):
            res = c.get("resources", {})
            for part in ("requests", "limits"):
                assert {"cpu", "memory"} <= set(res.get(part, {})), f"{o['metadata']['name']}/{c['name']}"


def test_every_container_is_hardened(objs) -> None:
    for o in (o for o in objs if o["kind"] in WORKLOADS):
        spec = pod_spec(o)
        assert spec["securityContext"]["runAsNonRoot"] is True, o["metadata"]["name"]
        assert spec["automountServiceAccountToken"] is False
        assert spec["serviceAccountName"] != "default"
        # a Service named chroma injects CHROMA_PORT=tcp://..., which crashes Chroma itself
        assert spec["enableServiceLinks"] is False, o["metadata"]["name"]
        for c in spec.get("containers", []) + spec.get("initContainers", []):
            sc = c["securityContext"]
            assert sc["readOnlyRootFilesystem"] is True and sc["allowPrivilegeEscalation"] is False
            assert sc["capabilities"]["drop"] == ["ALL"]


def test_dedicated_service_accounts_without_tokens(objs) -> None:
    sas = {o["metadata"]["name"]: o for o in objs if o["kind"] == "ServiceAccount"}
    assert set(sas) == {"api", "ui", "indexer", "chroma", "redis"}
    assert all(sa["automountServiceAccountToken"] is False for sa in sas.values())


def test_chroma_is_a_statefulset_with_a_claim_template(objs) -> None:
    chroma = one(objs, "StatefulSet", "chroma")
    assert chroma["spec"]["replicas"] == 1
    assert chroma["spec"]["volumeClaimTemplates"][0]["metadata"]["name"] == "data"
    assert pod_spec(chroma)["containers"][0]["image"] == "chromadb/chroma:1.0.12"
    assert not [o for o in objs if o["kind"] == "Deployment" and o["metadata"]["name"] == "chroma"]


def test_redis_persists_to_its_claim(objs) -> None:
    redis = one(objs, "Deployment", "redis")
    spec = pod_spec(redis)
    assert spec["volumes"][0]["persistentVolumeClaim"]["claimName"] == "redis-data"
    assert "--appendonly" in spec["containers"][0]["command"]


def test_data_tier_services_are_cluster_internal(objs) -> None:
    for o in (o for o in objs if o["kind"] == "Service"):
        assert o["spec"]["type"] == "ClusterIP", o["metadata"]["name"]


def test_indexer_job_and_cronjob_share_image_and_args(objs) -> None:
    job, cron = one(objs, "Job", "indexer"), one(objs, "CronJob", "reindex")
    assert job["spec"]["template"]["spec"]["restartPolicy"] == "OnFailure"
    assert job["spec"]["backoffLimit"] >= 1
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"
    a, b = pod_spec(job), pod_spec(cron)
    for key in ("containers", "initContainers"):
        assert [(c["image"], c.get("args"), c.get("command")) for c in a.get(key, [])] == \
               [(c["image"], c.get("args"), c.get("command")) for c in b.get(key, [])]


def test_ingress_routes_api_and_ui_on_one_host(objs) -> None:
    rule = one(objs, "Ingress", "rahbar")["spec"]["rules"][0]
    paths = {p["path"]: p["backend"]["service"]["name"] for p in rule["http"]["paths"]}
    assert paths == {"/api": "api", "/": "ui"} and rule["host"] == "rahbar.local"


def test_configmap_carries_every_tunable_and_the_pin(objs) -> None:
    data = one(objs, "ConfigMap", "rahbar-config")["data"]
    for key in ("CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", "RELEVANCE_FLOOR", "CACHE_THRESHOLD",
                "TEMPERATURE", "EMBED_MODEL", "LLM_PROVIDER", "CHROMA_HOST"):
        assert data.get(key), key
    assert 0 <= float(data["TEMPERATURE"]) <= 0.3


def test_api_and_indexer_read_the_pin_from_the_same_configmap(objs) -> None:
    for o in (one(objs, "Deployment", "api"), one(objs, "Job", "indexer")):
        c = pod_spec(o)["containers"][0]
        assert {"configMapRef": {"name": "rahbar-config"}} in c["envFrom"]
        assert not any(e["name"] == "EMBED_MODEL" for e in c.get("env", []))


def test_hpa_scales_api_from_three_to_eight(objs) -> None:
    hpa = one(objs, "HorizontalPodAutoscaler", "api")
    assert hpa["apiVersion"] == "autoscaling/v2"
    assert (hpa["spec"]["minReplicas"], hpa["spec"]["maxReplicas"]) == (3, 8)
    api = pod_spec(one(objs, "Deployment", "api"))["containers"][0]
    assert api["resources"]["requests"]["cpu"]       # the HPA's denominator


def _policies(objs: list[dict]) -> list[dict]:
    return [o for o in objs if o["kind"] == "NetworkPolicy"]


def _allows_ingress(objs, target: str, source: str, port: int) -> bool:
    for p in _policies(objs):
        if p["spec"]["podSelector"].get("matchLabels", {}).get("app") != target:
            continue
        for rule in p["spec"].get("ingress", []):
            ports = {x["port"] for x in rule.get("ports", [])}
            sources = {f.get("podSelector", {}).get("matchLabels", {}).get("app")
                       for f in rule.get("from", [])}
            if port in ports and source in sources:
                return True
    return False


def test_network_is_deny_by_default(objs) -> None:
    deny = one(objs, "NetworkPolicy", "default-deny-all")["spec"]
    assert deny["podSelector"] == {} and set(deny["policyTypes"]) == {"Ingress", "Egress"}
    assert "ingress" not in deny and "egress" not in deny


def test_network_graph_matches_the_architecture(objs) -> None:
    assert _allows_ingress(objs, "chroma", "api", 8000)
    assert _allows_ingress(objs, "chroma", "indexer", 8000)
    assert _allows_ingress(objs, "redis", "api", 6379)
    assert _allows_ingress(objs, "api", "ui", 8000)
    assert not _allows_ingress(objs, "chroma", "ui", 8000)      # the ui must not reach chroma
    assert not _allows_ingress(objs, "redis", "indexer", 6379)  # only the api reaches redis


def test_dns_egress_is_allowed(objs) -> None:
    dns = one(objs, "NetworkPolicy", "allow-dns-egress")["spec"]["egress"][0]
    assert {(p["protocol"], p["port"]) for p in dns["ports"]} == {("UDP", 53), ("TCP", 53)}


def test_images_are_pinned_and_never_latest(objs) -> None:
    for o in (o for o in objs if o["kind"] in WORKLOADS):
        spec = pod_spec(o)
        for c in spec.get("containers", []) + spec.get("initContainers", []):
            assert ":" in c["image"] and not c["image"].endswith(":latest"), c["image"]


def test_prod_overlay_pulls_sha_tagged_images_from_docker_hub() -> None:
    for o in (o for o in render("prod") if o["kind"] in ("Deployment", "Job")):
        image = pod_spec(o)["containers"][0]["image"]
        if "rahbar-" in image:
            repo, tag = image.rsplit(":", 1)
            assert repo.startswith("docker.io/") and len(tag) >= 7 and tag != "latest"
