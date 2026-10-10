import os
import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from api.repository import PostgresRepository
from ingest.pipeline import ingest

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; PostgreSQL integration test")
    database = "toil_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    repository = PostgresRepository(make_conninfo(url, dbname=database))
    try:
        repository.initialize()
        yield repository
    finally:
        repository.close()
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


def test_postgres_roundtrip_atomic_replacement_and_ingestion_metrics(postgres, source):
    assert postgres.ready()
    assert postgres.load_dataset() == ([], None, None)
    count = ingest(source, postgres)
    events, window, ingested_at = postgres.load_dataset()
    assert events == source.events()
    assert window == source.window
    assert ingested_at
    ingest(source, postgres)
    assert len(postgres.load_dataset()[0]) == count
    metrics = postgres.ingestion_metrics()
    assert metrics["count"] == 2
    assert metrics["events"] == count * 2
    assert metrics["buckets"][-1][1] == 2


def test_failed_sql_batch_rolls_back(postgres, source):
    from dataclasses import replace

    ingest(source, postgres)
    events = source.events()
    with pytest.raises(psycopg.errors.CheckViolation):
        postgres.replace_dataset([replace(events[0], responder_count=-1)], source.window)
    assert postgres.load_dataset()[0] == events


def test_api_and_durable_metrics_against_postgres(postgres, source, config):
    from api.app import create_app

    count = ingest(source, postgres)
    app = create_app(postgres, config)
    client = app.test_client()
    assert client.get("/readyz").status_code == 200
    assert client.get("/api/summary").json["alerts_analysed"] == count
    recommendations = client.get("/api/recommendations").json
    assert recommendations["automate"][0]["alert_name"] == "redis_memory_pressure"
    assert recommendations["delete"][0]["alert_name"] == "worker_queue_depth_warning"
    assert len(client.get("/api/alerts/redis_memory_pressure").json["monthly_occurrences"]) == 6
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "toil_budget_database_up 1.0" in metrics.text
    assert "toil_budget_ingestion_duration_seconds_count 1.0" in metrics.text
