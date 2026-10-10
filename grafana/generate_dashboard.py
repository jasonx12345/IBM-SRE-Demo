"""Keep a readable source for the provisioned dashboard JSON."""

import json
from pathlib import Path

import yaml


def panel(id, title, expr, unit, x, y, w=8, kind="timeseries", legend="__auto"):
    return {
        "id": id,
        "title": title,
        "type": kind,
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7 if kind != "stat" else 4, "w": w, "x": x, "y": y},
        "targets": [{"expr": expr, "refId": "A", "legendFormat": legend}],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "palette-classic"},
                "custom": {"lineWidth": 2, "fillOpacity": 10},
            },
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "reduceOptions": {"calcs": ["lastNotNull"]},
        },
    }


def burn_panel(id, title, signal, budget, short, long, x, y):
    # Separate targets preserve window identity. Arithmetic drops __name__, so
    # a selector matching both recording-rule names causes duplicate label sets.
    result = panel(
        id,
        title,
        f"toil_budget:api_{signal}_ratio:{short} / {budget:g}",
        "none",
        x,
        y,
        legend=short,
    )
    result["targets"].append(
        {
            "expr": f"toil_budget:api_{signal}_ratio:{long} / {budget:g}",
            "refId": "B",
            "legendFormat": long,
        }
    )
    return result


def build_dashboard():
    slo = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config/slo.yaml").read_text(encoding="utf-8")
    )
    latency_budget = 1 - slo["latency"]["objective"]
    error_budget = 1 - slo["availability"]["objective"]
    short = slo["burn_alerts"]["fast"]["short_window"]
    long = slo["burn_alerts"]["fast"]["long_window"]
    return {
        "uid": "toil-budget",
        "title": "Toil Budget · analysis & service health",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "15s",
        "timezone": "browser",
        "tags": ["sre", "toil", "slo"],
        "time": {"from": "now-1h", "to": "now"},
        "panels": [
            {
                "id": 1,
                "type": "text",
                "title": "Model assumptions",
                "gridPos": {"x": 0, "y": 0, "w": 24, "h": 3},
                "options": {
                    "mode": "markdown",
                    "content": f"All toil figures are **estimates**. Annualization uses explicit dataset coverage. Runbook repeat is the automation-confidence proxy. Shared dataset metrics use `max` across replicas; request metrics use `sum`. See MODEL.md and LIMITATIONS.md. SLO: {slo['latency']['objective']:.0%} of API requests within {slo['latency']['threshold_seconds'] * 1000:g} ms, fewer than {error_budget:.0%} HTTP 5xx over {slo['window_days']} days.",
                },
            },
            panel(
                2,
                "Estimated annual toil hours",
                'sum(max by(alert_name) (toil_budget_estimated_annual_toil_hours{job="toil-budget"}))',
                "h",
                0,
                3,
                kind="stat",
            ),
            panel(
                3,
                "Estimated annual hours recoverable · top 3",
                'max(toil_budget_automation_recoverable_hours{job="toil-budget"})',
                "h",
                8,
                3,
                kind="stat",
            ),
            panel(
                4,
                "Alerts analysed",
                'sum(max by(alert_name) (toil_budget_alert_occurrences{job="toil-budget"}))',
                "short",
                16,
                3,
                kind="stat",
            ),
            panel(
                5,
                "Estimated annual toil hours by alert",
                'max by(alert_name, classification) (toil_budget_estimated_annual_toil_hours{job="toil-budget"})',
                "h",
                0,
                7,
                w=12,
                legend="{{alert_name}} · {{classification}}",
            ),
            panel(
                6,
                "Runbook repeat rate",
                'max by(alert_name) (toil_budget_runbook_repeat_rate{job="toil-budget"})',
                "percentunit",
                12,
                7,
                w=12,
                legend="{{alert_name}}",
            ),
            panel(
                7,
                "Traffic · API requests / second",
                'sum by(status) (rate(toil_budget_http_requests_total{job="toil-budget",scope="api"}[$__rate_interval]))',
                "reqps",
                0,
                14,
                legend="HTTP {{status}}",
            ),
            panel(
                8,
                "Latency · API p99",
                'histogram_quantile(0.99, sum by(le) (rate(toil_budget_http_request_duration_seconds_bucket{job="toil-budget",scope="api"}[$__rate_interval])))',
                "s",
                8,
                14,
            ),
            panel(
                9,
                f"Errors · API 5xx ratio ({short})",
                f"toil_budget:api_error_ratio:{short}",
                "percentunit",
                16,
                14,
            ),
            panel(
                10,
                "Saturation · active requests per replica",
                'toil_budget_http_requests_in_flight{job="toil-budget"}',
                "short",
                0,
                21,
                legend="{{instance}}",
            ),
            burn_panel(
                11,
                f"Latency SLO burn · {short} / {long}",
                "slow",
                latency_budget,
                short,
                long,
                8,
                21,
            ),
            panel(
                12,
                "Availability · app and database",
                'min by(instance) ({__name__=~"up|toil_budget_database_up",job="toil-budget"})',
                "short",
                16,
                21,
                legend="{{instance}}",
            ),
            panel(
                13,
                "Ingestion · mean recorded duration",
                'max(toil_budget_ingestion_duration_seconds_sum{job="toil-budget"}) / clamp_min(max(toil_budget_ingestion_duration_seconds_count{job="toil-budget"}), 1)',
                "s",
                0,
                28,
            ),
            panel(
                14,
                "Ingestion · recorded failures",
                'max(toil_budget_ingestion_errors_total{job="toil-budget"})',
                "short",
                8,
                28,
            ),
            burn_panel(
                15,
                f"Error SLO burn · {short} / {long}",
                "error",
                error_budget,
                short,
                long,
                16,
                28,
            ),
        ],
    }


if __name__ == "__main__":
    Path(__file__).with_name("dashboard.json").write_text(
        json.dumps(build_dashboard(), indent=2) + "\n", encoding="utf-8"
    )
