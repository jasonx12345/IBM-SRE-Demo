SEED ?= 42
MONTHS ?= 6
PYTHON ?= python

.PHONY: run seed test test-local rules check-rules
run:
	docker compose up --build

seed:
	docker compose exec -T app python -m seed.generate --seed $(SEED) --months $(MONTHS)

test:
	docker compose run --rm --no-deps --user root app sh -c "pip install -q -r requirements-dev.txt && python -m tests.run"

test-local:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ruff check .

rules:
	$(PYTHON) -m prometheus.generate_rules

check-rules:
	docker compose run --rm --no-deps --entrypoint promtool prometheus check rules /etc/prometheus/rules.yaml
