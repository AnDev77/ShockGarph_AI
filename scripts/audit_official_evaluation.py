"""Count independent official outcome windows without exposing private scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.archive_forward_capture import audit_capture  # noqa: E402
from scripts.audit_private_capture import _listed_indices  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402
from scripts.score_archived_forward import official_score_plan  # noqa: E402


def nonoverlap_count(windows: Iterable[tuple[int, int]]) -> int:
    """Maximum count of disjoint inclusive intervals, by earliest finish."""
    ordered = sorted(windows, key=lambda item: (item[1], item[0]))
    if any(first > last for first, last in ordered):
        raise ValueError("outcome window is reversed")
    count = 0
    prior_end = -1
    for first, last in ordered:
        if first > prior_end:
            count += 1
            prior_end = last
    return count


def _verified_index(s3: Any, bucket: str, key: str) -> dict[str, Any]:
    audited = audit_capture(s3, bucket=bucket, index_key=key)
    head = s3.head_object(Bucket=bucket, Key=key)
    size = head.get("ContentLength")
    if not isinstance(size, int) or size < 0:
        raise ValueError("archive index size is invalid")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read(size + 1)
    if (len(body) != size
            or head.get("Metadata", {}).get("sha256") != hashlib.sha256(body).hexdigest()):
        raise ValueError("archive index readback hash differs")
    result = json.loads(body)
    if len(result["forecasts"]) != audited["forecast_count"]:
        raise ValueError("archive forecast count differs")
    return result


def audit_evaluation_coverage(s3: Any, *, bucket: str, prefix: str) -> dict[str, Any]:
    """Report distinct prospective origins and disjoint scored label windows."""
    indices = sorted(_listed_indices(s3, bucket=bucket, prefix=prefix))
    if len(indices) > 250:
        raise ValueError("evaluation inventory exceeds the review limit")
    first: dict[str, tuple[str, dict[int, tuple[int, int]]]] = {}
    forecast_indices = 0
    for _, key in indices:
        data = _verified_index(s3, bucket, key)
        if not data["forecasts"]:
            continue
        forecast_indices += 1
        origins = {item["origin_session"] for item in data["forecasts"]}
        if len(origins) != 1:
            raise ValueError("forecast origins differ")
        origin = next(iter(origins))
        origin_day = date.fromisoformat(origin).toordinal()
        pairs = []
        for forecast in data["forecasts"]:
            windows = {item["horizon"]: (
                date.fromisoformat(item["first_outcome_session"]).toordinal(),
                date.fromisoformat(item["last_outcome_session"]).toordinal(),
            ) for item in forecast["horizons"]}
            if set(windows) != {5, 20}:
                raise ValueError("forecast horizons differ")
            if any(start <= origin_day or end < start for start, end in windows.values()):
                raise ValueError("outcome window is invalid")
            pairs.append(windows)
        if len(pairs) != 2 or pairs[0] != pairs[1]:
            raise ValueError("asset outcome windows differ")
        first.setdefault(origin, (key, pairs[0]))

    plan = official_score_plan(s3, bucket=bucket, prefix=prefix)
    matured: dict[int, set[str]] = {5: set(), 20: set()}
    for source, _, horizon in plan:
        matching = [origin for origin, (key, _) in first.items() if key == source]
        if len(matching) != 1 or horizon not in matured or matching[0] in matured[horizon]:
            raise ValueError("official score plan differs from first forecast")
        matured[horizon].add(matching[0])

    horizons = {}
    for horizon, origins in matured.items():
        windows = [first[origin][1][horizon] for origin in origins]
        horizons[str(horizon)] = {
            "scored_origin_count": len(origins),
            "pending_origin_count": len(first) - len(origins),
            "nonoverlapping_origin_count": nonoverlap_count(windows),
        }
    return {"status": "private_evaluation_coverage_verified",
            "audited_index_count": len(indices), "unique_origin_count": len(first),
            "duplicate_forecast_index_count": forecast_indices - len(first),
            "horizons": horizons, "public_performance_allowed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공식 평가 시작일과 비중첩 정답 구간 감사")
    parser.add_argument("--prefix", default="shockgraph-research")
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
        result = audit_evaluation_coverage(client, bucket=bucket, prefix=args.prefix)
    except Exception:
        print(json.dumps({"status": "private_evaluation_coverage_failed"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
