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


@pytest.fixture(scope="module", params=["dev", "prod", "ci", "incluster"])
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
                       ("PersistentVolumeClaim", "redis-data"), ("Job", "ingest"),
                       ("CronJob", "ingest"), ("Ingress", "rahbar"),
                       ("PersistentVolumeClaim", "ragops-data"),
                       ("PersistentVolumeClaim", "ragops-traces"),
                       ("PersistentVolumeClaim", "ragops-results"),
                       ("ConfigMap", "ragops-config"), ("ConfigMap", "ragops-gate"),
                       ("ConfigMap", "ragops-eval-target"),
                       ("ConfigMap", "rahbar-config"), ("NetworkPolicy", "default-deny-all"),
                       ("HorizontalPodAutoscaler", "api")]:
        one(objs, kind, name)
    assert {"api", "chroma", "redis", "ui"} <= \
        {o["metadata"]["name"] for o in objs if o["kind"] == "Service"}


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
    # longer than the slowest generation we measured (~190 s), or rollouts drop answers
    assert pod_spec(api)["terminationGracePeriodSeconds"] >= 200
    # pods wait (unready) for the first index; a full index takes up to ~800 s measured
    assert api["spec"]["progressDeadlineSeconds"] >= 1500


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
    assert {"api", "ui", "indexer", "chroma", "redis", "ragops-eval", "ragops-loader"} <= set(sas)
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


def test_ingest_job_and_cronjob_share_image_and_args(objs) -> None:
    job, cron = one(objs, "Job", "ingest"), one(objs, "CronJob", "ingest")
    assert job["spec"]["template"]["spec"]["restartPolicy"] == "OnFailure"
    assert job["spec"]["backoffLimit"] >= 1
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"          # never two writers at once
    a, b = pod_spec(job), pod_spec(cron)
    for key in ("containers", "initContainers"):
        assert [(c["image"], c.get("args"), c.get("command")) for c in a.get(key, [])] == \
               [(c["image"], c.get("args"), c.get("command")) for c in b.get(key, [])]
    assert a["containers"][0]["args"] == ["sync"]


def test_the_a2_indexer_job_and_reindex_cronjob_are_retired(objs) -> None:
    """One definition of the writer: the A3 ingest Job and CronJob replace them."""
    assert not [o for o in objs if (o["kind"], o["metadata"]["name"]) in
                {("Job", "indexer"), ("CronJob", "reindex")}]


def test_ingest_writes_the_data_lake_volume_and_nothing_else_mounts_it_rw(objs) -> None:
    ing = pod_spec(one(objs, "Job", "ingest"))
    assert {"name": "data", "persistentVolumeClaim": {"claimName": "ragops-data"}} in ing["volumes"]
    api = pod_spec(one(objs, "Deployment", "api"))
    assert not [v for v in api["volumes"] if v.get("persistentVolumeClaim", {}).get("claimName")
                == "ragops-data"], "the API must not mount the data lake"


def test_ingress_routes_api_and_ui_on_one_host(objs) -> None:
    rule = one(objs, "Ingress", "rahbar")["spec"]["rules"][0]
    paths = {p["path"]: p["backend"]["service"]["name"] for p in rule["http"]["paths"]}
    # /api/retrieve (the evaluation endpoint) is sent to the UI: it is not public (see below)
    assert paths == {"/api/retrieve": "ui", "/api": "api", "/": "ui"} and rule["host"] == "rahbar.local"


def test_configmap_carries_every_tunable_and_the_pin(objs) -> None:
    data = one(objs, "ConfigMap", "rahbar-config")["data"]
    for key in ("CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", "RELEVANCE_FLOOR", "CACHE_THRESHOLD",
                "TEMPERATURE", "EMBED_MODEL", "LLM_PROVIDER", "CHROMA_HOST"):
        assert data.get(key), key
    assert 0 <= float(data["TEMPERATURE"]) <= 0.3


RELEASE_KEYS = ("RELEASE_ID", "CHROMA_COLLECTION", "EMBED_MODEL", "EMBED_VERSION",
                "RELEVANCE_FLOOR", "TOP_K")


