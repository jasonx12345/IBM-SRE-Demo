# Running Toil Budget

## Service topology

Compose runs PostgreSQL 16, the Python 3.11 Flask application under Gunicorn, Prometheus and Grafana. PostgreSQL readiness gates app startup; app readiness gates Prometheus startup. Bindings are localhost-only. There is no authentication in the application, and Grafana offers anonymous read-only viewing for this local demo.

Use `docker compose ps` to inspect status and `docker compose logs --tail=100 app postgres` for failures. `docker compose up -d --build` starts the complete stack in the background; `make seed` populates it. Named volumes preserve the dataset and observability history across ordinary stops. Local example credentials are for this isolated development setup.

`GET /healthz` reports process liveness without checking PostgreSQL. `GET /readyz` performs a database/schema check and returns 503 if PostgreSQL is unavailable; this separates dependency failure from a dead process. Schema creation is idempotent and serialized with a PostgreSQL advisory lock to accommodate concurrent replica starts. Replacement ingestion uses one transaction and the reader uses repeatable-read isolation, preventing a partly replaced dataset.

## Metrics

| Metric | Meaning |
| --- | --- |
| `toil_budget_http_requests_total{method,route,status,scope}` | Completed requests, including failures and unknown API paths |
| `toil_budget_http_request_duration_seconds{method,route,scope}` | Server-side latency histogram with the configured 300 ms SLO bucket |
| `toil_budget_http_requests_in_flight` | Concurrent requests; the service's saturation proxy |
| `toil_budget_database_up` | Whether DB-backed metrics could be collected during this scrape |
| `toil_budget_ingestion_duration_seconds` | Persisted cumulative histogram of parsing, validation and commit duration |
| `toil_budget_ingested_events_total` | All successful ingestions, including deliberate replacement runs |
| `toil_budget_ingestion_errors_total` | Failed ingestion runs that could be recorded in PostgreSQL |
| `toil_budget_last_ingestion_timestamp_seconds` | Timestamp of the last persisted successful or failed ingestion |
| `toil_budget_estimated_annual_toil_hours{alert_name,classification}` | Dataset analysis estimate, omitting unknown values |
| `toil_budget_alert_occurrences{alert_name,classification}` | Event volume in the current dataset |
| `toil_budget_runbook_repeat_rate{alert_name}` | Automation-confidence proxy |
| `toil_budget_automation_recoverable_hours` | Estimated annual gross savings from the top three automation candidates |

Route labels use Flask templates (`/api/alerts/<name>`), never raw user-provided paths. Unknown routes share the `unmatched` label. `/metrics` excludes its own requests from latency/count/in-flight instrumentation. Health, docs and static routes are measured but excluded from API SLOs with `scope="api"`.

Each pod runs **one Gunicorn worker, four threads**. The Prometheus client uses process-local request metrics; increasing workers without multiprocess instrumentation would yield incomplete counters. Scale replicas instead. Scrape **each pod**, not a load-balanced Kubernetes Service, or the observed counter can jump between processes. Sum rates across replicas for request metrics. Dataset and durable ingestion metrics are the same database values exposed by each replica: aggregate those using **max**, never sum. The Grafana dashboard follows these rules.

## SLOs and alert response

`config/slo.yaml` defines a 30-day rolling objective of 99% of API requests within 300 ms and fewer than 1% HTTP 5xx. Prometheus histogram boundaries are inclusive (≤ 300 ms). Client errors such as unknown alert names count in API traffic but do not consume the server-error budget. No-traffic periods do not create artificial burn. Requests failing before reaching this service need external black-box monitoring, which is outside this project.

`prometheus/rules.yaml` contains recording rules for slow/error ratios and multi-window alerts:

- **Fast burn**: both 1h and 5m bad-event ratios exceed 14.4 times the 1% budget, for 2 minutes.
- **Slow burn**: both 6h and 30m ratios exceed 6 times the 1% budget, for 15 minutes.
- **Unavailable**: a scrape target or its database availability signal is down for 2 minutes.

