from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx
from shockgraph_collector.bls import (
    BlsPublicClient,
    archive_path_for_reference,
    archive_release_paths,
)
from shockgraph_data_pipeline.raw_store import ImmutableRawStore


def test_bls_client_collects_public_archive_without_auth(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text='<a href="/news.release/archives/cpi_03112026.htm">March</a>',
            headers={"content-type": "text/html; charset=utf-8"},
        )

    with BlsPublicClient(
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 9, 26, 12, tzinfo=UTC),
    ) as client:
        artifact = client.collect_text(
            "/bls/news-release/cpi.htm",
            ImmutableRawStore(tmp_path),
        )

    assert requests[0].method == "GET"
    assert "authorization" not in requests[0].headers
    envelope = json.loads(artifact.path.read_text(encoding="utf-8"))
    assert envelope["payload"]["text"].startswith("<a href=")


def test_archive_paths_are_deduplicated_and_reject_external_links() -> None:
    html = """
    <a href="/news.release/archives/cpi_03112026.htm">valid</a>
    <a href="https://www.bls.gov/news.release/archives/cpi_03112026.htm">duplicate</a>
    <a href="https://example.com/news.release/archives/cpi_02132026.htm">external</a>
    <a href="/news.release/archives/empsit_03112026.htm">other release</a>
    """
    assert archive_release_paths(html) == ("/news.release/archives/cpi_03112026.htm",)


def test_archive_path_uses_release_month_after_reference_month() -> None:
    paths = (
        "/news.release/archives/cpi_01142026.htm",
        "/news.release/archives/cpi_02132026.htm",
        "/news.release/archives/cpi_03112026.htm",
        "/news.release/archives/cpi_04102026.htm",
    )
    assert archive_path_for_reference(date(2026, 2, 1), paths) == paths[2]
    assert archive_path_for_reference(date(2025, 12, 1), paths) == paths[0]
