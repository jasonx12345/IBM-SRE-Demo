import logging
from time import perf_counter

from ingest.source import Source


def ingest(source: Source, repository) -> int:
    started = perf_counter()
    events = []
    try:
        events = list(source.events())
        window = source.window
        if window.months <= 0 or window.end <= window.start:
            raise ValueError("Invalid observation window")
        for event in events:
            event.validate()
            if not window.start <= event.fired_at < window.end:
                raise ValueError("Event outside declared observation window")
        repository.replace_dataset(events, window)
    except Exception:
        try:
            repository.record_ingestion(perf_counter() - started, 0, "error")
        except Exception:
            logging.exception("Could not persist failed ingestion measurement")
        raise
    repository.record_ingestion(perf_counter() - started, len(events), "success")
    return len(events)
