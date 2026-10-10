from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from threading import RLock
from time import monotonic

from analysis.score import score_events


class AnalysisService:
    def __init__(self, repository, config: dict):
        self.repository = repository
        self.config = config
        self._cached = None
        self._expires = 0.0
        self._lock = RLock()

    def snapshot(self) -> dict:
        with self._lock:
            if self._cached is not None and monotonic() < self._expires:
                return self._cached
            events, window, ingested_at = self.repository.load_dataset()
            alerts = score_events(events, window, self.config) if window else []
            counts = Counter(row["classification"] for row in alerts)
            recommendations = {}
            for category, fraction_key in (
                ("automate", "automation_savings_fraction"),
                ("delete", "deletion_savings_fraction"),
            ):
                candidates = [row for row in alerts if row["classification"] == category]
                # Automation: reclaimable modeled time. Deletion: remove most noise first;
                # no-action noise can have zero modeled toil and still deserve removal.
                if category == "delete":
                    candidates.sort(key=lambda row: (-row["occurrences"], row["alert_name"]))
                recommendations[category] = [
                    {
                        **row,
                        "estimated_annual_hours_saved": (
                            row["estimated_annual_toil_hours"] * self.config["model"][fraction_key]
                            if row["estimated_annual_toil_hours"] is not None
                            else None
                        ),
                    }
                    for row in candidates[:3]
                ]
            pages = [event for event in events if event.severity == "page"]
            page_after_hours = (
                sum(row["after_hours_page_rate"] * row["pages"] for row in alerts if row["pages"])
                / len(pages)
                if pages
                else None
            )
            metadata = asdict(window) if window else None
            if metadata:
                metadata["start"] = window.start.isoformat()
                metadata["end"] = window.end.isoformat()
            snapshot = {
                "alerts": alerts,
                "recommendations": recommendations,
                "summary": {
                    "estimated_annual_toil_hours": sum(
                        row["estimated_annual_toil_hours"] or 0 for row in alerts
                    ),
                    "alerts_analysed": len(events),
                    "alert_types_analysed": len(alerts),
                    "classification_counts": {
                        key: counts[key]
                        for key in ("automate", "tune", "delete", "keep_human", "unclassified")
                    },
                    "classification_shares": {
                        key: counts[key] / len(alerts) if alerts else 0
                        for key in ("automate", "tune", "delete", "keep_human", "unclassified")
                    },
                    "top_three_automation_estimated_annual_hours_saved": sum(
                        row["estimated_annual_hours_saved"] or 0
                        for row in recommendations["automate"]
                    ),
                    "unestimable_alert_types": sum(
                        row["estimated_annual_toil_hours"] is None for row in alerts
                    ),
                    "manual_duration_missing": sum(
                        row["manual_duration_missing"] for row in alerts
                    ),
                    "after_hours_page_rate": page_after_hours,
                    "window": metadata,
                    "ingested_at": ingested_at,
                    "computed_at": datetime.now(UTC).isoformat(),
                    "assumptions": self.config["model"],
                    "thresholds": self.config["thresholds"],
                    "slo": self.config["slo"],
                    "savings_note": "Gross annualized estimates assuming configured intervention coverage; excludes implementation and maintenance costs.",
                    "share_denominator": "alert types",
                },
            }
            self._cached = snapshot
            self._expires = monotonic() + self.config["model"]["cache_seconds"]
            return snapshot
