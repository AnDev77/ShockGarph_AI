PYTHON ?= python

.PHONY: setup quality test test-fast collect train evaluate report dev build research-demo research-probe research-audit-cpi research-paper-data research-bls-cpi research-alpaca-etf research-asset-panel

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

research-paper-data:
	@test -n "$(PAPER_REPORT)" || (echo "PAPER_REPORT에 report.json 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/export_paper_dataset.py --input "$(PAPER_REPORT)"

research-bls-cpi:
	@test -n "$(AUDIT_REPORT)" || (echo "AUDIT_REPORT에 Kalshi 감사 report.json 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/collect_bls_cpi_vintages.py --input-audit "$(AUDIT_REPORT)"

research-alpaca-etf:
	@test -n "$(RELEASE_CSV)" || (echo "RELEASE_CSV에 release_vintage.csv 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/collect_alpaca_etf_bars.py --releases "$(RELEASE_CSV)" --feed "$${ALPACA_FEED:-iex}"

research-asset-panel:
	@test -n "$(RELEASE_CSV)" || (echo "RELEASE_CSV에 release_vintage.csv 경로를 지정하세요" && exit 2)
	@test -n "$(PROBABILITY_CSV)" || (echo "PROBABILITY_CSV에 event_coverage.csv 경로를 지정하세요" && exit 2)
	@test -n "$(ASSET_BAR_CSV)" || (echo "ASSET_BAR_CSV에 이용권이 확인된 ETF 분봉 CSV 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/build_cpi_asset_panel.py --releases "$(RELEASE_CSV)" --probabilities "$(PROBABILITY_CSV)" --asset-bars "$(ASSET_BAR_CSV)"

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
