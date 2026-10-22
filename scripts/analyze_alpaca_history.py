"""Research-only TLT/SPY price-model comparison from one captured Alpaca history."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/domain"), str(ROOT / "packages/data_pipeline"),
                str(ROOT / "packages/risk_engine")]

from shockgraph_data_pipeline.market_calendar import nasdaq_sessions  # noqa: E402
from shockgraph_risk.exploratory_garch import evaluate_exploratory_garch  # noqa: E402
from shockgraph_risk.exploratory_history import HistoryPrice  # noqa: E402
from shockgraph_risk.exploratory_model import compare_price_only_model  # noqa: E402

_COLUMNS = ["session_date", "observed_at", "available_at", "close",
            "adjusted_close", "volume"]


def _read_symbol(row: dict[str, Any], base: Path) -> tuple[list[HistoryPrice], int]:
    symbol = row.get("symbol")
    if symbol not in ("TLT", "SPY") or row.get("feed") != "sip":
        raise ValueError("manifest requires a supported SIP symbol")
    path = Path(row["snapshot_path"]).resolve()
    if not path.is_relative_to(base / symbol):
        raise ValueError("snapshot must be under the private symbol directory")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row.get("normalized_csv_sha256"):
        raise ValueError("snapshot hash does not match the capture manifest")
    captured_at = datetime.fromisoformat(row["capture"])
    if captured_at.tzinfo is None or captured_at.utcoffset() != UTC.utcoffset(None):
        raise ValueError("capture timestamp must be UTC")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames != _COLUMNS:
        raise ValueError("Alpaca snapshot columns are invalid")
    prices: list[HistoryPrice] = []
    raw: list[float] = []
    for item in reader:
        if None in item or any(value is None or not value for value in item.values()):
            raise ValueError("Alpaca snapshot has an incomplete row")
        day = date.fromisoformat(item["session_date"])
        available_at = datetime.fromisoformat(item["available_at"])
        if available_at != captured_at:
            raise ValueError("price availability differs from the actual capture")
        adjusted_close, raw_close = float(item["adjusted_close"]), float(item["close"])
        if any(not math.isfinite(value) or value <= 0 for value in (adjusted_close, raw_close)):
            raise ValueError("Alpaca price must be positive and finite")
        prices.append(HistoryPrice(day, adjusted_close))
        raw.append(raw_close)
    if not prices or row.get("session_count") != len(prices):
        raise ValueError("snapshot count does not match the capture manifest")
    sessions = nasdaq_sessions(prices[0].session_date, prices[-1].session_date)
    if [price.session_date for price in prices] != [session.session_date for session in sessions]:
        raise ValueError("snapshot does not match the reviewed session calendar")
    # Count materially different daily returns; do not interpret differences as
    # identified dividend or split events without a corporate-actions feed.
    discrepancy_count = sum(
        abs(math.log(prices[i].adjusted_close / prices[i - 1].adjusted_close)
            - math.log(raw[i] / raw[i - 1])) >= 0.001
        for i in range(1, len(prices))
    )
    return prices, discrepancy_count


def _percent_points(value: float | None) -> float | None:
    return round(value * 100, 4) if value is not None else None


def _ci(value: tuple[float, float] | None) -> list[float] | None:
    return [round(point * 100, 4) for point in value] if value is not None else None


def run_analysis(manifest_path: Path, *, holdout_start: date) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("status") != "archived_research_only":
        raise ValueError("expected a research-only Alpaca capture manifest")
    entries = manifest.get("prices")
    if not isinstance(entries, list) or len(entries) != 2 or {
        item.get("symbol") for item in entries if isinstance(item, dict)
    } != {"TLT", "SPY"}:
        raise ValueError("manifest must contain exactly TLT and SPY")
    output = []
    common_dates: list[date] | None = None
    for entry in entries:
        prices, discrepancy_count = _read_symbol(entry, manifest_path.resolve().parent.parent)
        dates = [row.session_date for row in prices]
        if common_dates is not None and dates != common_dates:
            raise ValueError("TLT and SPY sessions do not align")
        common_dates = dates
        ridge = compare_price_only_model(prices, holdout_start=holdout_start)
        garch = evaluate_exploratory_garch(prices, holdout_start=holdout_start)
        horizons = []
        for baseline, model in zip(garch, ridge, strict=True):
            if baseline.horizon != model.horizon or (
                baseline.sample_size, baseline.first_prediction_date,
                baseline.last_prediction_date
            ) != (
                model.holdout_count, model.first_holdout_date,
                model.last_holdout_date
            ):
                raise ValueError("models did not share the same forecast dates")
            if (baseline.status == model.status == "exploratory_current_history_only"
                    and not math.isclose(baseline.ewma_mae or 0, model.ewma_mae or 0,
                                         abs_tol=1e-12)):
                raise ValueError("baseline MAE differs across evaluators")
            horizons.append({
                "horizon_sessions": model.horizon,
                "holdout_prediction_dates": model.holdout_count,
                "nonoverlapping_windows": model.nonoverlapping_window_count,
                "last_training_label_date": (
                    model.last_training_label_date.isoformat()
                    if model.last_training_label_date else None
                ),
                "first_prediction_date": (
                    model.first_holdout_date.isoformat() if model.first_holdout_date else None
                ),
                "last_prediction_date": (
                    model.last_holdout_date.isoformat() if model.last_holdout_date else None
                ),
                "baseline_status": baseline.status,
                "ridge_status": model.status,
                "mae_daily_volatility_percentage_points": {
                    "trailing": _percent_points(model.trailing_mae),
                    "ewma": _percent_points(model.ewma_mae),
                    "garch": _percent_points(baseline.garch_mae),
                    "ridge": _percent_points(model.ridge_mae),
                },
                "paired_block_ci_difference_vs_ewma_percentage_points": {
                    "garch": _ci(baseline.garch_minus_ewma_mae_ci),
                    "ridge": _ci(model.ridge_minus_ewma_mae_ci),
                },
            })
        output.append({
            "symbol": entry["symbol"], "session_count": len(prices),
            "first_session": dates[0].isoformat(), "last_session": dates[-1].isoformat(),
            "capture": entry["capture"],
            "adjusted_vs_raw_return_difference_over_0_1_percent_points": discrepancy_count,
            "horizons": horizons,
        })
    return {
        "status": "exploratory_current_history_only",
        "source": "alpaca-sip",
        "capture_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "holdout_start": holdout_start.isoformat(),
        "historical_price_vintages_verified": False,
        "capture_history_persisted": False,
        "public_product_performance_allowed": False,
        "assets": output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpaca TLT·SPY 현재 이력의 비공개 탐색 평가")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--holdout-start", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_analysis(args.manifest, holdout_start=args.holdout_start)
    except (OSError, ValueError, KeyError, TypeError, csv.Error, UnicodeDecodeError,
            json.JSONDecodeError):
        print(json.dumps({"status": "analysis_failed", "reason": "invalid private capture"}))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
