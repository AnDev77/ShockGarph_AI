from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from build_cpi_asset_panel import _load_bars, _load_releases, _parse_datetime  # noqa: E402
from shockgraph_analytics.evaluation import paired_interval  # noqa: E402
from shockgraph_analytics.kalshi_ablation import (  # noqa: E402
    GROUPS,
    AblationEvent,
    summarize,
    walk_forward,
)
from shockgraph_analytics.paper_panel import build_asset_windows  # noqa: E402


@dataclass(frozen=True)
class FilterPolicy:
    name: str
    freshness_minutes: Literal[15, 30]
    max_spread: float
    require_positive_volume: bool


POLICIES = (
    FilterPolicy("F0", 15, 0.10, True),
    FilterPolicy("F1", 30, 0.10, True),
    FilterPolicy("F2", 15, 0.15, True),
    FilterPolicy("F3", 15, 0.10, False),
    FilterPolicy("F4", 30, 0.15, False),
)


def select_quote(
    candidates: list[dict[str, Any]], release_at: datetime, policy: FilterPolicy
) -> tuple[dict[str, Any] | None, str]:
    if release_at.tzinfo is None or release_at.utcoffset() != timedelta(0):
        raise ValueError("release time must be UTC")
    valid: list[dict[str, Any]] = []
    stages: Counter[str] = Counter()
    for candidate in candidates:
        try:
            quote_at = _parse_datetime(str(candidate["end_at"]))
            probability = float(candidate["yes_midpoint"])
            spread = float(candidate["spread"])
            raw_volume = candidate.get("volume")
            volume = None if raw_volume is None else float(raw_volume)
        except (KeyError, TypeError, ValueError):
            stages["invalid_candidate"] += 1
            continue
        if not all(math.isfinite(value) for value in (probability, spread)):
            stages["invalid_candidate"] += 1
            continue
        if volume is not None and (not math.isfinite(volume) or volume < 0):
            stages["invalid_candidate"] += 1
            continue
        if not 0 <= probability <= 1 or not 0 <= spread <= 1:
            stages["invalid_candidate"] += 1
            continue
        age = release_at - quote_at
        if age <= timedelta(0):
            stages["at_or_after_release"] += 1
        elif age > timedelta(minutes=policy.freshness_minutes):
            stages["stale_before_release"] += 1
        elif spread > policy.max_spread:
            stages["spread_exceeded"] += 1
        elif policy.require_positive_volume and (volume is None or volume <= 0):
            stages["volume_not_positive"] += 1
        else:
            valid.append(
                {
                    "quote_at": quote_at,
                    "probability": probability,
                    "spread": spread,
                    "volume": volume,
                }
            )
    if valid:
        return max(valid, key=lambda row: row["quote_at"]), "accepted"
    if not candidates:
        return None, "no_structural_quote"
    for reason in (
        "volume_not_positive",
        "spread_exceeded",
        "stale_before_release",
        "at_or_after_release",
        "invalid_candidate",
    ):
        if stages[reason]:
            return None, reason
    return None, "no_structural_quote"


def _load_audit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("series_ticker") != "KXCPI":
        raise ValueError("audit report must be a KXCPI object")
    events = payload.get("events")
    if not isinstance(events, list) or not all(isinstance(row, dict) for row in events):
        raise ValueError("audit events must be an object list")
    return payload


def build_policy_events(
    audit_path: Path, releases_path: Path, bars_path: Path, policy: FilterPolicy
) -> tuple[list[AblationEvent], dict[str, int]]:
    audit = _load_audit(audit_path)
    audit_rows = {str(row.get("event_ticker")): row for row in audit["events"]}
    if len(audit_rows) != len(audit["events"]):
        raise ValueError("audit event tickers must be unique")
    releases = _load_releases(releases_path)
    bars = _load_bars(bars_path)
    bar_index = {(bar.asset_id, bar.price_at): bar for bar in bars}
    windows = build_asset_windows(releases, bars)
    by_event: dict[str, dict[str, Any]] = {}
    for window in windows.windows:
        group = f"{window.asset_id}:{window.horizon}"
        if group in GROUPS:
            by_event.setdefault(window.event_id, {})[group] = window

    counts: Counter[str] = Counter()
    events: list[AblationEvent] = []
    for release in releases:
        audit_row = audit_rows.get(release.event_ticker)
        if audit_row is None:
            counts["missing_audit_event"] += 1
            continue
        if audit_row.get("outcome") != release.outcome:
            raise ValueError("Kalshi and BLS outcomes differ")
        candidates = audit_row.get("quote_candidates", [])
        if not isinstance(candidates, list) or not all(isinstance(row, dict) for row in candidates):
            raise ValueError("quote candidates must be an object list")
        quote, reason = select_quote(candidates, release.release_at, policy)
        if quote is None:
            counts[reason] += 1
            continue
        selected = by_event.get(release.event_id, {})
        if set(selected) != set(GROUPS):
            counts["incomplete_asset_windows"] += 1
            continue
        if any(
            bar_index[window.asset_id, window.start_at].available_at >= release.release_at
            for window in selected.values()
        ):
            raise ValueError("start price unavailable before release")
        events.append(
            AblationEvent(
                event_id=release.event_id,
                release_at=release.release_at,
                quote_at=quote["quote_at"],
                quote_age_limit_minutes=policy.freshness_minutes,
                label_available_at=max(
                    bar_index[window.asset_id, window.end_at].available_at
                    for window in selected.values()
                ),
                probability=quote["probability"],
                outcome=release.outcome == "yes",
                returns={key: window.return_value for key, window in selected.items()},
            )
        )
    counts["accepted"] = len(events)
    counts["input_events"] = len(releases)
    if counts["input_events"] != sum(
        value for key, value in counts.items() if key != "input_events"
    ):
        raise ValueError("selection counts do not reconcile")
    return events, dict(sorted(counts.items()))


