"""Reproducible, bounded import of IBM Research's public ITBench-Lite captures."""

import argparse
import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from ingest.replay import parse_dataset

REPOSITORY = "ibm-research/ITBench-Lite"
REVISION = "d0916b08ba421ce5e672e9ad68aa947d938dfef0"
PREFIX = "snapshots/sre/v0.2-B96DF826-4BB2-4B62-97AB-6D84254C53D7"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "seed" / "itbench"
OUTPUT = ROOT / "seed" / "itbench-replay.json"
SCENARIOS = {1: "Frontend proxy overload", 2: "Cart failure feature flag"}
LIMIT = 2 * 1024 * 1024


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fetch(url):
    with urllib.request.urlopen(url, timeout=40) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Public source file exceeded the 2 MB per-file limit.")
    return data


def download():
    """Fetch only two captures' alert snapshots, ground truth and dataset card."""
    metadata = json.loads(
        fetch(f"https://huggingface.co/api/datasets/{REPOSITORY}/revision/{REVISION}")
    )
    paths = ["README.md"]
    for row in metadata["siblings"]:
        path = row["rfilename"]
        if any(path.startswith(f"{PREFIX}/Scenario-{number}/") for number in SCENARIOS):
            if "/alerts/alerts_at_" in path or path.endswith("/ground_truth.yaml"):
                paths.append(path)
    if not 3 <= len(paths) <= 200:
        raise ValueError("Unexpected subset size; refusing an unbounded download.")

    def save(path):
        data = fetch(f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{path}")
        local = path.removeprefix(PREFIX + "/")
        target = RAW / local
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {
            "upstream_path": path,
            "local_path": local,
            "bytes": len(data),
            "sha256": digest(data),
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = list(pool.map(save, sorted(paths)))
    manifest = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "license": "Apache-2.0",
        "files": files,
    }
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def snapshot_time(path):
    # IBM's capture filenames omit the suffix; companion exports identify this clock as UTC.
    value = path.stem.removeprefix("alerts_at_")
    return datetime.strptime(value, "%Y-%m-%dT%H-%M-%S.%f").replace(tzinfo=UTC)


def linked_ground_truth(labels, truth):
    """Require name AND namespace AND service to match a declared alert group."""
    groups = {group["id"]: group for group in truth.get("groups", [])}
    for alert in truth.get("alerts", []):
        group = groups.get(alert.get("group_id"), {})
        if alert["id"] != labels.get("alertname") or group.get("kind") != "Service":
            continue
        if group.get("namespace") != labels.get("namespace"):
            continue
        service = labels.get("service_name", "")
        if service and any(re.fullmatch(pattern, service) for pattern in group.get("filter", [])):
            return alert["group_id"]
    return None


def normalize(raw=RAW):
    manifest_bytes = (raw / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["repository"] != REPOSITORY or manifest["revision"] != REVISION:
        raise ValueError("Unexpected dataset revision.")
    for item in manifest["files"]:
        path = (raw / item["local_path"]).resolve()
        if not path.is_relative_to(raw.resolve()):
            raise ValueError("Manifest path must stay inside the source directory.")
        content = path.read_bytes()
        if len(content) != item["bytes"] or digest(content) != item["sha256"]:
            raise ValueError(f"Source checksum mismatch: {item['local_path']}")
    alerts, events, incidents, captures = {}, [], [], []
    stats = {"snapshot_files": 0, "raw_rows": 0, "excluded_rows": 0, "duplicate_rows": 0}
    for number, title in SCENARIOS.items():
        scenario = f"Scenario-{number}"
        paths = sorted(raw.glob(f"{scenario}/alerts/alerts_at_*.json"))
        listed = {item["local_path"] for item in manifest["files"]}
        if f"{scenario}/ground_truth.yaml" not in listed:
            raise ValueError("Ground truth must be present in the verified manifest.")
        if not paths or any(path.relative_to(raw).as_posix() not in listed for path in paths):
            raise ValueError("Snapshot files must be present in the verified manifest.")
        truth = yaml.safe_load((raw / scenario / "ground_truth.yaml").read_text(encoding="utf-8"))
        start, end = snapshot_time(paths[0]), snapshot_time(paths[-1])
        incidents.append(
            {
                "id": scenario,
                "title": title,
                "started_at": start.isoformat(),
                "ended_at": end.isoformat(),
            }
        )
        seen = {}
        matched_groups = set()
        for path in paths:
            observed = snapshot_time(path)
            rows = json.loads(path.read_text(encoding="utf-8"))
            stats["snapshot_files"] += 1
            for row in rows:
                stats["raw_rows"] += 1
                labels = row["labels"]
                if row["state"] != "firing" or labels.get("severity") not in (
                    "warning",
                    "critical",
                ):
                    stats["excluded_rows"] += 1
                    continue
                # Label set + activeAt identifies one observed episode; changing values do not.
                identity = json.dumps([labels, row["activeAt"]], sort_keys=True).encode()
                episode = digest(identity)
                if episode in seen:
                    seen[episode]["observation_count"] += 1
                    seen[episode]["last_observed_at"] = observed.isoformat()
                    stats["duplicate_rows"] += 1
                    continue
                scope = {
                    key: labels.get(key, "")
                    for key in ("alertname", "namespace", "service_name", "job", "severity")
                }
                alert_id = digest(json.dumps(scope, sort_keys=True).encode())[:16]
                service = (
                    labels.get("service_name")
                    or labels.get("job")
                    or labels.get("namespace")
                    or "unscoped"
                )
                alerts[alert_id] = {
                    "id": alert_id,
                    "name": labels["alertname"],
                    "service": service,
                    "scope": scope,
                }
                group = linked_ground_truth(labels, truth)
                if group:
                    matched_groups.add((labels["alertname"], group))
                event = {
                    "id": f"{scenario}-{episode[:20]}",
                    "alert_id": alert_id,
                    "fired_at": observed.isoformat(),
                    "severity": "recorded",
                    "incident_id": scenario if group else None,
                    "provenance": {
                        "scenario": scenario,
                        "source_file": path.relative_to(raw).as_posix(),
                        "labels": labels,
                        "active_at": row["activeAt"],
                        "first_observed_at": observed.isoformat(),
                        "last_observed_at": observed.isoformat(),
                        "observation_count": 1,
                        "present_at_capture_start": observed == start,
                        "ground_truth_group": group,
                        "link_basis": "ground-truth alert name, namespace and service"
                        if group
                        else "unmatched",
                    },
                }
                seen[episode] = event["provenance"]
                events.append(event)
        expected = {(a["id"], a["group_id"]) for a in truth.get("alerts", [])}
        captures.append(
            {
                "id": scenario,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "snapshot_files": len(paths),
                "matched_ground_truth_alerts": len(matched_groups),
                "unmatched_ground_truth_alerts": [
                    list(x) for x in sorted(expected - matched_groups)
                ],
            }
        )
    document = {
        "schema_version": 1,
        "source": {
            "label": "IBM Research ITBench-Lite · two recorded SRE experiments",
            "description": "Recorded warning/critical alert episodes from fault-injected test systems. Ground-truth service links; first observed firing times. Not customer production data or paging history.",
            "synthetic": False,
            "incident_ledger_complete": False,
            "event_kind": "recorded_alert",
            "incident_kind": "benchmark_scenario",
            "url": f"https://huggingface.co/datasets/{REPOSITORY}",
            "revision": REVISION,
            "license": "Apache-2.0",
        },
        "window": {
            "start": min(x["started_at"] for x in incidents),
            "end": (
                max(datetime.fromisoformat(x["ended_at"]) for x in incidents)
                + timedelta(microseconds=1)
            ).isoformat(),
        },
        "alerts": sorted(alerts.values(), key=lambda a: (a["name"], a["service"], a["id"])),
        "incidents": incidents,
        "events": sorted(events, key=lambda e: (e["fired_at"], e["id"])),
        "provenance": {
            "manifest_sha256": digest(manifest_bytes),
            "captures": captures,
            "import_counts": stats,
            "timestamp_basis": "First snapshot containing this episode in firing state; filename clock interpreted as UTC. activeAt is preserved, not treated as notification time.",
        },
    }
    parse_dataset(document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download", action="store_true", help="Download the pinned small public subset first."
    )
    args = parser.parse_args()
    if args.download:
        download()
    document = normalize()
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "events": len(document["events"]),
                "rules": len(document["alerts"]),
                **document["provenance"]["import_counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