These alerts detect accelerated budget consumption rather than waiting until the entire 30-day objective fails. Low traffic can make ratios noisy; the windows/rates are tunable. The rules evaluate and fire in Prometheus; external notifications need an Alertmanager deployment and routing configuration, which this project does not include.

For availability burn, inspect `/readyz`, PostgreSQL logs, pool timeouts and connection limits. For latency burn, compare traffic, p99 latency and in-flight requests; inspect DB response time, cache misses, dataset size and CPU limits. For ingestion problems, inspect the CLI exit status first, then its persisted duration/error metrics. A completely unavailable DB cannot persist its own ingestion error, so the CLI failure is authoritative.

After editing SLOs, run `python -m prometheus.generate_rules` and `python -m grafana.generate_dashboard`, rebuild/restart the app so its histogram buckets reload, and restart Prometheus. `make check-rules` runs promtool syntax validation; `docker compose run --rm --no-deps --entrypoint promtool -v ./prometheus/tests.yaml:/tmp/tests.yaml:ro prometheus test rules /tmp/tests.yaml` exercises the checked-in burn-rule fixtures. Tests also reject drift between generated rules and their canonical YAML. After editing model/classification values, restart the app. Cache duration is 15 seconds by default; separate replicas can briefly serve snapshots computed on opposite sides of a seed transaction.

## Kubernetes (kind or minikube)

Build the Linux image and load it into your local cluster:

```sh
docker build -t toil-budget:local .
kind create cluster --name toil-budget
kind load docker-image toil-budget:local --name toil-budget
# Or: minikube start && minikube image load toil-budget:local
kubectl apply -k k8s/
kubectl -n toil-budget rollout status statefulset/postgres --timeout=180s
kubectl -n toil-budget rollout status deployment/toil-budget --timeout=180s
kubectl create -f k8s/seed-job.yaml
kubectl -n toil-budget get jobs
kubectl -n toil-budget port-forward service/toil-budget 8000:8000
```

The manifests provide two application replicas, Service, ConfigMap containing thresholds/model/SLOs, CPU/memory requests and limits, startup/liveness/readiness probes, an unprivileged app container with read-only filesystem and `/tmp` volume, and a local PostgreSQL StatefulSet with a persistent volume. An available default storage class is required (kind/minikube normally provide one). The application may restart while PostgreSQL initializes; its startup probe tolerates a slow initial boot. PostgreSQL itself is one replica and is **not highly available**.

Seeding is a separately created Job, so deploying the app never automatically replaces data. `kubectl create -f k8s/seed-job.yaml` creates a new named Job each time; completed Jobs expire after ten minutes. To update config, run `python -m k8s.generate_config`, apply again, then `kubectl -n toil-budget rollout restart deployment/toil-budget`. When rebuilding the image with the same `:local` tag, load it again and restart the Deployment.

Prometheus/Grafana are included in Compose. To monitor Kubernetes with an existing Prometheus, use pod discovery filtered to namespace `toil-budget`, label `app=toil-budget`, and port 8000; set the scrape job label to `toil-budget`. The Deployment includes scrape annotations, but annotations only work if your Prometheus scrape configuration consumes them. Import `prometheus/rules.yaml` into that server and `grafana/dashboard.json` into Grafana with a Prometheus datasource UID of `prometheus`. Provisioning a separate cluster monitoring stack is outside these local application manifests.

## Validation and recovery

`make test` runs unit tests and real PostgreSQL tests against disposable databases on the Compose PostgreSQL server; the role must be able to create databases. Without Docker, `make test-local` runs unit/API/config tests, and integration tests skip unless `TEST_DATABASE_URL` is explicitly supplied. The integration tests create only unique `toil_test_*` databases and drop those databases on completion.

For a failed seed, the previous committed dataset remains intact; inspect the error and repeat the same deterministic command. For no recommendations, inspect `/api/summary`, the configured thresholds and missing-duration counts before changing cutoffs. For a Docker connection error, start Docker Desktop's Linux engine and rerun `docker compose up`.

Implementation references: [Flask application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Prometheus Python custom collectors](https://prometheus.github.io/client_python/collector/custom/), and [Compose startup dependencies](https://docs.docker.com/compose/how-tos/startup-order/).
