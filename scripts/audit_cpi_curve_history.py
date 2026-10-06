"""발표 목록과 사건별 호가 감사를 대조하는 오프라인 커버리지 감사."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from shockgraph_analytics.cpi_distribution import (  # noqa: E402
    ConsensusVintage,
    ThresholdDistribution,
    ThresholdQuote,
    build_threshold_distribution,
    consensus_surprise_probabilities,
)

SCHEMA = "cpi-curve-history-coverage-v1"


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return parsed


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or any(
        not isinstance(k, str) or type(v) is not int or v < 0 for k, v in value.items()
    ):
        raise ValueError("nonnegative integer counts required")
    return value


def _inventory(
    report: dict[str, Any], *, ticker: str, as_of: datetime
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    if report.get("schema_version") != "kalshi-cpi-threshold-curve-v1":
        raise ValueError("unsupported curve input schema")
    if report.get("event_ticker") != ticker:
        raise ValueError("curve event mismatch")
    if _utc(report["as_of"]) != as_of:
        raise ValueError("curve does not match the common pre-release cutoff")
    if report.get("contract_definition") != (
        "single_decimal_cpi_mom_strictly_greater_percentage_point"
    ):
        raise ValueError("unsupported contract definition")
    rows = report.get("quotes")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("original quote rows required; aggregate summary is insufficient")
    rejected = _counts(report.get("market_rejection_counts"))
    statuses = _counts(report.get("quote_status_counts"))
    candidate = report.get("candidate_threshold_markets")
    inventory = report.get("inventory_markets")
    if (
        type(candidate) is not int
        or type(inventory) is not int
        or (candidate != len(rows) or inventory != candidate + sum(rejected.values()))
    ):
        raise ValueError("market inventory does not reconcile")
    actual_statuses = Counter(str(r.get("status")) for r in rows)
    if dict(actual_statuses) != statuses:
        raise ValueError("quote status counts do not reconcile")
    allowed = {"eligible", "stale", "no_eligible_candles", "access_error"}
    if not set(statuses) <= allowed:
        raise ValueError("unsupported quote status")
    if len({r.get("market_ticker") for r in rows}) != len(rows):
        raise ValueError("duplicate market ticker")
    return rows, rejected, statuses


def _event_curve(
    rows: list[dict[str, Any]],
    *,
    ticker: str,
    as_of: datetime,
    adjustment_limit: float,
    max_quote_age: timedelta,
) -> ThresholdDistribution:
    quotes: list[ThresholdQuote] = []
    for row in rows:
        if row["status"] != "eligible":
            continue
        quote = ThresholdQuote(
            event_id=ticker,
            market_ticker=row["market_ticker"],
            threshold=row["threshold"],
            observed_at=_utc(row["quote_end_at"]),
            # v1 캔들의 종료시각을 역사적 가용시각으로 가정한다. 수신시각 증명은 아니다.
            available_at=_utc(row["quote_end_at"]),
            probability_above=row["probability_above"],
            spread=row["spread"],
            raw_hash=row["raw_hash"],
        )
        if not quote.market_ticker.startswith(ticker + "-T") or (
            Decimal(quote.market_ticker.removeprefix(ticker + "-T"))
            != Decimal(str(quote.threshold))
        ):
            raise ValueError("quote ticker and threshold mismatch")
        volume = row.get("volume")
        if (
            isinstance(volume, bool)
            or not isinstance(volume, (int, float))
            or (not math.isfinite(volume) or volume <= 0 or quote.spread > 0.10)
        ):
            raise ValueError("quote fails baseline spread or volume filter")
        quotes.append(quote)
    return build_threshold_distribution(
        quotes,
        as_of=as_of,
        max_isotonic_adjustment=adjustment_limit,
        max_quote_age=max_quote_age,
    )


def audit_history(
    releases: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    *,
    consensuses: list[dict[str, Any]] | None = None,
    cutoff_minutes: int = 5,
    adjustment_limit: float = 0.05,
    data_scope: str = "synthetic",
) -> dict[str, Any]:
    """누락된 발표도 유지하며 실제 발표값과 자산 수익률은 읽지 않는다."""
    if not releases or type(cutoff_minutes) is not int or not 1 <= cutoff_minutes < 15:
        raise ValueError("nonempty release universe and cutoff between 1 and 14 minutes required")
    if not math.isfinite(adjustment_limit) or not 0 <= adjustment_limit <= 1:
        raise ValueError("adjustment limit must be between zero and one")
    if data_scope not in {"synthetic", "authorized_research"}:
        raise ValueError("unsupported data scope")
    tickers = [r["event_ticker"] for r in releases]
    ids = [r["event_id"] for r in releases]
    if len(set(tickers)) != len(tickers) or len(set(ids)) != len(ids):
        raise ValueError("duplicate release event")
    by_ticker = {r["event_ticker"]: r for r in reports}
    if len(by_ticker) != len(reports):
        raise ValueError("duplicate curve event; select one vintage explicitly")
    if not set(by_ticker) <= set(tickers):
        raise ValueError("curve event outside release universe")
    consensus_rows = [ConsensusVintage.model_validate(r) for r in consensuses or []]
    by_consensus = {r.event_id: r for r in consensus_rows}
    if len(by_consensus) != len(consensus_rows) or not set(by_consensus) <= set(tickers):
        raise ValueError("duplicate or unknown consensus event")
    event_rows: list[dict[str, Any]] = []
    for release in sorted(releases, key=lambda r: (_utc(r["release_at"]), r["event_ticker"])):
        ticker = release["event_ticker"]
        release_at = _utc(release["release_at"])
        as_of = release_at - timedelta(minutes=cutoff_minutes)
        row: dict[str, Any] = {
            "event_id": release["event_id"],
            "event_ticker": ticker,
            "release_at": release_at.isoformat(),
            "as_of": as_of.isoformat(),
            "status": "missing_curve_report",
            "consensus_status": "curve_unavailable" if ticker in by_consensus else "not_provided",
        }
        if ticker in by_ticker:
            try:
                quotes, rejected, statuses = _inventory(
                    by_ticker[ticker], ticker=ticker, as_of=as_of
                )
                row.update(market_rejection_counts=rejected, quote_status_counts=statuses)
                curve = _event_curve(
                    quotes,
                    ticker=ticker,
                    as_of=as_of,
                    adjustment_limit=adjustment_limit,
                    max_quote_age=timedelta(minutes=15 - cutoff_minutes),
                )
                thresholds = {Decimal(str(t)) for t in curve.thresholds}
                # 계산 가능한 중심값 후보이며 전문가 컨센서스 추정값이 아니다.
                centers = sorted(
                    t
                    for t in thresholds
                    if t % Decimal("0.1") == 0 and t - Decimal("0.1") in thresholds
                )
                row.update(
                    status="eligible",
                    threshold_count=len(curve.thresholds),
                    raw_monotone=curve.raw_monotone,
                    max_isotonic_adjustment=curve.max_isotonic_adjustment,
                    max_quote_age_minutes=curve.max_quote_age_minutes,
                    exact_boundary_centers=[float(t) for t in centers],
                    market_rejection_counts=rejected,
                    quote_status_counts=statuses,
                )
                if ticker in by_consensus:
                    try:
                        consensus_surprise_probabilities(
                            curve, by_consensus[ticker], release_at=release_at
                        )
                        row["consensus_status"] = "eligible"
                    except ValueError as error:
                        row.update(consensus_status="abstained", consensus_error=str(error))
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                row.update(status="abstained", curve_error=str(error))
        event_rows.append(row)
    status_counts = Counter(row["status"] for row in event_rows)
    consensus_counts = Counter(row["consensus_status"] for row in event_rows)
    rejection_counts: Counter[str] = Counter()
    quote_counts: Counter[str] = Counter()
    for row in event_rows:
        rejection_counts.update(row.get("market_rejection_counts", {}))
        quote_counts.update(row.get("quote_status_counts", {}))
    return {
        "schema_version": SCHEMA,
        "data_scope": data_scope,
        "total_release_events": len(event_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "consensus_status_counts": dict(sorted(consensus_counts.items())),
        "validated_inventory_events": sum("quote_status_counts" in r for r in event_rows),
        "market_rejection_counts": dict(sorted(rejection_counts.items())),
        "quote_status_counts": dict(sorted(quote_counts.items())),
        "cutoff_minutes_before_release": cutoff_minutes,
        "maximum_quote_age_minutes_at_cutoff": 15 - cutoff_minutes,
        "maximum_minutes_before_release": 15,
        "maximum_spread": 0.10,
        "minimum_volume_exclusive": 0,
        "maximum_isotonic_adjustment": adjustment_limit,
        "uses_outcomes_or_asset_returns": False,
        "availability_assumption": "v1_candle_end_time_not_verified_receipt_time",
        "events": event_rows,
    }


def synthetic_inputs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    releases, reports = [], []
    for index in range(1, 5):
        ticker = f"SYNTH-CPI-{index}"
        release_at = datetime(2025, index, 15, 13, 30, tzinfo=UTC)
        as_of = release_at - timedelta(minutes=5)
        releases.append(
            {"event_id": ticker, "event_ticker": ticker, "release_at": release_at.isoformat()}
        )
        if index == 4:
            continue
        probabilities = (
            [0.8, 0.55, 0.2]
            if index == 1
            else ([0.52, 0.54, 0.2] if index == 2 else [0.2, 0.8, 0.1])
        )
        quotes = [
            {
                "market_ticker": f"{ticker}-T{threshold}",
                "threshold": threshold,
                "status": "eligible",
                "quote_end_at": (as_of - timedelta(minutes=1)).isoformat(),
                "probability_above": probability,
                "spread": 0.02,
                "volume": 5,
                "raw_hash": hashlib.sha256(f"synthetic-{index}-{threshold}".encode()).hexdigest(),
            }
            for threshold, probability in zip([0.2, 0.3, 0.4], probabilities, strict=True)
        ]
        reports.append(
            {
                "schema_version": "kalshi-cpi-threshold-curve-v1",
                "event_ticker": ticker,
                "as_of": as_of.isoformat(),
                "inventory_markets": 3,
                "candidate_threshold_markets": 3,
                "market_rejection_counts": {},
                "quote_status_counts": {"eligible": 3},
                "quotes": quotes,
                "contract_definition": "single_decimal_cpi_mom_strictly_greater_percentage_point",
            }
        )
    return releases, reports


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI 전체 사건의 확률곡선 커버리지 감사")
    parser.add_argument("--demo", action="store_true", help="독립적으로 만든 합성 입력 실행")
    parser.add_argument("--releases", type=Path)
    parser.add_argument("--curves-dir", type=Path)
    parser.add_argument("--consensus", type=Path, help="발표 전 빈티지 JSON 배열")
    parser.add_argument("--authorization-record", type=Path, help="별도 보관한 실제 이용 허가 기록")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/cpi-curve-history"))
    args = parser.parse_args()
    if args.demo:
        if any((args.releases, args.curves_dir, args.consensus, args.authorization_record)):
            parser.error("--demo는 실제 자료 입력과 함께 사용할 수 없습니다")
        releases, reports = synthetic_inputs()
        consensuses = None
        evidence_hash = None
        scope = "synthetic"
    else:
        if not args.releases or not args.curves_dir or not args.authorization_record:
            parser.error(
                "실제 입력에는 --releases, --curves-dir, --authorization-record가 필요합니다"
            )
        evidence = args.authorization_record.read_bytes()
        if not evidence.strip():
            parser.error("이용 허가 기록이 비어 있습니다")
        evidence_hash = hashlib.sha256(evidence).hexdigest()
        with args.releases.open(encoding="utf-8", newline="") as handle:
            releases = list(csv.DictReader(handle))
        reports = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(args.curves_dir.rglob("report.json"))
        ]
        consensuses = (
            json.loads(args.consensus.read_text(encoding="utf-8")) if args.consensus else None
        )
        scope = "authorized_research"
    summary = audit_history(releases, reports, consensuses=consensuses, data_scope=scope)
    summary["input_sha256"] = hashlib.sha256(
        _canonical(
            {
                "releases": releases,
                "curves": reports,
                "consensus": consensuses,
            }
        ).encode()
    ).hexdigest()
    summary["authorization_record_sha256"] = evidence_hash
    content = _canonical(summary)
    destination = args.output_dir / hashlib.sha256(content.encode()).hexdigest() / "report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_text(encoding="utf-8") != content:
        raise ValueError("existing summary differs from content address")
    destination.write_text(content, encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(destination),
                "data_scope": scope,
                "status_counts": summary["status_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
