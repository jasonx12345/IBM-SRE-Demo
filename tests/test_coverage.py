"""The IBM coverage report is a reproducible evidence audit, not a page history."""

import json

from api.app import create_app
from api.demo_repository import DemoRepository
from api.settings import load_config
from ingest.itbench_coverage import OUTPUT, RAW, build_report, group_matches


def test_resource_match_requires_namespace_and_full_identity():
    group = {"kind": "Service", "namespace": "otel-demo", "filter": [r"frontend-proxy\b"]}
    labels = {"namespace": "otel-demo", "service_name": "frontend-proxy"}
    assert group_matches(group, labels)
    assert not group_matches(group, {**labels, "service_name": "frontend-proxy-copy"})
    assert not group_matches(group, {**labels, "namespace": "other"})
    assert not group_matches(group, {"namespace": "otel-demo"})
    pod = {"kind": "Pod", "namespace": "otel-demo", "filter": ["ad-.*"]}
    assert group_matches(pod, {"namespace": "otel-demo", "pod": "ad-123"})


def test_checked_in_report_is_reproducible_from_verified_public_files():
    report = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert build_report(RAW) == report
    assert report["totals"]["scenarios"] == 35
    assert report["totals"]["snapshots"] == 1839
    assert report["totals"]["expected"] == 96
    assert sum(report["totals"][k] for k in ("observed", "not_observed", "unknown")) == 96
    scenario11 = next(s for s in report["scenarios"] if s["id"] == "Scenario-11")
    assert scenario11["snapshot_count"] == 0
    assert all(a["status"] == "unknown" for a in scenario11["expected"])
    for scenario in report["scenarios"]:
        for alert in scenario["expected"]:
            assert alert["status"] in {"observed", "not_observed", "unknown"}
            assert bool(alert["evidence_url"]) == (alert["status"] == "observed")


def test_main_page_and_report_api():
    app = create_app(DemoRepository(), load_config())
    client = app.test_client()
    assert b"Did the expected warnings appear?" in client.get("/").data
    assert client.get("/retirement").status_code == 404
    response = client.get("/api/coverage/report")
    assert response.status_code == 200
    assert response.json["totals"]["scenarios"] == 35
    assert response.json["source"]["repository"] == "ibm-research/ITBench-Lite"
