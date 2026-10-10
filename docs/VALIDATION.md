# Validation record

## October 9, 2026 — IBM Research dataset integration

- **94 tests passed; 3 PostgreSQL integration tests skipped** without `TEST_DATABASE_URL`. Tests ran with a fresh workspace-local temporary directory because the pre-existing system pytest temp/cache directories had an access error.
- Verified all downloaded source checksums and reproduced the checked-in normalized document offline. A changed source file fails verification.
- Checked 82 source snapshots: 772 rows = 287 excluded + 448 repeated observations + 37 episodes. Thirteen alert scopes, eight ground-truth-linked episodes and 29 unlinked episodes.
- Tests cover strict ground-truth matching, warning/critical firing-only filtering, preservation of original timestamps, separation of recorded alerts from paging inputs, actual combined removal and restoration, and unknown links.
- Default replay: six episodes removed, one experiment loses all linked warnings and the other is approximately 19 minutes later. Keeping the proxy error-rate scope repairs both outcomes with one episode removed. The verdict still declares incomplete evidence.
- Headless Chromium verified the IBM default, source inspection, dataset switching, restoration, unlinked-alert example, full review export, synthetic teaching cases, delay editing, import validation, HTML escaping and the original toil view.
- Desktop 1440px and mobile 390px screenshots inspected. No horizontal overflow, including expanded source records, and no unexpected browser errors.
- The earlier synthetic-only validation below is retained as history; it no longer describes the default input. `retirement-lab.png` now shows the IBM-backed replay.

The evidence comes from controlled benchmark experiments, not production deployment testing or measured human toil. See [IBM_DATA.md](IBM_DATA.md).

## October 9, 2026 — Alert Retirement Lab

- Python 3.11: **85 tests passed; 3 PostgreSQL integration tests skipped** because `TEST_DATABASE_URL` was not supplied for the database-free demo checks. Earlier PostgreSQL validation is recorded separately below.
- Replay tests cover individual versus combined removals, sole warnings, twelve-minute delay and inclusive budget boundaries, baseline coverage gaps, unknown incident associations, incomplete ledgers, ticket/page separation, deterministic calculations, restoration alternatives, invalid inputs and API isolation.
- Ruff lint, formatting for changed Python files, and JavaScript syntax checks passed.
- Live local demo: `.venv\Scripts\python.exe -m api.demo --port 8001`. No Docker, Kubernetes or PostgreSQL required. The demo exposes a demo-mode metric rather than claiming a database is available.
- An isolated headless Chromium browser verified all four scenarios, keeping an alternative alert, editing the delay budget, clearing a proposal, exporting the full review, importing a dataset, rendering imported text without HTML execution, and preserving the existing dataset after an invalid import.
- Desktop 1440px and mobile 390px layouts were visually inspected. Mobile checks found no horizontal overflow. The original `/toil` dashboard still loads its 1,625-event synthetic dataset.
- No unexpected browser errors were captured; an HTTP 400 for the deliberately invalid import was expected.
- [retirement-lab.png](retirement-lab.png) captures the initial combined-removal scenario. The browser check script and exported verification artifact are in the ignored `.local/` directory.

Default lab fixture: 668 page events, eight alert rules, seven ledger incidents, six with baseline pages. Removing both worker rules removes 420 events and loses all pages for two incidents. Keeping `worker_lag_high` changes the proposal to 240 events removed with all six originally covered incidents inside the delay budget. The separate checkout scenario adds twelve minutes to its first page; the disk scenario has no incident-page evidence.

These are deliberately authored test cases, not a validation against production incidents or evidence of commercial uniqueness. Research scope and limits are recorded in [RESEARCH.md](RESEARCH.md).

The built-in browser automation initially failed because its Windows sandbox helper could not initialize. The isolated browser test used the available bundled Playwright runtime. The application itself was verified through that browser and live HTTP requests.

## October 5, 2026 — Original toil-analysis stack

### Verified

- Python 3.11: **49 tests passed**, including real PostgreSQL integration tests for schema initialization, seed replacement, rollback, API responses, and persisted ingestion metrics.
- Ruff lint and formatting checks passed; vanilla JavaScript syntax check passed.
- Prometheus 3.5.0 `promtool check rules`: **13 rules validated**.
- `promtool test rules`: sustained latency burn, sustained error burn, healthy traffic with no error series, and zero traffic fixtures all passed.
- A live Prometheus server scraped the PostgreSQL-backed application successfully; every recording/alert rule reported healthy and all **16 Grafana panel queries** executed without errors.
- Docker Compose configuration rendered successfully. Kubernetes Kustomize rendered successfully, including the two-replica Deployment, ConfigMap and probe/resource definitions.
- Browser checks covered recommendation values, sorting, search, classification filtering, monthly trend/runbook detail, and a 390 px layout without horizontal page/dialog overflow. No browser errors were reported.
- `docs/recommendations.jpg` captures the application using the real PostgreSQL repository.

The default seed produced 1,625 events, 392.2 estimated annual toil hours and 121.6 estimated annual gross automation savings. Redis memory pressure was the top automation candidate (95% runbook repeat), and worker queue depth was the top deletion candidate. Approximately 35% of pages fired after hours.

A 100-request loopback smoke check at concurrency eight returned all HTTP 200 responses, p99 41.03 ms and maximum 41.11 ms. This used Flask's local development server on this machine, not Gunicorn in a resource-limited container; it is **not** evidence of achieving a 30-day production SLO.

### Environment limitation at that time

Docker Desktop was installed but its Linux engine could not start. Its backend reported an inaccessible stale `sailor-ingest.sock` file during startup. Docker data and settings were left intact. Consequently, the complete Compose stack, Grafana's rendered dashboard/provisioning, and a running Kubernetes deployment could not be validated here. Their configuration and relevant application behavior were checked separately.

Official portable PostgreSQL and Prometheus binaries were used in the ignored `.local/` directory for the database and monitoring checks. These are validation tools, not a substitute production stack. During this chat, a PostgreSQL-backed development preview is available at `http://127.0.0.1:8001`; a temporary Prometheus is at `http://127.0.0.1:9091`. The temporary database listens only on `127.0.0.1:55432` and contains synthetic data. These processes may end with the local session; the reproducible entry point remains `docker compose up` followed by `make seed` once Docker is healthy.
