"""Evaluate a private, currently downloaded adjusted close CSV without pretending PIT."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/domain"), str(ROOT / "packages/risk_engine")]

from shockgraph_risk.exploratory_history import (  # noqa: E402
    HistoryPrice,
    evaluate_adjusted_history,
)


def run_history(path: Path, *, holdout_start: date, source: str) -> dict[str, Any]:
    if not source.strip():
        raise ValueError("source must be named")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError("input price file could not be read") from error
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != ["session_date", "adjusted_close"]:
            raise ValueError("CSV needs session_date,adjusted_close columns")
        rows = []
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None or value == "" for value in row.values()):
                raise ValueError(f"line {line}: incomplete price row")
            try:
                closing = float(row["adjusted_close"])
                session_date = date.fromisoformat(row["session_date"])
            except ValueError as error:
                raise ValueError(f"line {line}: invalid date or adjusted close") from error
            if not math.isfinite(closing) or closing <= 0:
                raise ValueError(f"line {line}: adjusted close must be positive and finite")
            rows.append(HistoryPrice(session_date, closing))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("CSV must be valid UTF-8 with two columns") from error
    reports = evaluate_adjusted_history(rows, holdout_start=holdout_start)
    return {
        "status": "exploratory_current_history_only",
        "source": source,
        "source_file_sha256": hashlib.sha256(data).hexdigest(),
        "symbol": "TLT",
        "observation_count": len(rows),
        "first_observation_date": rows[0].session_date.isoformat(),
        "last_observation_date": rows[-1].session_date.isoformat(),
        "holdout_start": holdout_start.isoformat(),
        "calendar_validated": False,
        "historical_price_vintages_verified": False,
        "public_performance_allowed": False,
        "horizons": [asdict(report) for report in reports],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="비공개 현재 수정가격 이력으로 탐색적 TLT 평가")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--holdout-start", type=date.fromisoformat, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, help="비공개 JSON 경로, 생략하면 표준 출력")
    args = parser.parse_args(argv)
    try:
        report = run_history(args.input, holdout_start=args.holdout_start, source=args.source)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, default=date.isoformat) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded)
    except (OSError, ValueError) as error:
        reason = str(error) if isinstance(error, ValueError) else "output could not be written"
        print(json.dumps({"status": "invalid_input", "reason": reason}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
