from collections import Counter, defaultdict
from dataclasses import replace
from zoneinfo import ZoneInfo

import pytest

from analysis.service import AnalysisService
from ingest.pipeline import ingest
from ingest.synthetic import SyntheticSource
from tests.fakes import MemoryRepository


def test_deterministic_and_different_seeds(source):
    assert source.events() == SyntheticSource().events()
    assert source.events() != SyntheticSource(seed=43).events()


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_coverage_and_two_storms(months):
    source = SyntheticSource(months=months, start="2025-10-01")
    events = source.events()
    for event in events:
        event.validate()
        assert source.window.start <= event.fired_at < source.window.end
    nights = defaultdict(list)
    pages = [event for event in events if event.severity == "page"]
    for event in pages:
        local = event.fired_at.astimezone(ZoneInfo(source.window.timezone))
        if local.hour == 2:
            nights[local.date()].append(local)
    storms = []
    for day, times in nights.items():
        times.sort()
        if any(
            sum(0 <= (other - first).total_seconds() <= 1200 for other in times) >= 40
            for first in times
        ):
            storms.append(day)
    assert len(storms) == 2
    outside = sum(
        not 9 <= event.fired_at.astimezone(ZoneInfo(source.window.timezone)).hour < 17
        for event in pages
    )
    assert abs(outside / len(pages) - 0.35) < 0.002


def test_archetypes_and_recommendation_order(source, config):
    snapshot = AnalysisService(MemoryRepository(source), config).snapshot()
    alerts = {row["alert_name"]: row for row in snapshot["alerts"]}
    assert snapshot["recommendations"]["automate"][0]["alert_name"] == "redis_memory_pressure"
    assert snapshot["recommendations"]["delete"][0]["alert_name"] == "worker_queue_depth_warning"
    assert len(snapshot["recommendations"]["automate"]) == 3
    assert alerts["worker_queue_depth_warning"]["auto_resolve_rate"] > 0.85
    assert alerts["worker_queue_depth_warning"]["incident_rate"] < 0.05
    assert alerts["cpu_throttling_warning"]["manual_rate"] == 0
    assert 0.35 < alerts["pod_crashloopbackoff"]["runbook_repeat_rate"] < 0.65
    assert alerts["db_connection_pool_saturation"]["incident_rate"] == 1
    assert 2 <= alerts["db_connection_pool_saturation"]["mean_responders"] <= 3
    assert alerts["deploy_failed"]["manual_rate"] == 1
    assert alerts["cert_expiry_warning"]["runbook_repeat_rate"] == 1
    assert Counter(row["classification"] for row in alerts.values())["automate"] == 3


def test_reseeding_replaces_instead_of_appending(source):
    repo = MemoryRepository()
    count = ingest(source, repo)
    ingest(source, repo)
    assert len(repo.events) == count
    assert len(repo.runs) == 2
    assert all(row[2] == "success" for row in repo.runs)


def test_bad_batch_is_rejected_before_replacement(source):
    repo = MemoryRepository(source)
    original = repo.events
    bad = replace(original[0], severity="invalid")
    source.events = lambda: [bad]
    with pytest.raises(ValueError, match="severity"):
        ingest(source, repo)
    assert repo.events is original
    assert repo.runs[-1][2] == "error"


@pytest.mark.parametrize("args", [{"months": 0}, {"months": -1}, {"start": "2026-04-02"}])
def test_invalid_windows(args):
    with pytest.raises(ValueError):
        SyntheticSource(**args)
