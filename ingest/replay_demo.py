"""Authored fixtures illustrating retirement interactions, never production data."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def build_demo():
    start = datetime(2026, 7, 1, tzinfo=UTC)
    definitions = [
        ("queue-depth", "queue_depth_high", "workers", 240),
        ("worker-lag", "worker_lag_high", "workers", 180),
        ("cache-evictions", "cache_evictions_high", "cache", 110),
        ("checkout-latency", "checkout_latency_high", "checkout", 60),
        ("db-connections", "db_connections_exhausted", "database", 24),
        ("disk-usage", "disk_usage_high", "storage", 40),
        ("checkout-errors", "checkout_errors_high", "checkout", 8),
        ("cache-unavailable", "cache_unavailable", "cache", 6),
    ]
    cases = [
        (
            "INC-101",
            "Worker backlog after a traffic spike",
            6,
            [("queue-depth", 0), ("worker-lag", 2)],
        ),
        ("INC-102", "Stalled worker consumer", 13, [("worker-lag", 0), ("queue-depth", 1)]),
        (
            "INC-103",
            "Checkout dependency degradation",
            22,
            [("checkout-latency", 0), ("checkout-errors", 12)],
        ),
        ("INC-104", "Database connection exhaustion", 35, [("db-connections", 0)]),
        (
            "INC-105",
            "Cache node unavailable",
            46,
            [("cache-unavailable", 0), ("cache-evictions", 3)],
        ),
        (
            "INC-106",
            "Cache failover failed",
            64,
            [("cache-unavailable", 0), ("cache-evictions", 2)],
        ),
        ("INC-107", "Customer-reported stale search results", 73, []),
    ]
    events, incidents = [], []
    for incident_id, title, day, alerts in cases:
        began = start + timedelta(days=day, hours=14)
        incidents.append(
            {
                "id": incident_id,
                "title": title,
                "started_at": began.isoformat(),
                "ended_at": (began + timedelta(hours=1)).isoformat(),
            }
        )
        for alert_id, minute in alerts:
            events.append(
                {
                    "id": f"{incident_id}-{alert_id}",
                    "alert_id": alert_id,
                    "fired_at": (began + timedelta(minutes=minute)).isoformat(),
                    "severity": "page",
                    "incident_id": incident_id,
                }
            )
    for index, (alert_id, _name, _service, total) in enumerate(definitions):
        linked_count = sum(event["alert_id"] == alert_id for event in events)
        for number in range(total - linked_count):
            fired = start + timedelta(
                days=number % 92,
                hours=(number * 7 + index) % 24,
                minutes=(number * 13 + index) % 60,
            )
            events.append(
                {
                    "id": f"{alert_id}-{number:04}",
                    "alert_id": alert_id,
                    "fired_at": fired.isoformat(),
                    "severity": "page",
                    "incident_id": None,
                }
            )
    return {
        "schema_version": 1,
        "source": {
            "label": "Authored retirement scenarios",
            "synthetic": True,
            "incident_ledger_complete": True,
            "description": "Deterministic teaching fixture authored for this project. Counts and incident links are invented; not IBM or customer data.",
        },
        "window": {
            "start": start.isoformat(),
            "end": datetime(2026, 10, 1, tzinfo=UTC).isoformat(),
        },
        "alerts": [
            {"id": key, "name": name, "service": service} for key, name, service, _ in definitions
        ],
        "incidents": incidents,
        "events": events,
    }


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "seed" / "retirement-demo.json"
    path.write_text(json.dumps(build_demo(), indent=2) + "\n", encoding="utf-8")
    print(path)
