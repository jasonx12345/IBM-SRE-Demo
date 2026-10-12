import atexit
import json
import logging
import os
from time import perf_counter

import psycopg
from flask import Flask, g, jsonify, request, send_from_directory
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from psycopg_pool import PoolTimeout
from werkzeug.exceptions import HTTPException

from analysis.retirement import replay
from analysis.service import AnalysisService
from api.metrics import AppMetrics
from api.repository import PostgresRepository
from api.settings import ROOT, load_config
from ingest.replay import load_dataset, parse_dataset
from ingest.replay_demo import build_demo


def create_app(repository=None, config=None):
    app = Flask(__name__, static_folder=str(ROOT / "ui"), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    config = config or load_config()
    if repository is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        repository = PostgresRepository(url)
        repository.initialize()
        atexit.register(repository.close)
    service = AnalysisService(repository, config)
    metrics = AppMetrics(service, repository, config)
    app.extensions.update(repository=repository, analysis=service, metrics=metrics)
    replay_path = os.environ.get("REPLAY_DATASET")
    replay_dataset = load_dataset(ROOT / (replay_path or "seed/itbench-replay.json"))
    app.extensions["replay_dataset"] = replay_dataset
    coverage_path = ROOT / "seed" / "itbench-coverage.json"
    coverage_report = (
        json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else None
    )

    @app.before_request
    def start_request():
        g.request_started = perf_counter()
        if request.path != "/metrics":
            metrics.in_flight.inc()

    @app.after_request
    def finish_request(response):
        if request.path != "/metrics":
            route = request.url_rule.rule if request.url_rule else "unmatched"
            scope = "api" if request.path == "/api" or request.path.startswith("/api/") else "other"
            metrics.requests.labels(request.method, route, str(response.status_code), scope).inc()
            metrics.latency.labels(request.method, route, scope).observe(
                perf_counter() - g.request_started
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.teardown_request
    def end_request(error):
        if request.path != "/metrics" and hasattr(g, "request_started"):
            metrics.in_flight.dec()

    @app.errorhandler(Exception)
    def handle_error(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.name, message=error.description), error.code
        if isinstance(error, (psycopg.Error, PoolTimeout)):
            app.logger.exception("Database request failed")
            return jsonify(
                error="database_unavailable", message="Database unavailable. Try again shortly."
            ), 503
        app.logger.exception("Request failed")
        return jsonify(error="internal_error", message="The request could not be completed."), 500

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "ui", "coverage.html")

    @app.get("/api/coverage/report")
    def coverage():
        if coverage_report is None:
            return jsonify(
                error="report_unavailable", message="Run the IBM coverage importer first."
            ), 503
        return jsonify(coverage_report)

    @app.get("/toil")
    def toil():
        return send_from_directory(ROOT / "ui", "index.html")

    @app.get("/docs/<name>")
    def document(name):
        if name not in {
            "MODEL.md",
            "LIMITATIONS.md",
            "OPERATIONS.md",
            "RESEARCH.md",
            "REPLAY.md",
            "DEMO.md",
            "IBM_DATA.md",
            "IBM_RESEARCH.md",
            "COVERAGE.md",
        }:
            return jsonify(error="not_found"), 404
        return send_from_directory(ROOT / "docs", name, mimetype="text/plain; charset=utf-8")

    @app.get("/api/retirement/dataset")
    def retirement_dataset():
        if request.args.get("example") == "synthetic":
            return jsonify(build_demo())
        return jsonify(replay_dataset.document)

    @app.post("/api/retirement/replay")
    def retirement_replay():
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="invalid_replay", message="Request must be a JSON object."), 400
        try:
            data = parse_dataset(payload["dataset"]) if "dataset" in payload else replay_dataset
            result = replay(data, payload.get("retire", []), payload.get("max_delay_minutes", 5))
        except ValueError as error:
            return jsonify(error="invalid_replay", message=str(error)), 400
        return jsonify(result)

    @app.get("/api/summary")
    def summary():
        return jsonify(service.snapshot()["summary"])

    @app.get("/api/alerts")
    def alerts():
        return jsonify(service.snapshot()["alerts"])

    @app.get("/api/alerts/<name>")
    def detail(name):
        row = next((row for row in service.snapshot()["alerts"] if row["alert_name"] == name), None)
        if row is None:
            return jsonify(error="not_found", message="Unknown alert name."), 404
        return jsonify(row)

    @app.get("/api/recommendations")
    def recommendations():
        return jsonify(service.snapshot()["recommendations"])

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/readyz")
    def ready():
        try:
            if repository.ready():
                return jsonify(status="ready")
        except Exception:
            logging.warning("Readiness DB check failed", exc_info=True)
        return jsonify(status="not_ready"), 503

    @app.get("/metrics")
    def prometheus_metrics():
        return app.response_class(
            generate_latest(metrics.registry), content_type=CONTENT_TYPE_LATEST
        )

    return app
