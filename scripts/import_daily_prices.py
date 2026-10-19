from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/domain"), str(ROOT / "packages/data_pipeline")]

from shockgraph_data_pipeline.daily_price_import import import_daily_prices  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="TLT 수정가격 CSV의 비공개 계보·품질 검사")
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--source", required=True, help="공급원 식별자: 영문 소문자·숫자·-_")
    parser.add_argument("--captured-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--prediction-delay-minutes", type=int, default=60)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    args = parser.parse_args()
    try:
        result = import_daily_prices(
            args.prices.read_bytes(),
            store=ImmutableRawStore(args.raw_root),
            source=args.source,
            captured_at=args.captured_at,
            start=args.start,
            end=args.end,
            prediction_delay=timedelta(minutes=args.prediction_delay_minutes),
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(asdict(result.quality), ensure_ascii=False, indent=2))
    return 0 if result.quality.structurally_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
