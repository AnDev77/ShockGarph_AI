from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from probe_cpi_coverage import inventory  # noqa: E402
from shockgraph_collector.client import KalshiPublicClient  # noqa: E402


def test_research_cli_replays_identically_and_preserves_input(tmp_path) -> None:
    source = ROOT / "data/fixtures/analytics/synthetic_cpi.json"
    before = source.read_bytes()
    command = [
        sys.executable,
        str(ROOT / "scripts/run_event_research.py"),
        "--input",
        str(source),
        "--output",
        str(tmp_path),
        "--min-train",
        "4",
    ]
    first = json.loads(subprocess.check_output(command, text=True))
    second = json.loads(subprocess.check_output(command, text=True))
    assert first == second
    report = json.loads(Path(first["report"]).read_text())
    assert report["status"] == "synthetic_only"
    assert report["evaluated_events"] == 8
    assert report["promotion_status"] == "not_evaluated"
    assert source.read_bytes() == before
    assert len(list(tmp_path.rglob("report.json"))) == 1


def test_inventory_deduplicates_and_marks_page_limit_partial() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("cursor"))
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "markets": [
                    {"ticker": "CPI-contract", "event_ticker": "KXCPI-TEST", "result": "yes"}
                ],
                "cursor": "next" if not request.url.params.get("cursor") else "",
            },
        )

    with KalshiPublicClient(transport=httpx.MockTransport(handler)) as client:
        partial = inventory(client, "/historical/markets", max_pages=1)
        complete = inventory(client, "/historical/markets", max_pages=2)
    assert partial["status"] == "partial"
    assert complete["complete"]
    assert complete["observed_resolved_events"] == 1
    assert complete["observed_contracts"] == 1
    assert seen == [None, None, "next"]


def test_inventory_rejects_repeated_cursor() -> None:
    with (
        KalshiPublicClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"markets": [], "cursor": "repeat"})
            )
        ) as client,
        pytest.raises(ValueError, match="repeated cursor"),
    ):
        inventory(client, "/markets", max_pages=3)
