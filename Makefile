PYTHON ?= python

.PHONY: setup quality test test-fast collect train evaluate report dev build api-dev web-dev web-build research-demo research-probe research-audit-cpi research-paper-data research-bls-cpi research-alpaca-etf research-asset-panel research-price-baseline research-cpi-asset-pipeline

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
	$(PYTHON) scripts/collect_alpaca_etf_bars.py --releases "$(RELEASE_CSV)" --feed "$${ALPACA_FEED:-sip}"

research-asset-panel:
	@test -n "$(RELEASE_CSV)" || (echo "RELEASE_CSV에 release_vintage.csv 경로를 지정하세요" && exit 2)
	@test -n "$(PROBABILITY_CSV)" || (echo "PROBABILITY_CSV에 event_coverage.csv 경로를 지정하세요" && exit 2)
	@test -n "$(ASSET_BAR_CSV)" || (echo "ASSET_BAR_CSV에 이용권이 확인된 ETF 분봉 CSV 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/build_cpi_asset_panel.py --releases "$(RELEASE_CSV)" --probabilities "$(PROBABILITY_CSV)" --asset-bars "$(ASSET_BAR_CSV)"

research-price-baseline:
	@test -n "$(PANEL_DIR)" || (echo "PANEL_DIR에 cpi-asset-panel 실행 디렉터리를 지정하세요" && exit 2)
	$(PYTHON) scripts/evaluate_cpi_price_baseline.py --panel-dir "$(PANEL_DIR)"

research-cpi-asset-pipeline:
	@test -n "$(RELEASE_CSV)" || (echo "RELEASE_CSV에 release_vintage.csv 경로를 지정하세요" && exit 2)
	@test -n "$(PROBABILITY_CSV)" || (echo "PROBABILITY_CSV에 event_coverage.csv 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/run_cpi_asset_pipeline.py --releases "$(RELEASE_CSV)" --probabilities "$(PROBABILITY_CSV)"

api-dev:
	@test -n "$${SHOCKGRAPH_RESEARCH_METADATA}" || (echo "SHOCKGRAPH_RESEARCH_METADATA를 지정하세요" && exit 2)
	$(PYTHON) -m uvicorn shockgraph_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000

web-dev:
	npm --prefix apps/web run dev

web-build:
	npm --prefix apps/web run build

train:
	@echo "Not implemented before the Day 4 data gate" && exit 2

evaluate:
	@echo "Not implemented before the Day 5 model baseline" && exit 2

report:
	@echo "Not implemented before validated model artifacts exist" && exit 2

dev:
	@echo "API와 웹을 별도 터미널에서 make api-dev, make web-dev로 실행하세요"

build: web-build
