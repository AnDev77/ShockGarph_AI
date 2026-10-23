PYTHON ?= python

.PHONY: setup quality test test-fast collect collect-treasury collect-alpaca analyze-alpaca treasury-coverage train evaluate risk-evaluate risk-compare risk-explore report dev build research-demo risk-demo portfolio-demo research-probe research-audit-cpi research-paper-data

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

collect-treasury:
	$(PYTHON) scripts/collect_treasury_rates.py $(if $(TREASURY_MONTH),--month $(TREASURY_MONTH),)

collect-alpaca:
	@test -n "$(PRICE_END)" || (echo "PRICE_END에 미국 마지막 거래일 YYYY-MM-DD를 지정하세요" && exit 2)
	$(PYTHON) scripts/collect_alpaca_prices.py --end "$(PRICE_END)" $(if $(PRICE_START),--start "$(PRICE_START)",)

analyze-alpaca:
	@test -n "$(ALPACA_MANIFEST)" || (echo "ALPACA_MANIFEST에 비공개 captures/*.json을 지정하세요" && exit 2)
	@test -n "$(HOLDOUT_START)" || (echo "HOLDOUT_START에 YYYY-MM-DD를 지정하세요" && exit 2)
	$(PYTHON) scripts/analyze_alpaca_history.py --manifest "$(ALPACA_MANIFEST)" --holdout-start "$(HOLDOUT_START)"

treasury-coverage:
	@test -n "$(PRICE_HISTORY)" || (echo "PRICE_HISTORY에 비공개 TLT 가격 CSV 경로를 지정하세요" && exit 2)
	$(PYTHON) scripts/report_treasury_coverage.py --price-history "$(PRICE_HISTORY)" --treasury-archive "$(or $(TREASURY_RAW_ROOT),data/raw)"

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

risk-compare:
	@test -n "$(SNAPSHOT_MANIFEST)" || (echo "SNAPSHOT_MANIFEST에 비공개 manifest.json 경로를 지정하세요" && exit 2)
	@test -n "$(INDICATOR_HISTORY)$(TREASURY_RAW_ROOT)" || (echo "INDICATOR_HISTORY 또는 TREASURY_RAW_ROOT를 지정하세요" && exit 2)
	@test -z "$(INDICATOR_HISTORY)" -o -z "$(TREASURY_RAW_ROOT)" || (echo "지표 CSV와 Treasury 원본은 동시에 지정할 수 없습니다" && exit 2)
	$(PYTHON) scripts/evaluate_traditional_holdout.py --manifest "$(SNAPSHOT_MANIFEST)" $(if $(TREASURY_RAW_ROOT),--treasury-archive "$(TREASURY_RAW_ROOT)",--indicators "$(INDICATOR_HISTORY)")

risk-explore:
	@test -n "$(PRICE_HISTORY)" || (echo "PRICE_HISTORY에 비공개 수정종가 CSV 경로를 지정하세요" && exit 2)
	@test -n "$(PRICE_SOURCE)" || (echo "PRICE_SOURCE에 공급원 이름을 지정하세요" && exit 2)
	@test -n "$(HOLDOUT_START)" || (echo "HOLDOUT_START에 YYYY-MM-DD를 지정하세요" && exit 2)
	$(PYTHON) scripts/evaluate_exploratory_history.py --input "$(PRICE_HISTORY)" --source "$(PRICE_SOURCE)" --holdout-start "$(HOLDOUT_START)" $(if $(COMPARE_MODEL),--compare-model,)

report:
	@echo "Not implemented before validated model artifacts exist" && exit 2

dev:
	@echo "Not implemented before the API and web milestones" && exit 2

build:
	@echo "Not implemented before the deployment milestone" && exit 2
