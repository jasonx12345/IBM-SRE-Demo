"""Source boundary for a future Alertmanager adapter; no network integration."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AlertEvent:
    alert_name: str
    service: str
    severity: str
    fired_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    auto_resolved: bool
    incident_id: str | None
    responder_count: int
    manual_action: bool
    runbook_action: str | None

    def validate(self) -> None:
        if not self.alert_name or not self.service:
            raise ValueError("Alert name and service must be non-empty")
        if self.severity not in {"page", "ticket", "info"}:
            raise ValueError("Unknown severity")
        if self.responder_count < 0:
            raise ValueError("Responder count cannot be negative")
        for value in (self.fired_at, self.acknowledged_at, self.resolved_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("All timestamps must include a timezone")
        if self.acknowledged_at and self.acknowledged_at < self.fired_at:
            raise ValueError("Acknowledgement precedes firing")
        if self.resolved_at and self.resolved_at < (self.acknowledged_at or self.fired_at):
            raise ValueError("Resolution precedes firing or acknowledgement")
        if self.auto_resolved and (
            self.manual_action or self.acknowledged_at is not None or self.resolved_at is None
        ):
            raise ValueError("Auto-resolution requires resolution with no human acknowledgement")


@dataclass(frozen=True)
class ObservationWindow:
    start: datetime
    end: datetime
    months: int
    timezone: str
    source: str
    seed: int | None = None


class Source(ABC):
    """Adapters emit normalized events plus an explicit [start, end) coverage window.

    Coverage must be supplied, never inferred from first/last event. A future
    adapter can paginate its upstream data inside events() without changing scoring.
    """

    @property
    @abstractmethod
    def window(self) -> ObservationWindow: ...

    @abstractmethod
    def events(self) -> Iterable[AlertEvent]: ...
