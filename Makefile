PYTHON ?= python

.PHONY: setup quality test test-fast collect train evaluate risk-evaluate report dev build research-demo risk-demo portfolio-demo research-probe research-audit-cpi research-paper-data

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

risk-demo:
	$(PYTHON) scripts/run_daily_risk_demo.py

portfolio-demo:
	$(PYTHON) scripts/run_portfolio_risk_demo.py

research-probe:
	$(PYTHON) scripts/probe_cpi_coverage.py --max-pages 10

research-audit-cpi:
	$(PYTHON) scripts/audit_kalshi_cpi.py --request-interval 0.3

research-paper-data:
	@test -n "$(PAPER_REPORT)" || (echo "PAPER_REPORT에 report.json 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/export_paper_dataset.py --input "$(PAPER_REPORT)"

train:
	@echo "Not implemented before the Day 4 data gate" && exit 2

evaluate:
	@echo "Not implemented before the Day 5 model baseline" && exit 2

risk-evaluate:
	@test -n "$(SNAPSHOT_MANIFEST)" || (echo "SNAPSHOT_MANIFEST에 비공개 manifest.json 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/evaluate_snapshot_holdout.py --manifest "$(SNAPSHOT_MANIFEST)"

report:
	@echo "Not implemented before validated model artifacts exist" && exit 2

dev:
	@echo "Not implemented before the API and web milestones" && exit 2

build:
	@echo "Not implemented before the deployment milestone" && exit 2
