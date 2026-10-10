import json
from collections import Counter
from copy import deepcopy

import pytest

from analysis.retirement import replay
from ingest.itbench import OUTPUT, RAW, linked_ground_truth, normalize
from ingest.replay import load_dataset, parse_dataset


@pytest.fixture(scope="module")
def ibm():
    return load_dataset(OUTPUT)


def test_import_reproduces_checked_in_dataset_and_checksums():
    assert normalize() == json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_repeated_snapshots_do_not_inflate_episode_counts(ibm):
    counts = ibm.document["provenance"]["import_counts"]
    assert counts == {
        "snapshot_files": 82,
        "raw_rows": 772,
        "excluded_rows": 287,
        "duplicate_rows": 448,
    }
    assert len(ibm.events) == 37
    assert counts["raw_rows"] - counts["excluded_rows"] - counts["duplicate_rows"] == len(
        ibm.events
    )
    assert sum(e["provenance"]["observation_count"] for e in ibm.document["events"]) == 485
    assert len(ibm.alerts) == 13
    assert Counter(e["incident_id"] for e in ibm.events) == {
        None: 29,
        "Scenario-1": 2,
        "Scenario-2": 6,
    }


def test_pending_and_support_alerts_do_not_count_as_measured_warnings(ibm):
    for event in ibm.document["events"]:
        p = event["provenance"]
        source = json.loads((RAW / p["source_file"]).read_text(encoding="utf-8"))
        row = next(
            row
            for row in source
            if row["labels"] == p["labels"] and row["activeAt"] == p["active_at"]
        )
        assert row["state"] == "firing"
        assert row["labels"]["severity"] in ("warning", "critical")
        assert event["severity"] == "recorded"
        assert event["fired_at"] == p["first_observed_at"]


def test_ground_truth_matching_requires_the_right_namespace_and_service():
    truth = {
        "groups": [
            {
                "id": "proxy",
                "kind": "Service",
                "namespace": "otel-demo",
                "filter": [r"frontend-proxy\b"],
            }
        ],
        "alerts": [{"id": "RequestErrorRate", "group_id": "proxy"}],
    }
    labels = {
        "alertname": "RequestErrorRate",
        "namespace": "otel-demo",
        "service_name": "frontend-proxy",
    }
    assert linked_ground_truth(labels, truth) == "proxy"
    for changes in (
        {"namespace": "another"},
        {"service_name": "frontend"},
        {"service_name": "frontend-proxy-other"},
        {"alertname": "Different"},
    ):
        assert linked_ground_truth({**labels, **changes}, truth) is None


def test_ibm_batch_removal_and_restoration_use_actual_evidence(ibm):
    selected = [a["id"] for a in ibm.alerts.values() if a["service"] == "frontend-proxy"]
    result = replay(ibm, selected)
    assert result["summary"]["baseline_events"] == 37
    assert result["summary"]["removed_events"] == 6
    assert result["summary"]["lost_incidents"] == 1
    assert result["summary"]["combination_conflicts"] == 1
    assert result["summary"]["unlinked_events"] == 29
    assert result["event_kind"] == "recorded_alert"
    assert not result["evidence"]["ledger_declared_complete"]
    assert "page_events" not in json.dumps(result)
    assert result["summary"]["late_incidents"] == 1
    cart = next(row for row in result["incidents"] if row["id"] == "Scenario-2")
    assert cart["added_delay_minutes"] == pytest.approx(19, abs=0.001)
    assert result["restoration_options"][0]["name"] == "RequestErrorRate"
    keep = result["restoration_options"][0]["id"]
    repaired = replay(ibm, [x for x in selected if x != keep])
    assert repaired["summary"]["lost_incidents"] == 0
    assert repaired["summary"]["late_incidents"] == 0
    assert repaired["summary"]["removed_events"] == 1
    assert repaired["verdict"] == "insufficient_evidence"


def test_unlinked_infrastructure_alerts_never_prove_redundancy(ibm):
    selected = [
        a["id"] for a in ibm.alerts.values() if a["name"] == "KubeClientCertificateExpiration"
    ]
    result = replay(ibm, selected)
    assert result["summary"]["removed_events"] == 10
    assert result["verdict"] == "insufficient_evidence"
    assert len(result["evidence"]["selected_without_incident_events"]) == 2


def test_source_mode_cannot_accidentally_treat_pages_as_recorded_alerts(ibm):
    changed = deepcopy(ibm.document)
    changed["events"][0]["severity"] = "page"
    with pytest.raises(ValueError, match="event_kind"):
        parse_dataset(changed)
    changed = deepcopy(ibm.document)
    changed["source"]["event_kind"] = "unknown"
    with pytest.raises(ValueError, match="event_kind"):
        parse_dataset(changed)


def test_default_api_uses_ibm_and_synthetic_example_is_separate(client, ibm):
    document = client.get("/api/retirement/dataset").json
    assert parse_dataset(document).fingerprint == ibm.fingerprint
    assert not document["source"]["synthetic"]
    assert client.get("/api/retirement/dataset?example=synthetic").json["source"]["synthetic"]
    assert client.get("/docs/IBM_DATA.md").status_code == 200


def test_manifest_detects_changed_source(tmp_path):
    import shutil

    shutil.copytree(RAW, tmp_path / "sources")
    source = next((tmp_path / "sources").glob("Scenario-1/alerts/*.json"))
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        normalize(tmp_path / "sources")
