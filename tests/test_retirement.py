from copy import deepcopy

import pytest

from analysis.retirement import replay
from api.app import create_app
from api.demo_repository import DemoRepository
from ingest.replay import parse_dataset
from ingest.replay_demo import build_demo


@pytest.fixture
def dataset():
    return parse_dataset(build_demo())


def test_joint_retirement_catches_what_individual_reviews_miss(dataset):
    for selected in (["queue-depth"], ["worker-lag"]):
        result = replay(dataset, selected)
        assert result["verdict"] == "no_observed_regression"
        assert result["summary"]["lost_incidents"] == 0
    combined = replay(dataset, ["queue-depth", "worker-lag"])
    assert combined["verdict"] == "regression"
    assert combined["summary"]["lost_incidents"] == 2
    assert combined["summary"]["combination_conflicts"] == 2
    assert combined["summary"]["removed_events"] == 420
    assert combined["summary"]["baseline_events"] == 668
    assert combined["restoration_options"][0]["id"] == "worker-lag"
    assert combined["restoration_options"][0]["remaining_regressions"] == 0
    assert combined["restoration_options"][0]["events_restored"] == 180


def test_delay_is_measured_from_first_page_and_boundary_is_inclusive(dataset):
    result = replay(dataset, ["checkout-latency"], 5)
    incident = next(row for row in result["incidents"] if row["id"] == "INC-103")
    assert incident["added_delay_minutes"] == 12
    assert incident["status"] == "late"
    assert result["summary"]["late_incidents"] == 1
    assert result["summary"]["combination_conflicts"] == 0
    assert replay(dataset, ["checkout-latency"], 12)["summary"]["late_incidents"] == 0


def test_baseline_gap_stays_in_denominator_without_blame_for_new_policy(dataset):
    result = replay(dataset, ["cache-evictions"])
    assert result["summary"]["incidents_total"] == 7
    assert result["summary"]["baseline_covered"] == 6
    assert result["summary"]["proposed_covered"] == 6
    assert result["summary"]["baseline_gaps"] == 1
    assert result["summary"]["lost_incidents"] == 0
    gap = next(row for row in result["incidents"] if row["id"] == "INC-107")
    assert gap["status"] == "baseline_gap"
    assert gap["added_delay_minutes"] is None
    assert gap["timeline"] == []


def test_unlinked_events_never_establish_safety(dataset):
    report = replay(dataset, ["disk-usage"])
    assert report["verdict"] == "insufficient_evidence"
    assert report["evidence"]["selected_without_incident_events"] == ["disk-usage"]
    assert report["summary"]["unlinked_events"] == 657


def test_incomplete_incident_ledger_is_explicit():
    data = build_demo()
    data["source"]["incident_ledger_complete"] = False
    assert replay(parse_dataset(data), ["cache-evictions"])["verdict"] == "insufficient_evidence"


def test_tickets_do_not_restore_paging_coverage():
    data = build_demo()
    for event in data["events"]:
        if event["id"] == "INC-103-checkout-errors":
            event["severity"] = "ticket"
    report = replay(parse_dataset(data), ["checkout-latency"])
    assert report["summary"]["lost_incidents"] == 1
    assert report["summary"]["late_incidents"] == 0


def test_order_independent_replay_and_stable_fingerprint():
    data = build_demo()
    first = replay(parse_dataset(data), ["queue-depth", "worker-lag"])
    second = replay(parse_dataset(deepcopy(data)), ["worker-lag", "queue-depth"])
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
    data["events"].reverse()
    third = replay(parse_dataset(data), ["worker-lag", "queue-depth"])
    assert first["summary"] == third["summary"]
    assert first["incidents"] == third["incidents"]


def test_restoration_is_verified_against_entire_batch(dataset):
    report = replay(dataset, ["queue-depth", "worker-lag", "db-connections"])
    assert report["summary"]["lost_incidents"] == 3
    for option in report["restoration_options"]:
        remaining = list(set(report["policy"]["retire"]) - {option["id"]})
        check = replay(dataset, remaining)
        assert (
            option["remaining_regressions"]
            == check["summary"]["lost_incidents"] + check["summary"]["late_incidents"]
        )