def _valid_folds(events: list[AblationEvent], min_train: int) -> dict[str, dict[str, Any]]:
    return {
        str(fold["event_id"]): fold
        for fold in walk_forward(events, min_train=min_train)
        if fold["status"] == "evaluated"
    }


def compare_shared_folds(
    baseline: list[AblationEvent], candidate: list[AblationEvent], *, min_train: int
) -> dict[str, Any]:
    f0 = _valid_folds(baseline, min_train)
    other = _valid_folds(candidate, min_train)
    shared = sorted(set(f0) & set(other))
    result: dict[str, Any] = {
        "status": "exploratory" if len(shared) >= 10 else "insufficient_test_events",
        "min_train": min_train,
        "required_test_events": 10,
        "shared_test_events": len(shared),
        "comparison": {},
    }
    if len(shared) < 10:
        return result
    for group in GROUPS:
        f0_historical = [
            f0[event]["scores"][group]["historical_frequency"]["crps"] for event in shared
        ]
        f0_kalshi = [f0[event]["scores"][group]["kalshi_probability"]["crps"] for event in shared]
        other_historical = [
            other[event]["scores"][group]["historical_frequency"]["crps"] for event in shared
        ]
        other_kalshi = [
            other[event]["scores"][group]["kalshi_probability"]["crps"] for event in shared
        ]
        f0_difference = [k - h for h, k in zip(f0_historical, f0_kalshi, strict=True)]
        other_difference = [k - h for h, k in zip(other_historical, other_kalshi, strict=True)]
        changes = [
            other_value - f0_value
            for f0_value, other_value in zip(f0_difference, other_difference, strict=True)
        ]
        interval = paired_interval(changes)
        assert interval is not None
        result["comparison"][group] = {
            "f0_historical_crps": math.fsum(f0_historical) / len(shared),
            "f0_kalshi_crps": math.fsum(f0_kalshi) / len(shared),
            "candidate_historical_crps": math.fsum(other_historical) / len(shared),
            "candidate_kalshi_crps": math.fsum(other_kalshi) / len(shared),
            "f0_mean_crps_difference": math.fsum(f0_difference) / len(shared),
            "candidate_mean_crps_difference": math.fsum(other_difference) / len(shared),
            "change_in_mean_difference": math.fsum(changes) / len(shared),
            "paired_event_bootstrap95": interval,
        }
    return result


def export_report(audit: Path, releases: Path, bars: Path, output: Path) -> Path:
    event_sets: dict[str, list[AblationEvent]] = {}
    policies: dict[str, Any] = {}
    for policy in POLICIES:
        events, counts = build_policy_events(audit, releases, bars, policy)
        event_sets[policy.name] = events
        policies[policy.name] = {
            "settings": {
                "freshness_minutes": policy.freshness_minutes,
                "max_spread": policy.max_spread,
                "require_positive_volume": policy.require_positive_volume,
            },
            "selection_counts": counts,
            "common_events": len(events),
            "diagnostic": summarize(events, min_train=5).model_dump(mode="json"),
            "research": summarize(events, min_train=20).model_dump(mode="json"),
        }
    shared = {
        name: {
            "diagnostic": compare_shared_folds(event_sets["F0"], events, min_train=5),
            "research": compare_shared_folds(event_sets["F0"], events, min_train=20),
        }
        for name, events in event_sets.items()
        if name != "F0"
    }
    audit_payload = _load_audit(audit)
    report = {
        "schema_version": "cpi-kalshi-filter-sensitivity-v1",
        "scope": "exploratory_filter_sensitivity_not_macro_benchmark",
        "input_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (("audit", audit), ("releases", releases), ("bars", bars))
        },
        "audit_candle_failure_counts": audit_payload.get("candle_failure_counts", {}),
        "audit_candle_primary_exclusion_counts": audit_payload.get(
            "candle_primary_exclusion_counts", {}
        ),
        "audit_no_eligible_event_reasons": audit_payload.get(
            "no_eligible_candle_event_reasons", {}
        ),
        "policies": policies,
        "shared_with_f0": shared,
        "interpretation": [
            "기존 표본을 관찰한 뒤 수행한 탐색적 민감도 분석",
            "성능 변화만으로 필터 편향 또는 필터 필수성을 증명하지 않음",
            "후보별 전체 표본 비교와 F0 공통 시험 사건 비교를 구분",
            "전통 거시정보 기준선과 Kalshi 추가 효과의 C-B 검증이 아님",
        ],
        "publication_boundary": "aggregate_metrics_only_no_credentials_raw_prices_or_event_returns",
    }
    content = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_text(encoding="utf-8") != content:
        raise ValueError("existing sensitivity report differs")
    output.write_text(content, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="CPI Kalshi 필터 F0~F4 민감도 분석")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--asset-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {"report": str(export_report(args.audit, args.releases, args.asset_bars, args.output))},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
