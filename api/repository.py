"""All database access is isolated here; routes depend on the repository interface."""

from dataclasses import asdict
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ingest.source import AlertEvent, ObservationWindow

EVENT_COLUMNS = tuple(AlertEvent.__dataclass_fields__)
INGESTION_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, float("inf"))


class PostgresRepository:
    def __init__(self, database_url: str):
        self.pool = ConnectionPool(
            database_url,
            open=True,
            min_size=0,
            max_size=5,
            timeout=3,
            kwargs={
                "row_factory": dict_row,
                "connect_timeout": 3,
                "options": "-c statement_timeout=5000",
            },
        )

    def initialize(self) -> None:
        with self.pool.connection() as connection:
            # Serialize idempotent schema installation when two replicas start together.
            connection.execute("SELECT pg_advisory_xact_lock(87412030)")
            connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def ready(self) -> bool:
        with self.pool.connection() as connection:
            connection.execute("SELECT id FROM dataset_metadata LIMIT 1")
            connection.execute("SELECT id FROM alert_event LIMIT 1")
        return True

    def load_dataset(self) -> tuple[list[AlertEvent], ObservationWindow | None, str | None]:
        with self.pool.connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            metadata = connection.execute("SELECT * FROM dataset_metadata WHERE id = 1").fetchone()
            rows = connection.execute(
                f"SELECT {', '.join(EVENT_COLUMNS)} FROM alert_event ORDER BY fired_at, id"
            ).fetchall()
        if metadata is None:
            return [], None, None
        window = ObservationWindow(
            metadata["start_at"],
            metadata["end_at"],
            metadata["months"],
            metadata["timezone"],
            metadata["source"],
            metadata["seed"],
        )
        return [AlertEvent(**row) for row in rows], window, metadata["ingested_at"].isoformat()

    def replace_dataset(self, events: list[AlertEvent], window: ObservationWindow) -> None:
        """Replace the demo dataset atomically; reruns never append duplicates."""
        with self.pool.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(87412031)")
            # DELETE is MVCC-safe for concurrent readers; TRUNCATE is not.
            connection.execute("DELETE FROM alert_event")
            with connection.cursor().copy(
                f"COPY alert_event ({', '.join(EVENT_COLUMNS)}) FROM STDIN"
            ) as copy:
                for event in events:
                    data = asdict(event)
                    copy.write_row(tuple(data[key] for key in EVENT_COLUMNS))
            connection.execute(
                """
                INSERT INTO dataset_metadata (id, start_at, end_at, months, timezone, source, seed)
                VALUES (1, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET start_at=EXCLUDED.start_at, end_at=EXCLUDED.end_at,
                    months=EXCLUDED.months, timezone=EXCLUDED.timezone, source=EXCLUDED.source,
                    seed=EXCLUDED.seed, ingested_at=now()
                """,
                (
                    window.start,
                    window.end,
                    window.months,
                    window.timezone,
                    window.source,
                    window.seed,
                ),
            )

    def record_ingestion(self, duration: float, count: int, status: str) -> None:
        with self.pool.connection() as connection:
            connection.execute(
                "INSERT INTO ingestion_run (duration_seconds, event_count, status) VALUES (%s, %s, %s)",
                (duration, count, status),
            )

    def ingestion_metrics(self) -> dict:
        with self.pool.connection() as connection:
            totals = connection.execute("""
                SELECT count(*) AS count, coalesce(sum(duration_seconds), 0) AS sum,
                    coalesce(sum(event_count) FILTER (WHERE status = 'success'), 0) AS events,
                    count(*) FILTER (WHERE status = 'error') AS errors,
                    extract(epoch FROM max(finished_at)) AS last_timestamp
                FROM ingestion_run
            """).fetchone()
            buckets = connection.execute(
                """
                SELECT bound, count(r.id) AS count
                FROM unnest(%s::double precision[]) AS bound
                LEFT JOIN ingestion_run r ON r.duration_seconds <= bound
                GROUP BY bound ORDER BY bound
            """,
                (list(INGESTION_BUCKETS),),
            ).fetchall()
        return {
            **totals,
            "buckets": [
                (str(row["bound"]) if row["bound"] != float("inf") else "+Inf", row["count"])
                for row in buckets
            ],
        }

    def close(self) -> None:
        self.pool.close()
