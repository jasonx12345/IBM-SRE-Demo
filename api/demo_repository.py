"""Explicit in-memory demo repository for the original toil-analysis view."""

from datetime import UTC, datetime

from api.repository import INGESTION_BUCKETS
from ingest.synthetic import SyntheticSource


class DemoRepository:
    is_demo = True

    def __init__(self):
        source = SyntheticSource()
        self.events = list(source.events())
        self.window = source.window
        self.loaded_at = datetime.now(UTC).isoformat()

    def load_dataset(self):
        return self.events, self.window, self.loaded_at

    def ready(self):
        return True

    def ingestion_metrics(self):
        return {
            "sum": 0,
            "events": 0,
            "errors": 0,
            "last_timestamp": 0,
            "buckets": [
                (str(bound) if bound != float("inf") else "+Inf", 0) for bound in INGESTION_BUCKETS
            ],
        }
