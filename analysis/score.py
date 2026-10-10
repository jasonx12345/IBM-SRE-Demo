from collections import Counter, defaultdict
from statistics import mean, median
from zoneinfo import ZoneInfo

from analysis.classify import classify
from ingest.source import AlertEvent, ObservationWindow


def month_keys(window: ObservationWindow) -> list[str]:
    local = window.start.astimezone(ZoneInfo(window.timezone))
    return [
        f"{(local.year * 12 + local.month - 1 + i) // 12:04d}-"
        f"{(local.year * 12 + local.month - 1 + i) % 12 + 1:02d}"
        for i in range(window.months)
    ]


def score_alert(events: list[AlertEvent], window: ObservationWindow, config: dict) -> dict:
    if not events or window.months <= 0:
        raise ValueError("Scoring requires events and a positive observation window")
    model = config["model"]
    timezone = ZoneInfo(model["timezone"])
    manual = [event for event in events if event.manual_action]
    ack_minutes = [
        (e.acknowledged_at - e.fired_at).total_seconds() / 60
        for e in events
        if e.acknowledged_at and e.acknowledged_at >= e.fired_at
    ]
    manual_minutes = [
        (e.resolved_at - e.acknowledged_at).total_seconds() / 60
        for e in manual
        if e.resolved_at and e.acknowledged_at and e.resolved_at >= e.acknowledged_at >= e.fired_at
    ]
    # Unknown runbooks stay in the denominator but cannot become a modal action.
    actions = Counter(e.runbook_action for e in manual if e.runbook_action)
    modal, modal_count = (
        sorted(actions.items(), key=lambda item: (-item[1], item[0]))[0] if actions else (None, 0)
    )
    manual_median = median(manual_minutes) if manual_minutes else None
    responders = mean(e.responder_count for e in manual) if manual else 0.0
    toil = (
        (len(manual) * manual_median * max(responders, 1))
        if manual_median is not None
        else (0.0 if not manual else None)
    )

    def after_hours(event):
        return (
            not model["business_hours_start"]
            <= event.fired_at.astimezone(timezone).hour
            < model["business_hours_end"]
        )

    pages = [e for e in events if e.severity == "page"]
    monthly = {
        key: {"month": key, "occurrences": 0, "manual_count": 0, "pages": 0}
        for key in month_keys(window)
    }
    for event in events:
        key = event.fired_at.astimezone(ZoneInfo(window.timezone)).strftime("%Y-%m")
        monthly.setdefault(key, {"month": key, "occurrences": 0, "manual_count": 0, "pages": 0})
        monthly[key]["occurrences"] += 1
        monthly[key]["manual_count"] += int(event.manual_action)
        monthly[key]["pages"] += int(event.severity == "page")
    result = {
        "alert_name": events[0].alert_name,
        "services": sorted({e.service for e in events}),
        "severities": sorted({e.severity for e in events}),
        "occurrences": len(events),
        "pages": len(pages),
        "pages_per_month": len(pages) / window.months,
        "occurrences_per_month": len(events) / window.months,
        "manual_count": len(manual),
        "manual_rate": len(manual) / len(events),
        "auto_resolve_rate": sum(e.auto_resolved for e in events) / len(events),
        "auto_resolve_under_3_minutes_rate": sum(
            e.auto_resolved
            and e.resolved_at is not None
            and 0 <= (e.resolved_at - e.fired_at).total_seconds() <= 180
            for e in events
        )
        / len(events),
        "incident_rate": sum(e.incident_id is not None for e in events) / len(events),
        "median_ack_minutes": median(ack_minutes) if ack_minutes else None,
        "median_manual_minutes": manual_median,
        "manual_duration_samples": len(manual_minutes),
        "manual_duration_missing": len(manual) - len(manual_minutes),
        "mean_responders": responders,
        "after_hours_rate": sum(after_hours(e) for e in events) / len(events),
        "after_hours_page_rate": sum(after_hours(e) for e in pages) / len(pages) if pages else None,
        "runbook_repeat_rate": modal_count / len(manual) if manual else 0.0,
        "modal_runbook_action": modal,
        "estimated_toil_minutes": toil,
        "estimated_annual_toil_hours": toil / 60 * (12 / window.months)
        if toil is not None
        else None,
        "monthly_occurrences": [monthly[key] for key in sorted(monthly)],
        "runbook_actions": [
            {"action": action, "count": count, "share": count / len(manual)}
            for action, count in sorted(actions.items(), key=lambda item: (-item[1], item[0]))
        ],
        "unknown_runbook_count": sum(not e.runbook_action for e in manual),
    }
    result["classification"], result["reason"] = classify(result, config["thresholds"])
    return result


def score_events(events: list[AlertEvent], window: ObservationWindow, config: dict) -> list[dict]:
    grouped = defaultdict(list)
    for event in events:
        grouped[event.alert_name].append(event)
    results = [score_alert(rows, window, config) for rows in grouped.values()]
    return sorted(
        results,
        key=lambda row: (
            row["estimated_annual_toil_hours"] is None,
            -(row["estimated_annual_toil_hours"] or 0),
            row["alert_name"],
        ),
    )
