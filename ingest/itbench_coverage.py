"""Import IBM Research ITBench-Lite alert captures for a conservative coverage audit."""

import argparse
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import yaml

from ingest.itbench import PREFIX, REPOSITORY, REVISION, ROOT, fetch, snapshot_time

RAW = ROOT / "seed" / "itbench-coverage"
OUTPUT = ROOT / "seed" / "itbench-coverage.json"
OLD_RAW = ROOT / "seed" / "itbench"
MAX_FILES = 2000


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_url(path):
    return f"https://huggingface.co/datasets/{REPOSITORY}/blob/{REVISION}/{PREFIX}/{path}"


def download(ground_truth_only=False):
    metadata = json.loads(
        fetch(f"https://huggingface.co/api/datasets/{REPOSITORY}/revision/{REVISION}")
    )
    paths = sorted(
        path.removeprefix(PREFIX + "/")
        for item in metadata["siblings"]
        if (path := item["rfilename"]).startswith(PREFIX + "/Scenario-")
        and (
            path.endswith("/ground_truth.yaml")
            or (not ground_truth_only and "/alerts/alerts_at_" in path)
        )
    )
    if not 35 <= len(paths) <= MAX_FILES:
        raise ValueError(f"Unexpected source file count: {len(paths)}")

    def save(path):
        target = RAW / path
        existing = OLD_RAW / path
        if target.exists():
            data = target.read_bytes()
        elif existing.exists():
            data = existing.read_bytes()
        else:
            data = fetch(
                f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{PREFIX}/{path}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return {"path": path, "bytes": len(data), "sha256": sha256(data)}

    with ThreadPoolExecutor(max_workers=12) as pool:
        files = list(pool.map(save, paths))
    manifest = {"repository": REPOSITORY, "revision": REVISION, "files": files}
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return len(files)


def group_matches(group, labels):
    """Match declared resource identity, never the alert name alone."""
    if group.get("kind") not in {"Service", "Pod"} or group.get("namespace") != labels.get(
        "namespace"
    ):
        return False
    label = "service_name" if group["kind"] == "Service" else "pod"
    value = labels.get(label, "")
    return bool(value and any(re.fullmatch(pattern, value) for pattern in group.get("filter", [])))


def build_report(raw=RAW):
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    if manifest["repository"] != REPOSITORY or manifest["revision"] != REVISION:
        raise ValueError("Unexpected source revision")
    listed = {}
    for item in manifest["files"]:
        path = (raw / item["path"]).resolve()
        if not path.is_relative_to(raw.resolve()):
            raise ValueError("Source path escaped raw directory")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
            raise ValueError(f"Checksum mismatch: {item['path']}")
        listed[item["path"]] = path

    scenarios = []
    totals = Counter()
    scenario_ids = sorted(
        (p.split("/")[0] for p in listed if p.endswith("/ground_truth.yaml")),
        key=lambda value: int(value.split("-")[1]),
    )
    for sid in scenario_ids:
        truth_path = f"{sid}/ground_truth.yaml"
        truth = yaml.safe_load(listed[truth_path].read_text(encoding="utf-8"))
        groups = {g["id"]: g for g in truth.get("groups", [])}
        snapshot_paths = sorted(p for p in listed if p.startswith(sid + "/alerts/alerts_at_"))
        observations = []
        observed_rows = 0
        for path in snapshot_paths:
            rows = json.loads(listed[path].read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError(f"Unexpected alert snapshot: {path}")
            observed_rows += len(rows)
            for row in rows:
                labels = row.get("labels", {})
                if row.get("state") == "firing" and labels.get("alertname"):
                    observations.append(
                        {
                            "labels": labels,
                            "path": path,
                            "at": snapshot_time(listed[path]).isoformat(),
                        }
                    )

        expected = []
        for alert in truth.get("alerts", []):
            group = groups.get(alert.get("group_id"), {})
            name = alert["id"]
            matches = [
                o
                for o in observations
                if o["labels"].get("alertname") == name and group_matches(group, o["labels"])
            ]
            identity_label = "service_name" if group.get("kind") == "Service" else "pod"
            ambiguous = any(
                o["labels"].get("alertname") == name
                and o["labels"].get("namespace") == group.get("namespace")
                and not o["labels"].get(identity_label)
                for o in observations
            )
            if not snapshot_paths:
                status = "unknown"
                reason = "No alert snapshots were published for this experiment."
            elif (
                group.get("kind") not in {"Service", "Pod"}
                or not group.get("filter")
                or not group.get("namespace")
            ):
                status = "unknown"
                reason = "The declared group cannot be matched to an available resource label conservatively."
            elif not matches and ambiguous:
                status = "unknown"
                reason = "A same-name alert exists, but its resource label is missing."
            else:
                status = "observed" if matches else "not_observed"
                reason = None
            first = matches[0] if matches else None
            expected.append(
                {
                    "name": name,
                    "group_id": alert.get("group_id"),
                    "service": group.get("id", "unknown group"),
                    "namespace": group.get("namespace"),
                    "status": status,
                    "reason": reason,
                    "first_observed_at": first["at"] if first else None,
                    "evidence_file": first["path"] if first else None,
                    "evidence_url": source_url(first["path"]) if first else None,
                }
            )
            totals[status] += 1

        fault = truth.get("fault", [])
        fault_names = [f.get("entity", {}).get("name") for f in fault if isinstance(f, dict)]
        fault_names = [str(n) for n in fault_names if n]
        scenarios.append(
            {
                "id": sid,
                "fault": ", ".join(fault_names[:3]) or "Fault injection",
                "snapshot_count": len(snapshot_paths),
                "alert_rows": observed_rows,
                "capture_start": snapshot_time(listed[snapshot_paths[0]]).isoformat()
                if snapshot_paths
                else None,
                "capture_end": snapshot_time(listed[snapshot_paths[-1]]).isoformat()
                if snapshot_paths
                else None,
                "expected": expected,
                "ground_truth_url": source_url(truth_path),
            }
        )
    return {
        "source": {
            "name": "IBM Research ITBench-Lite",
            "repository": REPOSITORY,
            "revision": REVISION,
            "url": f"https://huggingface.co/datasets/{REPOSITORY}",
            "license": "Apache-2.0",
            "kind": "Public fault-injection benchmark, not IBM customer production data",
        },
        "totals": {
            "scenarios": len(scenarios),
            "snapshots": sum(s["snapshot_count"] for s in scenarios),
            "expected": sum(totals.values()),
            "observed": totals["observed"],
            "not_observed": totals["not_observed"],
            "unknown": totals["unknown"],
        },
        "scenarios": scenarios,
        "method": "Match each ground-truth alert name to a firing snapshot alert with the declared namespace and full service-name or pod-name regex. A missing match means not observed in the published snapshots, not that monitoring failed or no page was sent.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--ground-truth-only", action="store_true")
    args = parser.parse_args()
    if args.download:
        print(f"Downloaded {download(args.ground_truth_only)} verified source files", flush=True)
    if not args.ground_truth_only:
        report = build_report()
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["totals"]), flush=True)


if __name__ == "__main__":
    main()