def test_api_release_identity_is_in_the_pod_template_and_agrees_with_the_configmap(objs) -> None:
    """A3 F3: `kubectl rollout undo` only restores what is in the pod template, so the release
    keys are explicit env entries (they override envFrom). The ingest Job reads the same
    values from the ConfigMap, so the two copies must agree or the writer and reader drift."""
    api = pod_spec(one(objs, "Deployment", "api"))["containers"][0]
    env = {e["name"]: e.get("value") for e in api["env"]}
    for key in RELEASE_KEYS:
        assert env.get(key), key
    data = one(objs, "ConfigMap", "rahbar-config")["data"]
    for key in ("CHROMA_COLLECTION", "EMBED_MODEL", "TOP_K", "RELEVANCE_FLOOR"):
        assert env[key] == data[key], f"{key}: pod template {env[key]!r} vs ConfigMap {data[key]!r}"
    assert {"configMapRef": {"name": "rahbar-config"}} in api["envFrom"]
    ingest = pod_spec(one(objs, "Job", "ingest"))["containers"][0]
    assert {"configMapRef": {"name": "rahbar-config"}} in ingest["envFrom"]
    assert not any(e["name"] == "EMBED_MODEL" for e in ingest.get("env", []))   # one pin for the writer
    assert api["env"][-1]["valueFrom"]["fieldRef"]["fieldPath"] == "metadata.name"   # POD_NAME


def test_api_writes_traces_to_a_volume_and_has_the_evaluation_switches(objs) -> None:
    api = pod_spec(one(objs, "Deployment", "api"))
    assert {"configMapRef": {"name": "ragops-config"}} in api["containers"][0]["envFrom"]
    assert {"name": "traces", "persistentVolumeClaim": {"claimName": "ragops-traces"}} in api["volumes"]
    assert {"name": "traces", "mountPath": "/traces"} in api["containers"][0]["volumeMounts"]
    cfg = one(objs, "ConfigMap", "ragops-config")["data"]
    assert cfg["TRACE_DIR"] == "/traces" and cfg["EVAL_ENDPOINTS_ENABLED"] == "true"


def test_the_gate_configmap_is_the_committed_gate_file(objs) -> None:
    cm = one(objs, "ConfigMap", "ragops-gate")["data"]["gate.yaml"]
    assert yaml.safe_load(cm) == yaml.safe_load((ROOT / "ragops" / "config" / "gate.yaml").read_text())


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


def test_ui_may_call_only_the_api(objs) -> None:
    ui = one(objs, "NetworkPolicy", "ui-from-ingress")["spec"]
    targets = [(t["podSelector"]["matchLabels"]["app"], p["port"])
               for rule in ui["egress"] for t in rule["to"] for p in rule["ports"]]
    assert targets == [("api", 8000)]


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


def test_incluster_ollama_has_a_patient_startup_probe_and_a_weights_volume() -> None:
    objs = render("incluster")
    ollama = one(objs, "Deployment", "ollama")
    c = pod_spec(ollama)["containers"][0]
    assert c["startupProbe"]["failureThreshold"] == 30          # weights take minutes to load
    assert pod_spec(ollama)["volumes"][0]["persistentVolumeClaim"]["claimName"] == "ollama-models"
    data = one(objs, "ConfigMap", "rahbar-config")["data"]
    assert data["OLLAMA_URL"] == "http://ollama:11434" and data["LLM_PROVIDER"] == "ollama-incluster"
    assert _allows_ingress(objs, "ollama", "api", 11434)
    assert not _allows_ingress(objs, "ollama", "ui", 11434)


# ---------------------------------------------------------------- A3 standalone manifests (k8s/*.yaml)
def standalone(name: str) -> list[dict]:
    return [d for d in yaml.safe_load_all((ROOT / "k8s" / name).read_text()) if d]


