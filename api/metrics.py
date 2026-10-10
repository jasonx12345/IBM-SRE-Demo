import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily


class DatasetCollector:
    """Durable ingestion metrics and bounded per-alert analysis gauges.

    Shared database gauges/counters repeat on each replica: use max, not sum,
    when aggregating them. Request metrics are per-process and should be summed.
    """

    def __init__(self, service, repository):
        self.service = service
        self.repository = repository

    def describe(self):
        return []

    def collect(self):
        try:
            ingestion = self.repository.ingestion_metrics()
            snapshot = self.service.snapshot()
        except Exception:
            logging.exception("Database-backed metrics collection failed")
            yield GaugeMetricFamily(
                "toil_budget_database_up", "Database available during scrape", value=0
            )
            return
        if getattr(self.repository, "is_demo", False):
            yield GaugeMetricFamily(
                "toil_budget_demo_mode", "In-memory demo repository in use", value=1
            )
        else:
            yield GaugeMetricFamily(
                "toil_budget_database_up", "Database available during scrape", value=1
            )
        yield HistogramMetricFamily(
            "toil_budget_ingestion_duration_seconds",
            "Persisted ingestion duration, including parsing, validation and commit",
            buckets=ingestion["buckets"],
            sum_value=ingestion["sum"],
        )
        yield CounterMetricFamily(
            "toil_budget_ingested_events",
            "Events processed by successful ingestions, including replacements",
            value=ingestion["events"],
        )
        yield CounterMetricFamily(
            "toil_budget_ingestion_errors", "Recorded failed ingestions", value=ingestion["errors"]
        )
        yield GaugeMetricFamily(
            "toil_budget_last_ingestion_timestamp_seconds",
            "Last persisted ingestion completion",
            value=float(ingestion["last_timestamp"] or 0),
        )
        hours = GaugeMetricFamily(
            "toil_budget_estimated_annual_toil_hours",
            "Estimated annual toil hours; never measured labor",
            labels=["alert_name", "classification"],
        )
        occurrences = GaugeMetricFamily(
            "toil_budget_alert_occurrences",
            "Events in the observation window",
            labels=["alert_name", "classification"],
        )
        repeat = GaugeMetricFamily(
            "toil_budget_runbook_repeat_rate",
            "Modal runbook share of all manual resolutions",
            labels=["alert_name"],
        )
        for row in snapshot["alerts"]:
            labels = [row["alert_name"], row["classification"]]
            if row["estimated_annual_toil_hours"] is not None:
                hours.add_metric(labels, row["estimated_annual_toil_hours"])
            occurrences.add_metric(labels, row["occurrences"])
            repeat.add_metric([row["alert_name"]], row["runbook_repeat_rate"])
        yield hours
        yield occurrences
        yield repeat
        yield GaugeMetricFamily(
            "toil_budget_automation_recoverable_hours",
            "Estimated annual gross savings from the top three automation candidates",
            value=snapshot["summary"]["top_three_automation_estimated_annual_hours_saved"],
        )


class AppMetrics:
    def __init__(self, service, repository, config):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "toil_budget_http_requests_total",
            "HTTP requests by route template and status",
            ["method", "route", "status", "scope"],
            registry=self.registry,
        )
        buckets = sorted(
            {
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.2,
                0.3,
                0.5,
                1,
                2.5,
                5,
                config["slo"]["latency"]["threshold_seconds"],
            }
        )
        self.latency = Histogram(
            "toil_budget_http_request_duration_seconds",
            "Server request latency by route template",
            ["method", "route", "scope"],
            buckets=buckets,
            registry=self.registry,
        )
        self.in_flight = Gauge(
            "toil_budget_http_requests_in_flight",
            "Concurrent requests excluding metrics scrapes",
            registry=self.registry,
        )
        self.registry.register(DatasetCollector(service, repository))
