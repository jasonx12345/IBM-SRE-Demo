"""Historical event-removal regression checks. No causal or future-safety claims."""

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime

from ingest.replay import ReplayDataset

ASSUMPTIONS = [
    "Each input event is counted once; delivery, escalation and human response are not modeled.",
    "Only explicitly linked events inside supplied evidence intervals count toward coverage.",
    "Remaining events are held fixed; removing an early warning may change later events in reality.",
    "Unlinked events are unknown, not proven noise. Ledger completeness is supplied by the data author.",
    "No observed regression is historical evidence only, never proof that a removal is safe in production.",
]


def _outcomes(dataset, grouped, retired, delay):
    result = []
    for incident in dataset.incidents.values():
        pages = grouped[incident["id"]]
        remaining = [event for event in pages if event["alert_id"] not in retired]
        before = pages[0]["fired_at"] if pages else None
        after = remaining[0]["fired_at"] if remaining else None
        extra = (after - before).total_seconds() / 60 if after and before else None
        status = (
            "baseline_gap"
            if before is None
            else "lost"
            if after is None
            else "late"
            if extra > delay
            else "delayed"
            if extra > 0
            else "unchanged"
        )
        result.append(
            {
                "id": incident["id"],
                "title": incident["title"],
                "started_at": incident["started_at"].isoformat(),
                "baseline_first_event": before.isoformat() if before else None,
                "proposed_first_event": after.isoformat() if after else None,
                "added_delay_minutes": extra,
                "status": status,
                "baseline_alert_ids": sorted({event["alert_id"] for event in pages}),
                "remaining_alert_ids": sorted({event["alert_id"] for event in remaining}),
            }
        )
    return result


