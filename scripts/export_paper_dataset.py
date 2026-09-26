from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "paper-event-v1"
FIELDS = (
    "event_order",
    "event_ticker",
    "market_ticker",
    "tier",
    "cutoff_at",
    "outcome",
    "outcome_binary",
    "status",
    "candidate_candles",
    "eligible_candles",
    "near_release_candles",
    "latest_eligible_end_at",
    "quote_end_at",
    "probability_yes",
    "spread",
    "volume",
    "prior_events",
    "expanding_historical_probability",
    "market_brier_loss",
    "expanding_historical_brier_loss",
    "brier_loss_difference",
)
ALLOWED_STATUSES = frozenset(
    {"eligible", "stale", "no_eligible_candles", "access_error", "invalid_close_time"}
)


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"comparison {key} must be finite")
    return float(value)


def build_event_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("series_ticker") != "KXCPI" or report.get("threshold_suffix") != "-T0.3":
        raise ValueError("paper dataset requires the fixed KXCPI T0.3 definition")
    events = report.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError("events must be an object list")
    if report.get("settled_fixed_threshold_events") != len(events):
        raise ValueError("settled event count does not match events")
    comparison = _require_dict(report.get("event_probability_comparison"), "comparison")
    comparisons = comparison.get("comparisons")
    if not isinstance(comparisons, list) or not all(isinstance(row, dict) for row in comparisons):
        raise ValueError("comparisons must be an object list")
    if comparison.get("comparable_events") != len(comparisons):
        raise ValueError("comparable event count does not match comparisons")
    event_tickers = {event.get("market_ticker") for event in events}
    if len(event_tickers) != len(events) or not all(
        isinstance(ticker, str) for ticker in event_tickers
    ):
        raise ValueError("market tickers must be unique strings")
    comparison_by_ticker: dict[str, dict[str, Any]] = {}
    for row in comparisons:
        ticker = row.get("market_ticker")
        if ticker not in event_tickers:
            raise ValueError("comparison references an unknown market")
        if not isinstance(ticker, str) or ticker in comparison_by_ticker:
            raise ValueError("comparison market tickers must be unique strings")
        comparison_by_ticker[ticker] = row

    provided_counts = _require_dict(report.get("status_counts"), "status_counts")
    for status, count in provided_counts.items():
        if not isinstance(status, str) or count != sum(
            event.get("status") == status for event in events
        ):
            raise ValueError("status counts do not match events")

    rows: list[dict[str, Any]] = []
    prior_outcomes: list[bool] = []
    for order, event in enumerate(events, start=1):
        ticker = event["market_ticker"]
        status = event.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError("unknown event status")
        outcome = event.get("outcome")
        if outcome not in ("yes", "no"):
            raise ValueError("paper events require a settled binary outcome")
        scored = comparison_by_ticker.get(ticker, {})
        target = int(outcome == "yes")
        market_loss: float | str = ""
        baseline_loss: float | str = ""
        if scored:
            probability = _number(scored, "probability_yes")
            historical_probability = _number(scored, "expanding_historical_probability")
            market_loss = _number(scored, "market_loss")
            baseline_loss = _number(scored, "expanding_historical_loss")
            expected_historical_probability = sum(prior_outcomes) / len(prior_outcomes)
            if scored.get("prior_events") != len(prior_outcomes):
                raise ValueError("comparison prior count does not match event history")
            if scored.get("outcome_binary") != target:
                raise ValueError("comparison outcome does not match event")
            if not math.isclose(probability, float(event.get("probability_yes", -1))):
                raise ValueError("comparison probability does not match event")
            if not math.isclose(historical_probability, expected_historical_probability):
                raise ValueError("comparison historical probability does not match prior events")
            if not math.isclose(market_loss, (probability - target) ** 2):
                raise ValueError("comparison market loss is inconsistent")
            if not math.isclose(baseline_loss, (historical_probability - target) ** 2):
                raise ValueError("comparison historical loss is inconsistent")
        rows.append(
            {
                "event_order": order,
                "event_ticker": event.get("event_ticker", ""),
                "market_ticker": ticker,
                "tier": event.get("tier", ""),
                "cutoff_at": event.get("cutoff_at", ""),
                "outcome": outcome,
                "outcome_binary": target,
                "status": status,
                "candidate_candles": event.get("candidate_candles", ""),
                "eligible_candles": event.get("eligible_candles", ""),
                "near_release_candles": event.get("near_release_candles", ""),
                "latest_eligible_end_at": event.get("latest_eligible_end_at", ""),
                "quote_end_at": event.get("quote_end_at", ""),
                "probability_yes": event.get("probability_yes", ""),
                "spread": event.get("spread", ""),
                "volume": event.get("volume", ""),
                "prior_events": scored.get("prior_events", ""),
                "expanding_historical_probability": scored.get(
                    "expanding_historical_probability", ""
                ),
                "market_brier_loss": market_loss,
                "expanding_historical_brier_loss": baseline_loss,
                "brier_loss_difference": (
                    float(market_loss) - float(baseline_loss)
                    if market_loss != "" and baseline_loss != ""
                    else ""
                ),
            }
        )
        prior_outcomes.append(bool(target))
    return rows


def _write_immutable(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"existing paper artifact differs: {path.name}")
        return
    path.write_text(content, encoding="utf-8")


def export_paper_dataset(report_path: Path, output_dir: Path) -> Path:
    source = report_path.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    payload = json.loads(source)
    report = _require_dict(payload, "report")
    rows = build_event_rows(report)

    csv_buffer = io.StringIO(newline="")
    fieldnames: list[str] = list(FIELDS)
    writer: csv.DictWriter[str] = csv.DictWriter(
        csv_buffer, fieldnames=fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    csv_content = csv_buffer.getvalue()

    comparison = _require_dict(report["event_probability_comparison"], "comparison")
    aggregate_comparison = {key: value for key, value in comparison.items() if key != "comparisons"}
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_report_sha256": source_hash,
        "source_checked_at": report.get("checked_at"),
        "series_ticker": report.get("series_ticker"),
        "threshold_suffix": report.get("threshold_suffix"),
        "event_count": len(rows),
        "status_counts": report.get("status_counts"),
        "event_probability_comparison": aggregate_comparison,
        "event_file": {
            "name": "event_coverage.csv",
            "sha256": hashlib.sha256(csv_content.encode()).hexdigest(),
            "columns": list(FIELDS),
        },
        "publication_status": "local_research_only_pending_source_license_review",
    }
    metadata_content = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    destination = output_dir / SCHEMA_VERSION / source_hash
    destination.mkdir(parents=True, exist_ok=True)
    _write_immutable(destination / "event_coverage.csv", csv_content)
    _write_immutable(destination / "metadata.json", metadata_content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi CPI 감사 보고서를 논문용 사건 자료로 변환")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/paper-dataset"))
    args = parser.parse_args()
    destination = export_paper_dataset(args.input, args.output)
    print(json.dumps({"paper_dataset": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
