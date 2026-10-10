from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from analysis.classify import classify
from analysis.score import score_alert
from ingest.source import AlertEvent, ObservationWindow

FIRED = datetime(2026, 4, 1, 13, tzinfo=UTC)
WINDOW = ObservationWindow(
    FIRED.replace(hour=4), FIRED.replace(month=10, hour=4), 6, "America/Toronto", "test"
)


def event(minutes=10, **updates):
    row = AlertEvent(
        "test",
        "cache",
        "page",
        FIRED,
        FIRED + timedelta(minutes=2),
        FIRED + timedelta(minutes=minutes + 2),
        False,
        None,
        1,
        True,
        "flush",
    )
    return replace(row, **updates)


def test_estimate_excludes_nonmanual_and_uses_median_and_mean_responders(config):
    rows = [
        event(10, responder_count=2),
        event(20, responder_count=3),
        event(999, manual_action=False, acknowledged_at=None, auto_resolved=True),
    ]
    score = score_alert(rows, WINDOW, config)
    assert score["median_manual_minutes"] == 15
    assert score["mean_responders"] == 2.5
    assert score["estimated_toil_minutes"] == 75
    assert score["estimated_annual_toil_hours"] == 2.5
    assert score["median_ack_minutes"] == 2
    assert score["manual_rate"] == 2 / 3


def test_auto_resolve_has_zero_toil_and_no_manual_median(config):
    score = score_alert(
        [event(manual_action=False, auto_resolved=True, acknowledged_at=None)], WINDOW, config
    )
    assert score["estimated_toil_minutes"] == 0
    assert score["median_manual_minutes"] is None
    assert score["median_ack_minutes"] is None


def test_no_usable_manual_duration_is_unknown_not_zero(config):
    score = score_alert([event(resolved_at=None)], WINDOW, config)
    assert score["estimated_annual_toil_hours"] is None
    assert score["manual_duration_missing"] == 1


def test_missing_duration_uses_available_median_and_reports_extrapolation(config):
    score = score_alert(
        [event(12, responder_count=0), event(resolved_at=None, responder_count=0)], WINDOW, config
    )
    assert score["estimated_toil_minutes"] == 24
    assert score["manual_duration_samples"] == 1


def test_unknown_actions_do_not_inflate_runbook_repeat(config):
    rows = [event(), event(), event(runbook_action=None), event(runbook_action="other")]
    score = score_alert(rows, WINDOW, config)
    assert score["runbook_repeat_rate"] == 0.5
    assert score["unknown_runbook_count"] == 1
    assert score["modal_runbook_action"] == "flush"


def test_unknown_actions_never_become_automation_confidence(config):
    score = score_alert([event(runbook_action=None)] * 30, WINDOW, config)
    assert score["runbook_repeat_rate"] == 0
    assert score["classification"] != "automate"


def test_local_business_hour_boundaries_and_dst(config):
    winter = datetime(2026, 1, 10, tzinfo=UTC)
    rows = [
        event(fired_at=winter.replace(hour=13, minute=59)),
        event(fired_at=winter.replace(hour=14)),
        event(fired_at=winter.replace(hour=21, minute=59)),
        event(fired_at=winter.replace(hour=22)),
    ]
    assert score_alert(rows, WINDOW, config)["after_hours_rate"] == 0.5
    summer = [
        event(fired_at=FIRED.replace(hour=12, minute=59)),
        event(fired_at=FIRED.replace(hour=13)),
        event(fired_at=FIRED.replace(hour=20, minute=59)),
        event(fired_at=FIRED.replace(hour=21)),
    ]
    assert score_alert(summer, WINDOW, config)["after_hours_rate"] == 0.5


def test_empty_months_are_kept(config):
    score = score_alert([event()], WINDOW, config)
    assert len(score["monthly_occurrences"]) == 6
    assert score["monthly_occurrences"][-1] == {
        "month": "2026-09",
        "occurrences": 0,
        "manual_count": 0,
        "pages": 0,
    }


def test_annualization_uses_declared_months(config):
    score = score_alert([event(60)], replace(WINDOW, months=3), config)
    assert score["estimated_annual_toil_hours"] == 4


@pytest.mark.parametrize(
    "updates,expected",
    [
        (
            {
                "occurrences": 30,
                "manual_rate": 0.1,
                "incident_rate": 0.05,
                "auto_resolve_rate": 0.9,
            },
            "delete",
        ),
        (
            {
                "occurrences": 30,
                "manual_rate": 0.6,
                "incident_rate": 0.2,
                "auto_resolve_rate": 0.5,
                "runbook_repeat_rate": 0.7,
            },
            "tune",
        ),
        ({"occurrences": 10, "manual_rate": 0.6, "runbook_repeat_rate": 0.7}, "automate"),
        ({"occurrences": 10}, "keep_human"),
        ({"occurrences": 11}, "unclassified"),
    ],
)
def test_rule_boundaries_and_precedence(config, updates, expected):
    metrics = {
        "occurrences": 100,
        "manual_rate": 0.4,
        "auto_resolve_rate": 0.1,
        "incident_rate": 0.5,
        "runbook_repeat_rate": 0.2,
        "auto_resolve_under_3_minutes_rate": 0.2,
        "modal_runbook_action": "flush",
        **updates,
    }
    classification, reason = classify(metrics, config["thresholds"])
    assert classification == expected
    assert any(char.isdigit() for char in reason)


def test_threshold_edits_change_decisions(config):
    rows = [event()] * 15
    assert score_alert(rows, WINDOW, config)["classification"] == "automate"
    config["thresholds"]["automate"]["min_occurrences"] = 20
    assert score_alert(rows, WINDOW, config)["classification"] == "unclassified"