def replay(dataset: ReplayDataset, retired=None, max_delay_minutes=5) -> dict:
    retired = [] if retired is None else retired
    if (
        not isinstance(retired, list)
        or len(retired) > 20
        or any(not isinstance(value, str) for value in retired)
    ):
        raise ValueError("retire must be a list of at most 20 alert IDs.")
    if len(set(retired)) != len(retired) or set(retired) - dataset.alerts.keys():
        raise ValueError("retire must contain unique, known alert IDs.")
    if (
        type(max_delay_minutes) not in (int, float)
        or not 0 <= max_delay_minutes <= 60
        or not math.isfinite(max_delay_minutes)
    ):
        raise ValueError("max_delay_minutes must be a finite number from 0 to 60.")
    retired = set(retired)
    event_kind = dataset.document["source"].get("event_kind", "page")
    severity = "recorded" if event_kind == "recorded_alert" else "page"
    pages = [event for event in dataset.events if event["severity"] == severity]
    grouped = defaultdict(list)
    for event in pages:
        if event["incident_id"]:
            grouped[event["incident_id"]].append(event)
    counts = Counter(event["alert_id"] for event in pages)
    linked = Counter(event["alert_id"] for event in pages if event["incident_id"])
    isolated = {}
    candidates = []
    for alert in dataset.alerts.values():
        outcomes = _outcomes(dataset, grouped, {alert["id"]}, max_delay_minutes)
        isolated[alert["id"]] = {row["id"]: row["status"] for row in outcomes}
        lost = sum(row["status"] == "lost" for row in outcomes)
        late = sum(row["status"] == "late" for row in outcomes)
        candidates.append(
            {
                **alert,
                "event_count": counts[alert["id"]],
                "linked_events": linked[alert["id"]],
                "incident_count": len(
                    {
                        event["incident_id"]
                        for event in pages
                        if event["alert_id"] == alert["id"] and event["incident_id"]
                    }
                ),
                "isolated_lost": lost,
                "isolated_late": late,
                "isolated_verdict": "regression"
                if lost or late
                else "insufficient_evidence"
                if not linked[alert["id"]]
                else "no_observed_regression",
            }
        )
    candidates.sort(key=lambda row: (-row["event_count"], row["id"]))
    outcomes = _outcomes(dataset, grouped, retired, max_delay_minutes)
    for row in outcomes:
        row["combination_conflict"] = row["status"] in ("lost", "late") and all(
            isolated[alert_id][row["id"]] not in ("lost", "late") for alert_id in retired
        )
        baseline = grouped[row["id"]][0]["fired_at"] if grouped[row["id"]] else None
        row["timeline"] = [
            {
                "event_id": event["id"],
                "alert_id": event["alert_id"],
                "alert_name": dataset.alerts[event["alert_id"]]["name"],
                "service": dataset.alerts[event["alert_id"]]["service"],
                "fired_at": event["fired_at"].isoformat(),
                "minutes_from_first_event": (event["fired_at"] - baseline).total_seconds() / 60,
                "removed": event["alert_id"] in retired,
            }
            for event in grouped[row["id"]]
        ]
    regression_ids = {row["id"] for row in outcomes if row["status"] in ("lost", "late")}
    restorations = []
    for alert_id in sorted(retired):
        restored = _outcomes(dataset, grouped, retired - {alert_id}, max_delay_minutes)
        resolved = sorted(
            row["id"]
            for row in restored
            if row["id"] in regression_ids and row["status"] not in ("lost", "late")
        )
        if resolved:
            restorations.append(
                {
                    **dataset.alerts[alert_id],
                    "events_restored": counts[alert_id],
                    "resolves_incidents": resolved,
                    "remaining_regressions": len(regression_ids) - len(resolved),
                }
            )
    restorations.sort(
        key=lambda row: (row["remaining_regressions"], row["events_restored"], row["id"])
    )
    removed_pages = sum(counts[alert_id] for alert_id in retired)
    evidence_gaps = sorted(alert_id for alert_id in retired if not linked[alert_id])
    complete = dataset.document["source"]["incident_ledger_complete"]
    statuses = Counter(row["status"] for row in outcomes)
    verdict = (
        "no_changes"
        if not retired
        else "regression"
        if regression_ids
        else "insufficient_evidence"
        if evidence_gaps or not complete or not grouped
        else "no_observed_regression"
    )
    return {
        "report_version": 2,
        "engine_version": "retirement-replay-2",
        "event_kind": event_kind,
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": dataset.fingerprint,
        "source": dataset.document["source"],
        "window": dataset.document["window"],
        "policy": {"retire": sorted(retired), "max_delay_minutes": max_delay_minutes},
        "verdict": verdict,
        "summary": {
            "baseline_events": len(pages),
            "removed_events": removed_pages,
            "remaining_events": len(pages) - removed_pages,
            "event_reduction_rate": removed_pages / len(pages) if pages else None,
            "incidents_total": len(outcomes),
            "baseline_covered": len(outcomes) - statuses["baseline_gap"],
            "proposed_covered": len(outcomes) - statuses["baseline_gap"] - statuses["lost"],
            "lost_incidents": statuses["lost"],
            "late_incidents": statuses["late"],
            "within_delay_budget": statuses["unchanged"] + statuses["delayed"],
            "baseline_gaps": statuses["baseline_gap"],
            "combination_conflicts": sum(row["combination_conflict"] for row in outcomes),
            "unlinked_events": sum(not event["incident_id"] for event in pages),
        },
        "evidence": {
            "selected_without_incident_events": evidence_gaps,
            "ledger_declared_complete": complete,
        },
        "candidates": candidates,
        "incidents": outcomes,
        "restoration_options": restorations,
        "assumptions": ASSUMPTIONS
        + (
            [
                "Benchmark scenarios are controlled experiments, not production incidents or a complete incident ledger.",
                "Event timestamps are first observed firing snapshots, not exact firing or pager delivery times.",
                "Alerts present at the first snapshot are left-censored; their earlier firing order is unknown.",
                "Scope is alert name, namespace, service, job and source severity; this is not an exported rule configuration.",
            ]
            if event_kind == "recorded_alert"
            else []
        ),
    }