def test_eval_job_fails_with_the_gate_and_mounts_the_lake_read_only() -> None:
    job = standalone("eval-job.yaml")[0]
    assert job["metadata"]["name"] == "eval" and job["spec"]["backoffLimit"] == 0
    spec = job["spec"]["template"]["spec"]
    assert spec["restartPolicy"] == "Never"           # a failed gate must not retry into a pass
    c = spec["containers"][0]
    mounts = {m["name"]: m for m in c["volumeMounts"]}
    assert mounts["data"]["readOnly"] is True and mounts["traces"]["readOnly"] is True
    assert mounts["gate"]["mountPath"] == "/config"
    assert {"name": "gate", "configMap": {"name": "ragops-gate"}} in spec["volumes"]
    assert c["command"] == ["/app/job_entry.sh"]
    assert not c["image"].endswith(":latest") and ":" in c["image"]
    assert "ttlSecondsAfterFinished" not in job["spec"]           # logs must outlive the screenshot


def test_candidate_is_isolated_from_live_traffic() -> None:
    dep, svc = standalone("candidate.yaml")
    assert dep["metadata"]["name"] == "api-candidate" and svc["metadata"]["name"] == "api-candidate"
    assert dep["spec"]["selector"]["matchLabels"] == {"app": "api-candidate"}
    assert dep["spec"]["strategy"]["rollingUpdate"] == {"maxSurge": 1, "maxUnavailable": 0}
    env = {e["name"]: e.get("value") for e in dep["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["REDIS_URL"] == ""                      # cache off: no cached answer hides a regression
    assert env["CHROMA_COLLECTION"] != "rahbar" and env["RELEASE_ID"] != "R1-nomic"
    assert svc["spec"]["selector"] == {"app": "api-candidate"} and svc["spec"]["type"] == "ClusterIP"


def test_loader_pod_has_no_network_and_all_three_volumes() -> None:
    pod = standalone("loader-pod.yaml")[0]
    claims = {v["persistentVolumeClaim"]["claimName"] for v in pod["spec"]["volumes"]
              if "persistentVolumeClaim" in v}
    assert claims == {"ragops-data", "ragops-traces", "ragops-results"}
    iso = one(render("dev"), "NetworkPolicy", "loader-isolation")["spec"]
    assert iso["podSelector"]["matchLabels"] == {"app": "ragops-loader"}
    assert "ingress" not in iso and "egress" not in iso      # deny: kubectl cp does not need the network


def test_every_standalone_pod_is_hardened_and_pinned() -> None:
    for name in ("eval-job.yaml", "candidate.yaml", "loader-pod.yaml", "coverage-job.yaml"):
        for o in standalone(name):
            if o["kind"] == "Service":
                continue
            spec = o["spec"] if o["kind"] == "Pod" else o["spec"]["template"]["spec"]
            assert spec["securityContext"]["runAsNonRoot"] is True, name
            assert spec["enableServiceLinks"] is False and spec["automountServiceAccountToken"] is False
            for c in spec["containers"]:
                assert c["securityContext"]["readOnlyRootFilesystem"] is True, name
                assert {"cpu", "memory"} <= set(c["resources"]["requests"]) and \
                    {"cpu", "memory"} <= set(c["resources"]["limits"]), name
                assert ":" in c["image"] and not c["image"].endswith(":latest"), name


def test_the_evaluation_job_can_reach_the_api_and_ollama_but_never_chroma_or_redis(objs) -> None:
    assert _allows_ingress(objs, "api", "ragops-eval", 8000)
    assert _allows_ingress(objs, "api-candidate", "ragops-eval", 8000)
    assert not _allows_ingress(objs, "chroma", "ragops-eval", 8000)      # read-only against Chroma, by network
    assert not _allows_ingress(objs, "redis", "ragops-eval", 6379)
    assert _allows_ingress(objs, "chroma", "api-candidate", 8000)         # the candidate reads its own collection
    assert not _allows_ingress(objs, "redis", "api-candidate", 6379)      # and has no cache
    ev = one(objs, "NetworkPolicy", "eval-policy")["spec"]
    targets = {(t.get("podSelector", {}).get("matchLabels", {}).get("app") or t["ipBlock"]["cidr"], p["port"])
               for r in ev["egress"] for t in r["to"] for p in r["ports"]}
    assert targets == {("api", 8000), ("api-candidate", 8000), ("192.168.49.1/32", 11434)}


def test_the_evaluation_endpoint_is_guarded_by_a_runtime_secret_and_not_routed_publicly(objs) -> None:
    """The Ingress routes /api to the API, so /api/retrieve and X-Eval-* need a token that is
    generated at run time (scripts/ragops/eval-token.sh) and read from a Secret, never from Git."""
    ref = {"secretKeyRef": {"name": "ragops-eval-token", "key": "token"}}
    api = pod_spec(one(objs, "Deployment", "api"))["containers"][0]
    assert {"name": "EVAL_TOKEN", "valueFrom": ref} in api["env"]
    for name in ("candidate.yaml", "eval-job.yaml"):
        o = standalone(name)[0]
        spec = o["spec"]["template"]["spec"]
        assert {"name": "EVAL_TOKEN", "valueFrom": ref} in spec["containers"][0]["env"], name
    rule = one(objs, "Ingress", "rahbar")["spec"]["rules"][0]["http"]["paths"]
    retrieve = next(p for p in rule if p["path"] == "/api/retrieve")
    assert retrieve["pathType"] == "Exact" and retrieve["backend"]["service"]["name"] == "ui"
    assert not [o for o in objs if o["kind"] == "Secret"]


def test_the_data_stores_accept_connections_only_from_named_workloads(objs) -> None:
    """The earlier 'eval cannot reach chroma' assertions only looked at rules that name a podSelector, so an
    allow-all ingress rule (no `from`, an ipBlock, a namespaceSelector, an empty podSelector) would have passed
    them. Every ingress rule of chroma and redis must name its sources explicitly."""
    allowed = {"chroma": {"api", "indexer", "api-candidate"}, "redis": {"api"}}
    for target, sources in allowed.items():
        policies = [p for p in _policies(objs) if p["spec"]["podSelector"].get("matchLabels", {}).get("app") == target]
        assert policies, target
        for p in policies:
            for rule in p["spec"].get("ingress", []):
                assert rule.get("from"), f"{p['metadata']['name']}: an ingress rule without `from` allows everyone"
                for f in rule["from"]:
                    assert set(f) == {"podSelector"} and f["podSelector"].get("matchLabels"), (p["metadata"]["name"], f)
                    assert f["podSelector"]["matchLabels"]["app"] in sources, (p["metadata"]["name"], f)


def test_only_the_baseline_policies_select_every_pod(objs) -> None:
    """A policy that selects all pods could grant the evaluation Job egress that eval-policy does not list."""
    selecting_all = {p["metadata"]["name"] for p in _policies(objs) if p["spec"]["podSelector"] == {}}
    assert selecting_all == {"default-deny-all", "allow-dns-egress"}


def test_the_evaluation_job_is_selected_only_by_its_own_policy(objs) -> None:
    for p in _policies(objs):
        sel = p["spec"]["podSelector"].get("matchLabels", {})
        if sel.get("app") == "ragops-eval":
            assert p["metadata"]["name"] == "eval-policy"


def test_the_standalone_containers_drop_all_capabilities_and_forbid_escalation() -> None:
    for name in ("eval-job.yaml", "candidate.yaml", "loader-pod.yaml", "coverage-job.yaml"):
        for o in standalone(name):
            if o["kind"] == "Service":
                continue
            spec = o["spec"] if o["kind"] == "Pod" else o["spec"]["template"]["spec"]
            for c in spec["containers"]:
                assert c["securityContext"]["allowPrivilegeEscalation"] is False, name
                assert c["securityContext"]["capabilities"]["drop"] == ["ALL"], name


def test_the_writer_and_the_reader_agree_on_the_embedding_version(objs) -> None:
    api = {e["name"]: e.get("value") for e in pod_spec(one(objs, "Deployment", "api"))["containers"][0]["env"]}
    ingest = {e["name"]: e.get("value") for e in pod_spec(one(objs, "Job", "ingest"))["containers"][0]["env"]}
    cron = {e["name"]: e.get("value") for e in pod_spec(one(objs, "CronJob", "ingest"))["containers"][0]["env"]}
    assert api["EMBED_VERSION"] == ingest["EMBED_VERSION"] == cron["EMBED_VERSION"]
