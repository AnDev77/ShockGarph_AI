"""Privately archive selected ETF SIP history with raw and all-adjusted versions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/collector"), str(ROOT / "packages/domain"),
                str(ROOT / "packages/data_pipeline")]

import httpx  # noqa: E402
from shockgraph_collector.alpaca_bars import AlpacaDailyCollector  # noqa: E402
from shockgraph_data_pipeline.daily_price_import import import_daily_prices  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpaca ETF SIP 일봉 원본과 수정본 비공개 수집")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, required=True,
                        help="미국 수신일 이전의 마지막 거래일 YYYY-MM-DD")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/alpaca-private")
    parser.add_argument("--symbols", nargs="+", choices=("TLT", "SPY", "QQQ"),
                        default=("TLT", "SPY"), help="기본 TLT SPY; QQQ 단독 수집 가능")
    args = parser.parse_args(argv)
    if len(set(args.symbols)) != len(args.symbols):
        parser.error("symbols must be distinct")
    key_id = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key_id or not secret:
        print(json.dumps({"status": "missing_credentials", "required_environment": [
            "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]}, ensure_ascii=False))
        return 2
    try:
        store = ImmutableRawStore(args.raw_root)
        summaries = []
        staged = []
        with AlpacaDailyCollector(key_id, secret) as collector:
            for symbol in args.symbols:
                capture = collector.collect(symbol, args.start, args.end, store)
                imported = import_daily_prices(
                    capture.csv_bytes, store=store, source="alpaca-sip",
                    captured_at=capture.captured_at, start=args.start, end=args.end,
                    symbol=symbol, venue="US_SIP", full_snapshot=True,
                )
                if not imported.quality.structurally_ready:
                    raise ValueError(f"{symbol} is missing scheduled SIP sessions")
                path = args.output_dir / symbol / (
                    capture.captured_at.strftime("%Y%m%dT%H%M%S.%fZ") + ".csv"
                )
                staged.append((path, capture.csv_bytes))
                summaries.append({
                    "symbol": symbol, "feed": "sip", "capture": capture.captured_at.isoformat(),
                    "session_count": capture.session_count,
                    "source_response_sha256": capture.raw_response_hashes,
                    "source_raw_payload_hashes": tuple(item.payload_sha256
                                                       for item in capture.raw_artifacts),
                    "source_raw_artifact_paths": tuple(str(item.path)
                                                       for item in capture.raw_artifacts),
                    "normalized_csv_sha256": imported.quality.file_sha256,
                    "normalized_raw_payload_hash": imported.quality.raw_payload_hash,
                    "normalized_raw_artifact_path": str(imported.raw_artifact.path),
                    "snapshot_path": str(path),
                    "public_performance_allowed": False,
                })
        for path, contents in staged:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as file:
                file.write(contents)
        manifest = {"status": "archived_research_only", "prices": summaries,
                    "actual_response_capture_times_recorded": True,
                    "historical_provider_release_times_verified": False,
                    "redistribution_rights_verified": False}
        manifest_path = args.output_dir / "captures" / (
            max(row["capture"] for row in summaries).replace(":", "-") + ".json"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("x", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
        print(json.dumps({"manifest_path": str(manifest_path), **manifest},
                         ensure_ascii=False))
    except ValueError as error:
        print(json.dumps({"status": "collection_failed", "reason": str(error)},
                         ensure_ascii=False))
        return 2
    except (OSError, httpx.HTTPError):
        print(json.dumps({"status": "collection_failed",
                          "reason": "Alpaca response or local output could not be read"},
                         ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
