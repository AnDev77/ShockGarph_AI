from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/collector"),
    str(ROOT / "packages/data_pipeline"),
    str(ROOT / "packages/event_study"),
]

from shockgraph_analytics.paper_panel import (  # noqa: E402
    AssetMinuteBar,
    CpiReleaseVintage,
    build_asset_windows,
)
from shockgraph_collector.alpaca import (  # noqa: E402
    AlpacaMarketDataClient,
    AlpacaMinuteBar,
    normalize_alpaca_minute_bars,
)
from shockgraph_collector.client import RetryPolicy  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402

SCHEMA_VERSION = "alpaca-etf-minute-bars-v1"
ASSETS = ("SPY", "TLT", "GLD")
BAR_FIELDS = (
    "asset_id",
    "source_start_at",
    "price_at",
    "available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "extended_hours",
    "raw_hash",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_releases(path: Path) -> list[CpiReleaseVintage]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("release vintage CSV is empty")
    releases = [
        CpiReleaseVintage.model_validate(
            {
                "event_id": row["event_id"],
                "event_ticker": row["event_ticker"],
                "reference_month": date.fromisoformat(row["reference_month"]),
                "release_at": _parse_datetime(row["release_at"]),
                "actual_mom_first": float(row["actual_mom_first"]),
                "threshold": float(row["threshold"]),
                "outcome": row["bls_outcome"],
                "source_url": row["source_url"],
                "raw_hash": row["raw_hash"],
            }
        )
        for row in rows
    ]
    event_ids = {release.event_id for release in releases}
    if len(event_ids) != len(releases):
        raise ValueError("release event ids must be unique")
    return sorted(releases, key=lambda row: (row.release_at, row.event_id))


def credentials_from_env(environment: Mapping[str, str]) -> tuple[str, str]:
    key_id = environment.get("ALPACA_API_KEY_ID", "").strip()
    secret_key = environment.get("ALPACA_API_SECRET_KEY", "").strip()
    if not key_id or not secret_key:
        raise RuntimeError(
            "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are required; "
            "no demo credential or alternate source is substituted"
        )
    return key_id, secret_key


def _asset_model(bar: AlpacaMinuteBar) -> AssetMinuteBar:
    return AssetMinuteBar(
        asset_id=bar.asset_id,
        price_at=bar.price_at,
        available_at=bar.available_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        extended_hours=bar.extended_hours,
        raw_hash=bar.raw_hash,
    )


def _csv_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _write_immutable(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"existing Alpaca artifact differs: {path.name}")
        return
    path.write_text(content, encoding="utf-8")


def collect_alpaca_asset_dataset(
    client: AlpacaMarketDataClient,
    store: ImmutableRawStore,
    release_path: Path,
    output_dir: Path,
    *,
    feed: str = "sip",
    request_interval_seconds: float = 0.35,
) -> Path:
    if request_interval_seconds < 0:
        raise ValueError("request interval must be nonnegative")
    releases = _load_releases(release_path)
    normalized: list[AlpacaMinuteBar] = []
    for index, release in enumerate(releases):
        pages = client.collect_stock_bars(
            store,
            symbols=ASSETS,
            start=release.release_at - timedelta(minutes=2),
            end=release.release_at + timedelta(minutes=30),
            feed=feed,
        )
        for page in pages:
            normalized.extend(
                normalize_alpaca_minute_bars(
                    page.payload,
                    raw_hash=page.artifact.payload_sha256,
                )
            )
        if index + 1 < len(releases):
            time.sleep(request_interval_seconds)

    bar_keys = {(bar.asset_id, bar.source_start_at) for bar in normalized}
    if len(bar_keys) != len(normalized):
        raise ValueError("duplicate Alpaca bars across release requests or pages")
    normalized.sort(key=lambda row: (row.price_at, row.asset_id))
    asset_models = [_asset_model(bar) for bar in normalized]
    windows = build_asset_windows(
        releases,
        asset_models,
        horizons={"m5": timedelta(minutes=5), "m30": timedelta(minutes=30)},
    )

    buffer = io.StringIO(newline="")
    fields: list[str] = list(BAR_FIELDS)
    writer: csv.DictWriter[str] = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for bar in normalized:
        writer.writerow(
            {
                "asset_id": bar.asset_id,
                "source_start_at": _csv_timestamp(bar.source_start_at),
                "price_at": _csv_timestamp(bar.price_at),
                "available_at": _csv_timestamp(bar.available_at),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "extended_hours": str(bar.extended_hours).lower(),
                "raw_hash": bar.raw_hash,
            }
        )
    csv_content = buffer.getvalue()
    coverage_payload = {
        "coverage": windows.coverage,
        "common_event_ids": windows.common_event_ids,
    }
    coverage_content = (
        json.dumps(
            coverage_payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    identity = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "release_sha256": _sha256(release_path),
            "feed": feed,
            "bar_csv_sha256": hashlib.sha256(csv_content.encode()).hexdigest(),
            "coverage_sha256": hashlib.sha256(coverage_content.encode()).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(identity.encode()).hexdigest()
    destination = output_dir / run_id
    destination.mkdir(parents=True, exist_ok=True)
    _write_immutable(destination / "asset_minute_bars.csv", csv_content)
    _write_immutable(destination / "coverage.json", coverage_content)
    status_counts: dict[str, int] = {}
    for row in windows.coverage:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source": "alpaca_market_data",
        "feed": feed,
        "adjustment": "raw",
        "bar_time_semantics": "source_start_plus_one_minute_is_close_and_available_time",
        "release_vintage_sha256": _sha256(release_path),
        "release_events": len(releases),
        "bar_rows": len(normalized),
        "coverage_rows": len(windows.coverage),
        "coverage_status_counts": status_counts,
        "common_events": len(windows.common_event_ids),
        "common_event_ids": windows.common_event_ids,
        "bar_csv_sha256": hashlib.sha256(csv_content.encode()).hexdigest(),
        "coverage_sha256": hashlib.sha256(coverage_content.encode()).hexdigest(),
        "publication_status": "raw_market_data_local_only_pending_license_review",
    }
    metadata_content = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _write_immutable(destination / "metadata.json", metadata_content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca에서 CPI 발표 전후 미국 ETF 분봉 수집")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--feed", choices=("iex", "sip"), default="sip")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "artifacts/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/alpaca-etf-bars")
    parser.add_argument("--request-interval", type=float, default=0.35)
    args = parser.parse_args()
    try:
        key_id, secret_key = credentials_from_env(os.environ)
    except RuntimeError as error:
        parser.error(str(error))
    with AlpacaMarketDataClient(
        api_key_id=key_id,
        api_secret_key=secret_key,
        retry_policy=RetryPolicy(max_attempts=4, initial_backoff_seconds=1),
    ) as client:
        destination = collect_alpaca_asset_dataset(
            client,
            ImmutableRawStore(args.raw_dir),
            args.releases,
            args.output,
            feed=args.feed,
            request_interval_seconds=args.request_interval,
        )
    print(json.dumps({"asset_bar_dataset": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
