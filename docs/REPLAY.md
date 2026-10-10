# Alert Retirement Lab: replay contract

The lab answers a narrow question: **If these paging rules were removed together, which recorded incidents would lose or receive a later first page?** It does not estimate human attention, evaluate monitoring queries, or predict future incidents.

## Run locally

```powershell
.venv\Scripts\python.exe -m api.demo --port 8001
```

Open http://127.0.0.1:8001/. No database, Docker, Kubernetes, cloud account, or API key is needed. The original toil dashboard remains at `/toil`. The lab defaults to IBM Research ITBench-Lite captures; the original toil dashboard and optional teaching examples remain explicitly synthetic. See [IBM_DATA.md](IBM_DATA.md) for source files and normalization.

For a fresh checkout, install Python 3.11+, create `.venv` with `python -m venv .venv`, then run `.venv\Scripts\python.exe -m pip install -r requirements.txt`. The server binds to localhost. This command is for the local demo; it is not an internet deployment command.

## Calculation

For each incident in the independent ledger:

1. Find explicitly linked events: severity `page` in paging mode, or `recorded` when `source.event_kind` is `recorded_alert`. Order by event timestamp and ID. The earliest is the baseline first event. In recorded mode, coverage means matched benchmark alert observations, not pager delivery.
2. Remove events belonging to the selected alert IDs as a single batch.
3. Find the earliest remaining page. Added delay is `(remaining first page - baseline first page)` in minutes.
4. Classify: `baseline_gap` if no original page existed; `lost` if all pages disappear; `late` if added delay exceeds the configured budget; `delayed` if the delay is positive but within budget; otherwise `unchanged`. Equality with the budget is allowed. Lost warnings have a null delay, never zero.
5. Compare the batch with the same alerts removed one at a time. A combination conflict is an incident that fails only in the batch, while each single removal stays within the budget for that incident.

The first-page reference is the original first page, not incident onset. `proposed_covered` includes late warnings; `within_delay_budget` excludes them. Every ledger incident stays in the denominator, including incidents with no recorded page. Coverage is evidence within the supplied history, not recall against all real incidents.

Restoration options re-run the entire batch while keeping one selected alert. They are ordered by remaining regressions, then the number of page events restored. These are useful single-rule alternatives, not a globally optimal removal plan.

Page reduction counts input events with severity `page`; it does not count delivered notifications, deduplicated incidents, phone calls, or engineer hours. No annual extrapolation is used in the lab.

## Dataset format

Use **Download dataset** to obtain a complete example. Import with **Load JSON**. Files are sent only to this app's replay endpoint and kept in browser memory for the session; they do not replace the server's dataset or write to PostgreSQL. Refresh restores the configured dataset. A review export includes the full input dataset, policy, report, assumptions, engine version, and SHA-256 fingerprint.

```json
{
  "schema_version": 1,
  "source": {
    "label": "Team-reviewed export",
    "description": "Paging events joined to the incident ledger by reviewed IDs.",
    "synthetic": false,
    "incident_ledger_complete": false
  },
  "window": {
    "start": "2026-09-01T00:00:00Z",
    "end": "2026-10-01T00:00:00Z"
  },
  "alerts": [
    {"id": "workers/queue", "name": "queue_depth_high", "service": "workers"}
  ],
  "incidents": [
    {
      "id": "INC-1",
      "title": "Worker backlog",
      "started_at": "2026-09-05T12:00:00Z",
      "ended_at": "2026-09-05T13:00:00Z"
    }
  ],
  "events": [
    {
      "id": "event-1",
      "alert_id": "workers/queue",
      "fired_at": "2026-09-05T12:02:00Z",
      "severity": "page",
      "incident_id": "INC-1"
    }
  ]
}
```

- Use unique stable rule IDs; the same alert name in different services must have different IDs.
- Every timestamp must include a timezone. The observation window is `[start, end)`.
- Incident `started_at` and `ended_at` define the inclusive **evidence interval** for its linked events. Include early warning time in that interval where appropriate; these fields are not used as ground truth for detection latency.
- Every linked event must reference an existing incident and fall inside its evidence interval. Invalid joins are rejected rather than silently ignored.
- `incident_id: null` means unknown association. Unlinked events contribute to page volume but never establish noise or lack of incident value.
- `source.event_kind` defaults to `page`; valid severities in that mode are `page`, `ticket`, and `info`, and only pages contribute. The new `recorded_alert` mode requires severity `recorded` and counts recorded alert episodes; it must never be used to assert page delivery.
- `incident_ledger_complete` is an assertion by the exporter, not a conclusion inferred by this app. Leave false unless the ledger was independently checked for the full window.
- Limits: 64 alert rules, 2,000 incidents, 20,000 events, 20 proposed removals, and an 8 MiB request body. The extra-delay budget is between 0 and 60 minutes. The UI uses whole minutes; the API accepts finite fractional values.

For a persistent server dataset, set `REPLAY_DATASET` to an absolute path or a path relative to the project before starting the app. Invalid configured datasets fail startup. Without it, the lab loads `seed/itbench-replay.json`, including when the original toil dashboard uses PostgreSQL. The synthetic teaching fixture is available separately.

## API

- `GET /api/retirement/dataset`: configured input document. Add `?example=synthetic` for the separate teaching fixture.
- Report version 2 uses neutral fields (`baseline_events`, `removed_events`, `event_count`, `baseline_first_event`, etc.) plus an explicit `event_kind`. Version 1 page-specific report names were replaced. Input schema version 1 remains supported; old inputs without `event_kind` use paging mode.
- `POST /api/retirement/replay`: JSON with `retire` (array of rule IDs), `max_delay_minutes` (default 5), and optional `dataset`. Omitting `dataset` uses the configured dataset. Invalid inputs return HTTP 400; oversized requests return 413.
- Existing `/api/summary`, `/api/alerts`, and `/api/recommendations` continue to serve the original toil analysis.

## Data provenance and interpretation

`ingest/replay_demo.py` authors the linked scenarios and deterministic unlinked page history. Run `python -m ingest.replay_demo` to write `seed/retirement-demo.json`. It is not sampled from IBM, PagerDuty, or a production SRE team. No synthetic outcome demonstrates real-world accuracy.

The engine assumes that all unremoved events stay at their observed times. In reality, removing an early page may change responder actions and later events. The output therefore describes a **historical event-removal replay**, not causal detection or outage prevention. Zero regressions does not prove production safety. No incident history exists for rare, unseen failure modes.

Research and competing features are documented in [RESEARCH.md](RESEARCH.md).
