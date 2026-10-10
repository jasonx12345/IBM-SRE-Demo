import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(directory: Path | None = None) -> dict:
    directory = directory or Path(os.environ.get("CONFIG_DIR", ROOT / "config"))
    config = {}
    for name in ("thresholds", "model", "slo"):
        with (directory / f"{name}.yaml").open(encoding="utf-8") as handle:
            config[name] = yaml.safe_load(handle)
    expected = {
        "automate": {"min_manual_rate", "min_runbook_repeat", "min_occurrences"},
        "tune": {"min_occurrences", "max_incident_rate", "min_auto_resolve"},
        "delete": {"min_occurrences", "max_manual_rate", "max_incident_rate"},
        "keep_human": {"max_occurrences"},
    }
    for category, keys in expected.items():
        section = config["thresholds"][category]
        if set(section) != keys:
            raise ValueError(f"Invalid threshold keys for {category}")
        for key, value in section.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Invalid threshold: {category}.{key}")
            if "occurrences" in key:
                if not isinstance(value, int):
                    raise ValueError(f"Occurrence threshold must be an integer: {key}")
            elif value > 1:
                raise ValueError(f"Rate must be in [0, 1]: {key}")
    model = config["model"]
    ZoneInfo(model["timezone"])
    if not 0 <= model["business_hours_start"] < model["business_hours_end"] <= 24:
        raise ValueError("Invalid business hours")
    if model["cache_seconds"] < 0:
        raise ValueError("Cache duration must be nonnegative")
    for key in ("automation_savings_fraction", "deletion_savings_fraction"):
        if not 0 <= model[key] <= 1:
            raise ValueError(f"{key} must be in [0, 1]")
    for objective in (
        config["slo"]["latency"]["objective"],
        config["slo"]["availability"]["objective"],
    ):
        if not 0 < objective < 1:
            raise ValueError("SLO objectives must be in (0, 1)")
    if config["slo"]["latency"]["threshold_seconds"] <= 0:
        raise ValueError("Latency threshold must be positive")
    return config