def test_empty_history_is_unknown_not_zero_risk():
    data = build_demo()
    data["incidents"] = []
    data["events"] = []
    report = replay(parse_dataset(data), ["queue-depth"])
    assert report["verdict"] == "insufficient_evidence"
    assert report["summary"]["event_reduction_rate"] is None
    assert report["summary"]["incidents_total"] == 0


@pytest.mark.parametrize(
    "retired,delay",
    [
        (["missing"], 5),
        (["queue-depth"] * 2, 5),
        ("queue-depth", 5),
        ([{}], 5),
        ([], -1),
        ([], 61),
        ([], True),
        ([], float("nan")),
        ([], float("inf")),
        ([], "5"),
    ],
)
def test_invalid_policy(dataset, retired, delay):
    with pytest.raises(ValueError):
        replay(dataset, retired, delay)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["events"].append(d["events"][0]),
        lambda d: d["events"][0].update(incident_id="unknown"),
        lambda d: d["events"][0].update(alert_id="unknown"),
        lambda d: d["events"][0].update(fired_at="2026-07-07T14:00:00"),
        lambda d: d["events"][0].update(fired_at="2025-07-07T14:00:00Z"),
        lambda d: d["events"][0].update(fired_at="2026-07-07T16:00:00Z"),
        lambda d: d["events"][0].update(severity="critical"),
        lambda d: d["source"].update(incident_ledger_complete="yes"),
        lambda d: d["window"].update(end=d["window"]["start"]),
        lambda d: d.update(events={}),
        lambda d: d.update(schema_version=True),
    ],
)
def test_invalid_datasets_rejected(mutation):
    data = build_demo()
    mutation(data)
    with pytest.raises(ValueError):
        parse_dataset(data)


def test_replay_api_export_input_round_trip(client):
    data = client.get("/api/retirement/dataset?example=synthetic").json
    payload = {"dataset": data, "retire": ["queue-depth", "worker-lag"], "max_delay_minutes": 5}
    response = client.post("/api/retirement/replay", json=payload)
    assert response.status_code == 200
    report = response.json
    assert report["summary"]["combination_conflicts"] == 2
    assert report["dataset_sha256"] == parse_dataset(data).fingerprint
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/toil").status_code == 200
    assert client.get("/docs/RESEARCH.md").status_code == 200


@pytest.mark.parametrize(
    "payload", [[], None, {"dataset": {}}, {"retire": ["unknown"]}, {"max_delay_minutes": -1}]
)
def test_api_rejects_bad_requests(client, payload):
    response = client.post("/api/retirement/replay", json=payload, content_type="application/json")
    assert response.status_code == 400


def test_import_does_not_replace_server_dataset(client):
    data = build_demo()
    data["source"]["label"] = "Uploaded history"
    assert (
        client.post("/api/retirement/replay", json={"dataset": data}).json["source"]["label"]
        == "Uploaded history"
    )
    assert client.get("/api/retirement/dataset").json["source"]["label"] != "Uploaded history"


def test_demo_runs_without_a_database(config, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = create_app(DemoRepository(), config).test_client()
    assert client.get("/readyz").status_code == 200
    metrics = client.get("/metrics").text
    assert "toil_budget_demo_mode 1.0" in metrics
    assert "toil_budget_database_up" not in metrics
    assert client.get("/api/summary").json["alerts_analysed"] > 0
    assert (
        client.post(
            "/api/retirement/replay",
            json={"dataset": build_demo(), "retire": ["queue-depth", "worker-lag"]},
        ).json["summary"]["lost_incidents"]
        == 2
    )


def test_oversized_delay_is_a_client_error(client):
    response = client.post("/api/retirement/replay", json={"max_delay_minutes": 10**400})
    assert response.status_code == 400
