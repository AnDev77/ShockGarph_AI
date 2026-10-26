"""Private single-ETF historical summary from a local adjusted-close CSV."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/domain"), str(ROOT / "packages/risk_engine")]

from shockgraph_risk.asset_market import analyze_asset_history  # noqa: E402

from scripts.evaluate_exploratory_history import load_history_prices  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="단일 ETF의 비공개 과거 가격 요약")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.source.strip():
            raise ValueError("source is required")
        prices, fingerprint = load_history_prices(args.input)
        summary = analyze_asset_history(args.symbol, prices, trailing_window=args.window)
        payload = {
            "schema_version": 1,
            "status": "private_retrospective_history_only",
            "source": args.source,
            "source_file_sha256": fingerprint,
            "analysis": asdict(summary),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, default=date.isoformat, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status": payload["status"], "output": str(args.output),
                          "public_display_allowed": False}, ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "reason": str(error)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
