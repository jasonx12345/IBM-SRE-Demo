import psycopg
import pytest
from prometheus_client.parser import text_string_to_metric_families

from api.app import create_app
from ingest.pipeline import ingest
from tests.fakes import MemoryRepository


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api/summary",
        "/api/alerts",
        "/api/recommendations",
        "/healthz",
        "/readyz",
        "/metrics",
        "/docs/MODEL.md",
        "/docs/LIMITATIONS.md",
    ],
)
def test_routes(client, path):
    assert client.get(path).status_code == 200


def test_summary_and_details(client):
    summary = client.get("/api/summary").json
    alerts = client.get("/api/alerts").json
    assert summary["alert_types_analysed"] == 8
    assert summary["alerts_analysed"] == sum(row["occurrences"] for row in alerts)
    assert sum(summary["classification_shares"].values()) == pytest.approx(1)
    assert [row["estimated_annual_toil_hours"] for row in alerts] == sorted(
        [row["estimated_annual_toil_hours"] for row in alerts], reverse=True
    )
    detail = client.get("/api/alerts/redis_memory_pressure").json
    assert len(detail["monthly_occurrences"]) == 6
    assert detail["runbook_actions"][0]["action"] == "flush_cache"
    assert "flush_cache" in detail["reason"]


def test_empty_database(config):
    client = create_app(MemoryRepository(), config).test_client()
    summary = client.get("/api/summary").json
    assert summary["alerts_analysed"] == 0
    assert summary["window"] is None
    assert client.get("/api/alerts").json == []
    assert client.get("/api/recommendations").json == {"automate": [], "delete": []}


def test_probe_separation_and_scrape_failure(client, repository):
    repository.healthy = False
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    assert "toil_budget_database_up 0.0" in client.get("/metrics").text


def test_metrics_count_success_errors_and_ingestion(client, repository, source):
    ingest(source, repository)
    client.get("/api/summary")
    client.get("/api/alerts/not-a-real-alert")
    client.get("/api/another-unknown-path")
    exposition = client.get("/metrics").text
    families = {family.name: family for family in text_string_to_metric_families(exposition)}
    assert "toil_budget_http_request_duration_seconds" in families
    assert "toil_budget_ingestion_duration_seconds" in families
    assert "toil_budget_estimated_annual_toil_hours" in families
    samples = families["toil_budget_http_requests"].samples
    assert any(
        sample.labels.get("status") == "404" and sample.labels.get("route") == "/api/alerts/<name>"
        for sample in samples
    )
    assert any(
        sample.labels.get("scope") == "api" and sample.labels.get("route") == "unmatched"
        for sample in samples
    )
    assert "not-a-real-alert" not in exposition  # bounded route label cardinality
    assert 'le="0.3"' in exposition
    assert "toil_budget_http_requests_in_flight 0.0" in exposition
    assert "toil_budget_ingestion_duration_seconds_count 1.0" in exposition


def test_database_exception_has_safe_503(client, repository):
    def fail():
        raise psycopg.OperationalError("secret DSN details")

    repository.load_dataset = fail
    response = client.get("/api/summary")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert 'status="503"' in client.get("/metrics").text


def test_unknown_alert_returns_404(client):
    assert client.get("/api/alerts/nonexistent").status_code == 404


def test_savings_fraction_changes_recoverable_estimate(repository, config):
    config["model"]["automation_savings_fraction"] = 0.5
    client = create_app(repository, config).test_client()
    row = client.get("/api/recommendations").json["automate"][0]
    assert row["estimated_annual_hours_saved"] == row["estimated_annual_toil_hours"] * 0.5
