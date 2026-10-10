"""Validated, vendor-neutral event history and independent incident ledger."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ReplayDataset:
    document: dict
    fingerprint: str
    alerts: dict
    incidents: dict
    events: tuple


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ValueError(f"{field} must be a non-empty string of at most 300 characters.")
    return value


def _time(value, field):
    try:
        result = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise ValueError(f"{field} must be an ISO timestamp with a timezone.") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone.")
    return result


def _rows(document, key, limit):
    rows = document.get(key)
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError(f"{key} must be a list with at most {limit} entries.")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Each {key} entry must be an object.")
    ids = [_text(row.get("id"), f"{key}.id") for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Duplicate {key} IDs are not allowed.")
    return rows


def parse_dataset(document) -> ReplayDataset:
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("Dataset must be an object with schema_version: 1.")
    source, window = document.get("source"), document.get("window")
    if not isinstance(source, dict) or not isinstance(window, dict):
        raise ValueError("Dataset requires source and window objects.")
    _text(source.get("label"), "source.label")
    _text(source.get("description"), "source.description")
    for key in ("synthetic", "incident_ledger_complete"):
        if type(source.get(key)) is not bool:
            raise ValueError(f"source.{key} must be a boolean.")
    event_kind = source.get("event_kind", "page")
    if event_kind not in ("page", "recorded_alert"):
        raise ValueError("source.event_kind must be page or recorded_alert.")
    start, end = _time(window.get("start"), "window.start"), _time(window.get("end"), "window.end")
    if end <= start:
        raise ValueError("window.end must be after window.start.")
    alerts = {}
    for row in _rows(document, "alerts", 64):
        scope = row.get("scope", {})
        if not isinstance(scope, dict) or any(not isinstance(v, str) for v in scope.values()):
            raise ValueError("alerts.scope must be an object with string values.")
        alerts[row["id"]] = {
            "id": row["id"],
            "name": _text(row.get("name"), "alerts.name"),
            "service": _text(row.get("service"), "alerts.service"),
            "scope": scope,
        }
    incidents = {}
    for row in _rows(document, "incidents", 2000):
        began = _time(row.get("started_at"), "incidents.started_at")
        ended = _time(row.get("ended_at"), "incidents.ended_at")
        if not start <= began <= ended < end:
            raise ValueError(
                "Incident intervals must be ordered and inside the observation window."
            )
        incidents[row["id"]] = {
            "id": row["id"],
            "title": _text(row.get("title"), "incidents.title"),
            "started_at": began,
            "ended_at": ended,
        }
    events = []
    for row in _rows(document, "events", 20000):
        alert_id = _text(row.get("alert_id"), "events.alert_id")
        incident_id = row.get("incident_id")
        fired = _time(row.get("fired_at"), "events.fired_at")
        if alert_id not in alerts:
            raise ValueError("Every event must reference a known alert_id.")
        allowed = ("recorded",) if event_kind == "recorded_alert" else ("page", "ticket", "info")
        if row.get("severity") not in allowed:
            raise ValueError("Event severity must match the source event_kind.")
        if incident_id is not None:
            _text(incident_id, "events.incident_id")
            if incident_id not in incidents:
                raise ValueError("Every linked event must reference a known incident_id.")
            incident = incidents[incident_id]
            if not incident["started_at"] <= fired <= incident["ended_at"]:
                raise ValueError("Linked events must be inside their incident evidence interval.")
        if not start <= fired < end:
            raise ValueError("Every event must be inside the observation window [start, end).")
        events.append(
            {
                "id": row["id"],
                "alert_id": alert_id,
                "incident_id": incident_id,
                "fired_at": fired,
                "severity": row["severity"],
            }
        )
    fingerprint = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return ReplayDataset(
        document,
        fingerprint,
        alerts,
        incidents,
        tuple(sorted(events, key=lambda event: (event["fired_at"], event["id"]))),
    )


def load_dataset(path: Path) -> ReplayDataset:
    return parse_dataset(json.loads(path.read_text(encoding="utf-8")))
