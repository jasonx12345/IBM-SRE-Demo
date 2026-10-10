import calendar
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ingest.source import AlertEvent, ObservationWindow, Source


def add_months(value: datetime, months: int) -> datetime:
    index = value.year * 12 + value.month - 1 + months
    return value.replace(year=index // 12, month=index % 12 + 1)


class SyntheticSource(Source):
    """Clock-independent fixture with differentiated remediation patterns and storms."""

    ARCHETYPES = (
        (
            "redis_memory_pressure",
            "cache",
            "page",
            30,
            0.85,
            0.12,
            0.02,
            "flush_cache",
            0.94,
            (10, 15),
        ),
        ("disk_usage_high", "storage", "page", 20, 0.90, 0.08, 0.01, "prune_logs", 0.98, (5, 8)),
        ("cert_expiry_warning", "edge", "ticket", 8, 1.0, 0.0, 0.0, "rotate_cert", 1.0, (18, 22)),
        (
            "worker_queue_depth_warning",
            "workers",
            "page",
            95,
            0.02,
            0.92,
            0.02,
            "scale_workers",
            0.5,
            (2, 4),
        ),
        ("cpu_throttling_warning", "compute", "info", 60, 0.0, 0.90, 0.0, None, 0.0, (1, 3)),
        (
            "pod_crashloopbackoff",
            "platform",
            "page",
            25,
            0.75,
            0.20,
            0.12,
            "restart_pod",
            0.50,
            (8, 25),
        ),
        (
            "db_connection_pool_saturation",
            "database",
            "page",
            4,
            1.0,
            0.0,
            1.0,
            None,
            0.0,
            (40, 90),
        ),
        ("deploy_failed", "delivery", "page", 12, 1.0, 0.0, 0.08, None, 0.0, (10, 35)),
    )

    def __init__(
        self,
        seed: int = 42,
        months: int = 6,
        start: str = "2026-04-01",
        timezone_name: str = "America/Toronto",
    ):
        if not 1 <= months <= 120:
            raise ValueError("months must be between 1 and 120")
        beginning = datetime.fromisoformat(start).replace(tzinfo=ZoneInfo(timezone_name))
        if beginning.day != 1 or beginning.time().isoformat() != "00:00:00":
            raise ValueError("start must be the first day of a month (YYYY-MM-01)")
        self._window = ObservationWindow(
            beginning, add_months(beginning, months), months, timezone_name, "synthetic", seed
        )
        self.seed = seed

    @property
    def window(self) -> ObservationWindow:
        return self._window

    def events(self) -> list[AlertEvent]:
        rng = random.Random(self.seed)
        drafts = []
        for month in range(self.window.months):
            start = add_months(self.window.start, month)
            for archetype in self.ARCHETYPES:
                count = max(1, round(archetype[3] * rng.uniform(0.9, 1.1)))
                for _ in range(count):
                    drafts.append(
                        (
                            archetype,
                            start.replace(
                                day=rng.randint(1, calendar.monthrange(start.year, start.month)[1])
                            ),
                            False,
                        )
                    )
        # Two distinct nights, including when only one month is requested.
        for month, day in ((0, 8), (self.window.months - 1, 22)):
            night = add_months(self.window.start, month).replace(day=day, hour=2)
            for index in range(48):
                drafts.append((self.ARCHETYPES[3], night + timedelta(seconds=index * 24), True))
        page_indices = [i for i, (a, _, _) in enumerate(drafts) if a[2] == "page"]
        storm_indices = {i for i, (_, _, storm) in enumerate(drafts) if storm}
        # Include storms in the 35% page target, rather than adding them afterwards.
        outside = set(storm_indices)
        candidates = [i for i in page_indices if i not in storm_indices]
        outside.update(
            rng.sample(candidates, max(0, round(len(page_indices) * 0.35) - len(storm_indices)))
        )
        events = []
        for index, (archetype, day, storm) in enumerate(drafts):
            (
                name,
                service,
                severity,
                _,
                manual_rate,
                auto_rate,
                incident_rate,
                action,
                repeat,
                duration,
            ) = archetype
            if storm:
                fired = day
            else:
                off_hours = index in outside if severity == "page" else rng.random() < 0.35
                hour = (
                    rng.choice(list(range(0, 9)) + list(range(17, 24)))
                    if off_hours
                    else rng.randrange(9, 17)
                )
                fired = day.replace(hour=hour, minute=rng.randrange(60), second=rng.randrange(60))
            # Arithmetic in UTC keeps acknowledge/resolve intervals correct through DST.
            fired = fired.astimezone(UTC)
            draw = rng.random()
            manual = draw < manual_rate
            auto = not manual and draw < manual_rate + auto_rate
            ack = fired + timedelta(minutes=rng.uniform(0.5, 6)) if manual else None
            if manual:
                resolved = ack + timedelta(minutes=rng.uniform(*duration))
            else:
                resolved = fired + timedelta(
                    minutes=rng.uniform(0.25, 2.9) if auto else rng.uniform(4, 15)
                )
                # The remaining non-auto cases were acknowledged but needed no action.
                if not auto:
                    ack = fired + timedelta(seconds=rng.uniform(5, 45))
            runbook = (
                (action if action and rng.random() < repeat else f"investigate_{name}_{index:05d}")
                if manual
                else None
            )
            responders = (
                rng.choice((2, 3))
                if name == "db_connection_pool_saturation"
                else (1 if manual else 0)
            )
            incident = f"inc-{index:05d}" if rng.random() < incident_rate else None
            event = AlertEvent(
                name,
                service,
                severity,
                fired,
                ack,
                resolved,
                auto,
                incident,
                responders,
                manual,
                runbook,
            )
            event.validate()
            events.append(event)
        return sorted(events, key=lambda event: (event.fired_at, event.alert_name))
