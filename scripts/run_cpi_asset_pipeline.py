from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/collector"))
sys.path.insert(0, str(ROOT / "packages/data_pipeline"))

from build_cpi_asset_panel import build_panel_dataset  # noqa: E402
from collect_alpaca_etf_bars import (  # noqa: E402
    collect_alpaca_asset_dataset,
    credentials_from_env,
)
from evaluate_cpi_price_baseline import evaluate_panel  # noqa: E402
from shockgraph_collector.alpaca import AlpacaMarketDataClient  # noqa: E402
from shockgraph_collector.client import RetryPolicy  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="과거 SIP 수집부터 CPI ETF 기준선 평가까지 실행")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
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
        asset_dir = collect_alpaca_asset_dataset(
            client,
            ImmutableRawStore(args.artifacts / "raw"),
            args.releases,
            args.artifacts / "alpaca-etf-bars",
            feed="sip",
        )
    panel_dir = build_panel_dataset(
        args.releases,
        args.probabilities,
        asset_dir / "asset_minute_bars.csv",
        args.artifacts / "cpi-asset-panel",
    )
    report = evaluate_panel(panel_dir, args.artifacts / "cpi-price-baseline")
    print(
        json.dumps(
            {"asset_dataset": str(asset_dir), "asset_panel": str(panel_dir), "report": str(report)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
