PYTHON ?= python

.PHONY: setup quality test test-fast collect train evaluate report dev build research-demo research-probe research-audit-cpi

setup:
	$(PYTHON) -m pip install -e ".[dev]"

quality:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest

test-fast:
	$(PYTHON) -m pytest tests/unit tests/contracts

collect:
	$(PYTHON) scripts/probe_kalshi.py

research-demo:
	$(PYTHON) scripts/run_event_research.py --input data/fixtures/analytics/synthetic_cpi.json --min-train 4

research-probe:
	$(PYTHON) scripts/probe_cpi_coverage.py --max-pages 10

research-audit-cpi:
	$(PYTHON) scripts/audit_kalshi_cpi.py --request-interval 0.3

train:
	@echo "Not implemented before the Day 4 data gate" && exit 2

evaluate:
	@echo "Not implemented before the Day 5 model baseline" && exit 2

report:
	@echo "Not implemented before validated model artifacts exist" && exit 2

dev:
	@echo "Not implemented before the API and web milestones" && exit 2

build:
	@echo "Not implemented before the deployment milestone" && exit 2
