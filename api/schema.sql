CREATE TABLE IF NOT EXISTS alert_event (
  id SERIAL PRIMARY KEY,
  alert_name TEXT NOT NULL,
  service TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('page', 'ticket', 'info')),
  fired_at TIMESTAMPTZ NOT NULL,
  acknowledged_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  auto_resolved BOOLEAN NOT NULL,
  incident_id TEXT,
  responder_count INTEGER NOT NULL DEFAULT 0 CHECK (responder_count >= 0),
  manual_action BOOLEAN NOT NULL,
  runbook_action TEXT
);
CREATE INDEX IF NOT EXISTS alert_event_name_fired_idx ON alert_event (alert_name, fired_at);
CREATE INDEX IF NOT EXISTS alert_event_incident_idx ON alert_event (incident_id);

-- Explicit coverage is necessary to annualize correctly, including quiet months.
CREATE TABLE IF NOT EXISTS dataset_metadata (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ NOT NULL,
  months INTEGER NOT NULL CHECK (months > 0),
  timezone TEXT NOT NULL,
  source TEXT NOT NULL,
  seed INTEGER,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Persist CLI ingestion measurements so the running app can expose them.
CREATE TABLE IF NOT EXISTS ingestion_run (
  id SERIAL PRIMARY KEY,
  finished_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  duration_seconds DOUBLE PRECISION NOT NULL CHECK (duration_seconds >= 0),
  event_count INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'error'))
);
