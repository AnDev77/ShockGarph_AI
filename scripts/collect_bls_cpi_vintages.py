from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/collector"),
    str(ROOT / "packages/data_pipeline"),
    str(ROOT / "packages/event_study"),
]

from audit_kalshi_cpi import score_event_probabilities  # noqa: E402
from shockgraph_analytics.paper_panel import (  # noqa: E402
    CpiReleaseVintage,
    event_reference_month,
    parse_bls_cpi_release,
)
from shockgraph_collector.bls import (  # noqa: E402
    BLS_BASE_URL,
    BLS_CPI_ARCHIVE_INDEX,
    BlsPublicClient,
    archive_path_for_reference,
    archive_release_paths,
)
from shockgraph_collector.client import RetryPolicy  # noqa: E402
from shockgraph_data_pipeline.raw_store import ImmutableRawStore  # noqa: E402

SCHEMA_VERSION = "cpi-release-vintage-v1"
CSV_FIELDS = (
    "event_id",
    "event_ticker",
    "reference_month",
    "release_at",
    "actual_mom_first",
    "threshold",
    "bls_outcome",
    "kalshi_outcome",
    "outcome_match",
    "source_url",
    "raw_hash",
)


def reconcile_probability_events(
    events: list[dict[str, Any]], validated_outcomes: dict[str, str]
) -> list[dict[str, Any]]:
    reconciled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        ticker = event.get("event_ticker")
        if not isinstance(ticker, str):
            raise ValueError("audit event ticker is required")
        if ticker in seen:
            raise ValueError("duplicate audit event")
        seen.add(ticker)
        if ticker not in validated_outcomes:
            continue
        outcome = validated_outcomes[ticker]
        if outcome not in ("yes", "no"):
            raise ValueError("validated outcome must be yes or no")
        if event.get("outcome") != outcome:
            raise ValueError("Kalshi and BLS outcome mismatch")
        reconciled.append({**event, "outcome": outcome})
    return reconciled


def _load_audit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("series_ticker") != "KXCPI":
        raise ValueError("input must be a KXCPI audit report")
    events = payload.get("events")
    if not isinstance(events, list) or not all(isinstance(row, dict) for row in events):
        raise ValueError("audit events must be an object list")
    return payload


def collect_vintages(
    client: BlsPublicClient,
    store: ImmutableRawStore,
    audit: dict[str, Any],
    *,
    request_interval_seconds: float = 0.2,
) -> dict[str, Any]:
    if request_interval_seconds < 0:
        raise ValueError("request interval must be nonnegative")
    index_html = client.get_text(BLS_CPI_ARCHIVE_INDEX)
    store.save(
        {"source_url": f"{BLS_BASE_URL}{BLS_CPI_ARCHIVE_INDEX}", "text": index_html},
        source="bls",
        endpoint=BLS_CPI_ARCHIVE_INDEX,
        observed_at=client.clock(),
    )
    archive_paths = archive_release_paths(index_html)
    releases: list[CpiReleaseVintage] = []
    coverage: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    for event in audit["events"]:
        event_ticker = event.get("event_ticker")
        kalshi_outcome = event.get("outcome")
        if not isinstance(event_ticker, str) or kalshi_outcome not in ("yes", "no"):
            raise ValueError("audit event identity and outcome are required")
        if event_ticker in seen_events:
            raise ValueError("duplicate audit event")
        seen_events.add(event_ticker)
        reference_month = event_reference_month(event_ticker)
        row: dict[str, Any] = {
            "event_ticker": event_ticker,
            "reference_month": reference_month.isoformat(),
            "kalshi_outcome": kalshi_outcome,
        }
        try:
            path = archive_path_for_reference(reference_month, archive_paths)
            html = client.get_text(path)
            artifact = store.save(
                {"source_url": f"{BLS_BASE_URL}{path}", "text": html},
                source="bls",
                endpoint=path,
                observed_at=client.clock(),
            )
            release = parse_bls_cpi_release(
                html,
                event_ticker=event_ticker,
                source_url=f"{BLS_BASE_URL}{path}",
                raw_hash=artifact.payload_sha256,
            )
            releases.append(release)
            row.update(
                status="matched" if release.outcome == kalshi_outcome else "outcome_mismatch",
                bls_outcome=release.outcome,
                actual_mom_first=release.actual_mom_first,
                release_at=release.release_at.isoformat(),
            )
        except (httpx.HTTPError, ValueError) as error:
            row.update(
                status="access_error" if isinstance(error, httpx.HTTPError) else "invalid_release",
                error_type=type(error).__name__,
                error_message=str(error),
            )
        coverage.append(row)
        time.sleep(request_interval_seconds)
    status_counts = {
        status: sum(row["status"] == status for row in coverage)
        for status in ("matched", "outcome_mismatch", "invalid_release", "access_error")
    }
    validated_outcomes = {release.event_ticker: release.outcome for release in releases}
    reconciled_events = reconcile_probability_events(audit["events"], validated_outcomes)
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "source_audit_schema": audit.get("schema_version"),
        "source_audit_checked_at": audit.get("checked_at"),
        "requested_events": len(coverage),
        "parsed_releases": len(releases),
        "status_counts": status_counts,
        "reconciled_probability_comparison": score_event_probabilities(reconciled_events),
        "releases": [release.model_dump(mode="json") for release in releases],
        "coverage": coverage,
    }


