"""Private exploratory TLT GARCH comparison and chart from a local adjusted-close CSV."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/domain"), str(ROOT / "packages/risk_engine")]

from shockgraph_risk.exploratory_garch import (  # noqa: E402
    ExploratoryGarchReport,
    evaluate_exploratory_garch,
)
from shockgraph_risk.exploratory_model import compare_price_only_model  # noqa: E402

from scripts.evaluate_exploratory_history import load_history_prices  # noqa: E402


def compare_private_history(
    path: Path, *, source: str, holdout_start: date
) -> tuple[dict[str, Any], tuple[ExploratoryGarchReport, ...]]:
    if not source.strip():
        raise ValueError("source must be named")
    prices, fingerprint = load_history_prices(path)
    garch = evaluate_exploratory_garch(prices, holdout_start=holdout_start)
    ridge = compare_price_only_model(prices, holdout_start=holdout_start)
    for a, b in zip(garch, ridge, strict=True):
        if (a.horizon != b.horizon or a.sample_size != b.holdout_count
                or a.first_prediction_date != b.first_holdout_date
                or a.last_prediction_date != b.last_holdout_date
                or (a.ewma_mae is not None and b.ewma_mae is not None
                    and abs(a.ewma_mae - b.ewma_mae) > 1e-12)):
            raise ValueError("exploratory models must have exactly matched evaluation dates")
    report = {
        "schema_version": 1,
        "status": "exploratory_current_history_only",
        "symbol": "TLT", "source": source, "source_file_sha256": fingerprint,
        "observation_count": len(prices),
        "first_observation_date": prices[0].session_date,
        "last_observation_date": prices[-1].session_date,
        "holdout_start": holdout_start,
        "calendar_validated": False,
        "historical_price_vintages_verified": False,
        "independent_model_selection_holdout": False,
        "public_performance_allowed": False,
        "horizons": [
            {"garch_and_price_baselines": asdict(a), "price_only_ridge": asdict(b)}
            for a, b in zip(garch, ridge, strict=True)
        ],
    }
    return report, garch


def plot_comparison(report: dict[str, Any], horizons: tuple[ExploratoryGarchReport, ...],
                    output: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    except ImportError as error:
        raise ValueError("install the optional viz dependency to draw the chart") from error

    if len(horizons) != 2 or any(row.status != "exploratory_current_history_only"
                                  for row in horizons):
        raise ValueError("both 5 and 20 session comparisons need scored holdout windows")

    colors = {"Observed": "#172b4d", "EWMA": "#168aad", "GARCH": "#e37d23",
              "Trailing": "#8a95a4", "Ridge": "#8461b3"}
    fig, axes = plt.subplots(3, 1, figsize=(13.5, 10), height_ratios=[1.15, 1.15, 0.9])
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("TLT future daily volatility | exploratory comparison",
                 fontsize=18, fontweight="bold", y=0.985)
    fig.text(0.5, 0.945,
             "One current adjusted-close history  |  unverified price vintages  |  "
             "private research",
             ha="center", fontsize=10, color="#6b7280")

    def smooth(values: list[float], window: int = 20) -> list[float]:
        return [sum(values[max(0, index - window + 1):index + 1]) /
                min(index + 1, window) for index in range(len(values))]

    for ax, row in zip(axes[:2], horizons, strict=True):
        days = [point.session_date for point in row.points]
        series = {
            "Observed": [point.observed_volatility * 100 for point in row.points],
            "EWMA": [point.ewma_volatility * 100 for point in row.points],
            "GARCH": [point.garch_volatility * 100 for point in row.points],
        }
        for name, values in series.items():
            ax.plot(days, smooth(values), label=name, color=colors[name],
                    linewidth=2.1 if name == "Observed" else 1.5,
                    alpha=0.95 if name == "Observed" else 0.85)
        ax.set_title(f"Next {row.horizon} trading days", loc="left", fontweight="bold")
        ax.set_ylabel("Daily volatility (%)")
        ax.grid(axis="y", alpha=0.17)
        ax.spines[["top", "right"]].set_visible(False)
        locator = AutoDateLocator(minticks=4, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    axes[0].legend(ncol=3, loc="upper right", frameon=False)

    bar = axes[2]
    labels = ["Trailing", "EWMA", "Ridge", "GARCH"]
    maximum_mae = 0.0
    for h_index, (row, source_row) in enumerate(zip(horizons, report["horizons"], strict=True)):
        ridge = source_row["price_only_ridge"]
        values = [row.trailing_mae, row.ewma_mae, ridge["ridge_mae"], row.garch_mae]
        if any(value is None for value in values):
            raise ValueError("missing score for the comparison chart")
        for index, (label, value) in enumerate(zip(labels, values, strict=True)):
            assert value is not None
            maximum_mae = max(maximum_mae, value)
            position = h_index * 5 + index
            bar.bar(position, value * 100, width=0.77, color=colors[label])
            bar.text(position, value * 100 + 0.005, f"{value * 100:.3f}",
                     ha="center", va="bottom", fontsize=9)
    bar.set_xticks(list(range(4)) + list(range(5, 9)), labels * 2)
    bar.set_title("Mean absolute error on the same holdout dates", loc="left",
                  fontweight="bold")
    bar.set_ylabel("Percentage points")
    bar.set_ylim(0, maximum_mae * 135)
    bar.text(1.5, 0.94, "5-day target", ha="center", transform=bar.get_xaxis_transform())
    bar.text(6.5, 0.94, "20-day target", ha="center", transform=bar.get_xaxis_transform())
    bar.grid(axis="y", alpha=0.17)
    bar.set_axisbelow(True)
    bar.spines[["top", "right"]].set_visible(False)

    fig.text(0.5, 0.016,
             "Lines: 20-session smoothing for readability. Bars: unsmoothed holdout MAE. "
             "Past prices may have been revised; no live forecast claim.",
             ha="center", fontsize=9, color="#6b7280")
    fig.tight_layout(rect=(0.035, 0.045, 0.99, 0.93), h_pad=2.3)
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TLT 과거 수정종가의 비공개 탐색 그래프")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--holdout-start", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report, horizons = compare_private_history(
            args.input, source=args.source, holdout_start=args.holdout_start
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        chart = args.output_dir / "tlt-volatility-exploratory.png"
        summary = args.output_dir / "tlt-volatility-exploratory.json"
        if chart.exists() or summary.exists():
            raise ValueError("output already exists; choose a new private directory")
        plot_comparison(report, horizons, chart)
        with summary.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, default=date.isoformat)
            stream.write("\n")
        print(json.dumps({"status": report["status"], "chart": str(chart),
                          "report": str(summary),
                          "public_performance_allowed": False}, ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "reason": str(error)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
