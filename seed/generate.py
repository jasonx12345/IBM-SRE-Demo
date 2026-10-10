"""python -m seed.generate --seed 42 --months 6 [--output seed/events.json]."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

# Support both `python seed/generate.py` and `python -m seed.generate`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.synthetic import SyntheticSource


def main():
    parser = argparse.ArgumentParser(
        description="Replace the synthetic dataset or export deterministic JSON"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument(
        "--start", default="2026-04-01", help="First day of the first complete month"
    )
    parser.add_argument("--timezone", default="America/Toronto")
    parser.add_argument("--output", type=Path, help="Export JSON instead of writing to PostgreSQL")
    args = parser.parse_args()
    try:
        source = SyntheticSource(args.seed, args.months, args.start, args.timezone)
    except ValueError as error:
        parser.error(str(error))
    if args.output:
        payload = {"window": asdict(source.window), "events": [asdict(e) for e in source.events()]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, default=lambda value: value.isoformat(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Exported {len(payload['events'])} events to {args.output}")
        return
    from api.repository import PostgresRepository
    from ingest.pipeline import ingest

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("Set DATABASE_URL or use --output")
    repository = PostgresRepository(database_url)
    try:
        repository.initialize()
        count = ingest(source, repository)
        print(f"Ingested {count} events across {args.months} complete months (seed={args.seed}).")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