def save_vintage_dataset(report: dict[str, Any], output_dir: Path) -> Path:
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    run_id = hashlib.sha256(content.encode()).hexdigest()
    destination = output_dir / run_id
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "report.json"
    if report_path.exists() and report_path.read_text(encoding="utf-8") != content:
        raise ValueError("existing release report differs from its content address")
    report_path.write_text(content, encoding="utf-8")

    kalshi_by_ticker = {row["event_ticker"]: row["kalshi_outcome"] for row in report["coverage"]}
    rows = []
    for release in report["releases"]:
        kalshi_outcome = kalshi_by_ticker[release["event_ticker"]]
        rows.append(
            {
                "event_id": release["event_id"],
                "event_ticker": release["event_ticker"],
                "reference_month": release["reference_month"],
                "release_at": release["release_at"],
                "actual_mom_first": release["actual_mom_first"],
                "threshold": release["threshold"],
                "bls_outcome": release["outcome"],
                "kalshi_outcome": kalshi_outcome,
                "outcome_match": release["outcome"] == kalshi_outcome,
                "source_url": release["source_url"],
                "raw_hash": release["raw_hash"],
            }
        )
    buffer = io.StringIO(newline="")
    fields: list[str] = list(CSV_FIELDS)
    writer: csv.DictWriter[str] = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_content = buffer.getvalue()
    csv_path = destination / "release_vintage.csv"
    if csv_path.exists() and csv_path.read_text(encoding="utf-8") != csv_content:
        raise ValueError("existing release CSV differs from its content address")
    csv_path.write_text(csv_content, encoding="utf-8")

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "report_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "release_csv_sha256": hashlib.sha256(csv_content.encode()).hexdigest(),
        "requested_events": report["requested_events"],
        "parsed_releases": report["parsed_releases"],
        "status_counts": report["status_counts"],
        "reconciled_probability_comparison": report["reconciled_probability_comparison"],
        "publication_status": "bls_source_links_and_derived_values_reviewed_separately",
    }
    metadata_content = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    metadata_path = destination / "metadata.json"
    if metadata_path.exists() and metadata_path.read_text(encoding="utf-8") != metadata_content:
        raise ValueError("existing metadata differs from its content address")
    metadata_path.write_text(metadata_content, encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="BLS 최초 CPI 발표 빈티지와 Kalshi 사건 매핑")
    parser.add_argument("--input-audit", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "artifacts/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/bls-cpi-vintages")
    parser.add_argument("--request-interval", type=float, default=0.2)
    args = parser.parse_args()
    audit = _load_audit(args.input_audit)
    with BlsPublicClient(
        timeout_seconds=30,
        retry_policy=RetryPolicy(max_attempts=4, initial_backoff_seconds=1),
    ) as client:
        report = collect_vintages(
            client,
            ImmutableRawStore(args.raw_dir),
            audit,
            request_interval_seconds=args.request_interval,
        )
    destination = save_vintage_dataset(report, args.output)
    print(
        json.dumps(
            {
                "release_dataset": str(destination),
                "requested_events": report["requested_events"],
                "parsed_releases": report["parsed_releases"],
                "status_counts": report["status_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
