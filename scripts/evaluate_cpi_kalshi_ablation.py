from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from build_cpi_asset_panel import (  # noqa: E402
    _load_bars,
    _load_releases,
    _parse_datetime,
    _read_csv,
)
from shockgraph_analytics.kalshi_ablation import (  # noqa: E402
    GROUPS,
    AblationEvent,
    AblationReport,
    summarize,
)
from shockgraph_analytics.paper_panel import build_asset_windows  # noqa: E402


def build_events(releases: Path, probabilities: Path, bars: Path) -> list[AblationEvent]:
    release_rows = _load_releases(releases)
    probability_rows = _read_csv(probabilities)
    by_ticker = {row["event_ticker"]: row for row in probability_rows}
    if len(by_ticker) != len(probability_rows):
        raise ValueError("duplicate probability event")
    if len({r.event_id for r in release_rows}) != len(release_rows):
        raise ValueError("duplicate release event")
    bar_rows = _load_bars(bars)
    bar_index = {(b.asset_id, b.price_at): b for b in bar_rows}
    windows = build_asset_windows(release_rows, bar_rows)
    by_event = {}
    for w in windows.windows:
        if f"{w.asset_id}:{w.horizon}" in GROUPS:
            by_event.setdefault(w.event_id, {})[f"{w.asset_id}:{w.horizon}"] = w
    events = []
    for release in release_rows:
        p = by_ticker.get(release.event_ticker)
        selected = by_event.get(release.event_id, {})
        if p is None or p["status"] != "eligible" or set(selected) != set(GROUPS):
            continue
        if p["outcome"] != release.outcome:
            raise ValueError("Kalshi and BLS outcomes differ")
        spread, volume = float(p["spread"]), float(p["volume"])
        if not math.isfinite(spread) or not 0 <= spread <= 0.10:
            raise ValueError("eligible quote violates spread gate")
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError("eligible quote requires positive volume")
        if any(
            bar_index[w.asset_id, w.start_at].available_at >= release.release_at
            for w in selected.values()
        ):
            raise ValueError("start price unavailable before release")
        events.append(
            AblationEvent(
                event_id=release.event_id,
                release_at=release.release_at,
                quote_at=_parse_datetime(p["quote_end_at"]),
                label_available_at=max(
                    bar_index[w.asset_id, w.end_at].available_at for w in selected.values()
                ),
                probability=float(p["probability_yes"]),
                outcome=release.outcome == "yes",
                returns={key: w.return_value for key, w in selected.items()},
            )
        )
    return events


def export_report(releases: Path, probabilities: Path, bars: Path, output: Path) -> Path:
    events = build_events(releases, probabilities, bars)
    report = AblationReport(
        common_events=len(events),
        input_sha256={
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("releases", releases),
                ("probabilities", probabilities),
                ("bars", bars),
            )
        },
        research=summarize(events, min_train=20),
        diagnostic=summarize(events, min_train=5),
        limitations=[
            "전통 거시 기대·금리·최근 변동성 기준선 자료 미확보: 논문의 C-B 비교가 아님",
            "T0.3 이진 계약만 사용하며 전체 CPI 확률분포를 복원하지 않음",
            "사후 자산 선정에 따른 탐색 결과: 신규 또는 외부 표본 검증 필요",
            "동일 사건 재표집 1000회·seed 42: 월별 독립 가정, 순차 학습 의존성 미반영",
            "네 조합의 신뢰구간은 개별 구간이며 다중비교 보정되지 않음",
            "후속 위험·곡률·DNN 연구는 배포 이후 진행, 실시간 예측 및 자동 거래 미제공",
        ],
    )
    content = (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_text(encoding="utf-8") != content:
        raise ValueError("existing ablation report differs")
    output.write_text(content, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="SPY·TLT 동일 사건의 Kalshi 확률 추가 효과 비교")
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--asset-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "report": str(
                    export_report(args.releases, args.probabilities, args.asset_bars, args.output)
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
