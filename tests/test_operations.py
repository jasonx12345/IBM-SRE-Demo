import json

import yaml

from api.settings import ROOT
from grafana.generate_dashboard import build_dashboard
from k8s.generate_config import build_configmap
from prometheus.generate_rules import build_rules


def test_slo_rules_match_canonical_config(config):
    actual = yaml.safe_load((ROOT / "prometheus/rules.yaml").read_text())
    assert actual == build_rules(config["slo"])


def test_kubernetes_config_does_not_drift():
    actual = yaml.safe_load((ROOT / "k8s/configmap.yaml").read_text())
    assert actual == build_configmap()


def test_dashboard_matches_generator_and_has_all_signals():
    actual = json.loads((ROOT / "grafana/dashboard.json").read_text(encoding="utf-8"))
    assert actual == build_dashboard()
    expressions = " ".join(
        target["expr"] for panel in actual["panels"] for target in panel.get("targets", [])
    )
    for name in (
        "http_requests_total",
        "http_request_duration_seconds_bucket",
        "api_error_ratio",
        "http_requests_in_flight",
        "ingestion_duration_seconds",
        "estimated_annual_toil_hours",
    ):
        assert name in expressions


def test_kubernetes_replicas_resources_and_probes():
    manifest = yaml.safe_load((ROOT / "k8s/deployment.yaml").read_text())
    assert manifest["spec"]["replicas"] == 2
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert set(container["resources"]) == {"requests", "limits"}
