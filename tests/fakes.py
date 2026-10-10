from datetime import UTC, datetime

from api.repository import INGESTION_BUCKETS


class MemoryRepository:
    """Test double only; the application always uses PostgreSQL by default."""

    def __init__(self, source=None):
        self.events = list(source.events()) if source else []
        self.window = source.window if source else None
        self.runs = []
        self.healthy = True

    def load_dataset(self):
        return (
            self.events,
            self.window,
            datetime(2026, 10, 1, tzinfo=UTC).isoformat() if self.window else None,
        )

    def ready(self):
        return self.healthy

    def replace_dataset(self, events, window):
        self.events, self.window = events, window

    def record_ingestion(self, duration, count, status):
        self.runs.append((duration, count, status))

    def ingestion_metrics(self):
        if not self.healthy:
            raise ConnectionError("Test database unavailable")
        return {
            "sum": sum(row[0] for row in self.runs),
            "events": sum(row[1] for row in self.runs if row[2] == "success"),
            "errors": sum(row[2] == "error" for row in self.runs),
            "last_timestamp": 0,
            "buckets": [
                (
                    str(bound) if bound != float("inf") else "+Inf",
                    sum(row[0] <= bound for row in self.runs),
                )
                for bound in INGESTION_BUCKETS
            ],
        }
