PYTHON ?= python

.PHONY: setup quality test test-fast collect train evaluate report dev build

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
