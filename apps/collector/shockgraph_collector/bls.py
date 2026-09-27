from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

from shockgraph_collector.client import RETRYABLE_STATUS_CODES, RetryPolicy

BLS_BASE_URL = "https://www.bls.gov"
BLS_CPI_ARCHIVE_INDEX = "/bls/news-release/cpi.htm"
_ARCHIVE_PATH = re.compile(r"^/news\.release/archives/cpi_\d{8}\.htm$")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = next((value for key, value in attrs if key.lower() == "href"), None)
        if href:
            self.links.append(href)


def archive_release_paths(html: str) -> tuple[str, ...]:
    parser = _LinkParser()
    parser.feed(html)
    paths: set[str] = set()
    for link in parser.links:
        parsed = urlparse(link)
        if (parsed.scheme or parsed.netloc) and (
            parsed.scheme != "https" or parsed.netloc.lower() != "www.bls.gov"
        ):
            continue
        if _ARCHIVE_PATH.fullmatch(parsed.path):
            paths.add(parsed.path)
    return tuple(sorted(paths))


def archive_path_for_reference(reference_month: date, paths: tuple[str, ...]) -> str:
    if reference_month.day != 1:
        raise ValueError("reference month must use its first day")
    release_year = reference_month.year + (reference_month.month == 12)
    release_month = 1 if reference_month.month == 12 else reference_month.month + 1
    candidates = []
    for path in paths:
        match = _ARCHIVE_PATH.fullmatch(path)
        if match is None:
            continue
        released = datetime.strptime(
            path.removeprefix("/news.release/archives/cpi_").removesuffix(".htm"), "%m%d%Y"
        )
        if released.year == release_year and released.month == release_month:
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError("expected exactly one BLS CPI release in the following month")
    return candidates[0]


class BlsPublicClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep or time.sleep
        self._client = httpx.Client(
            base_url=BLS_BASE_URL,
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "shockgraph-ai-research/0.1"},
        )

    def __enter__(self) -> BlsPublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _validate_path(path: str) -> None:
        if path == BLS_CPI_ARCHIVE_INDEX or _ARCHIVE_PATH.fullmatch(path):
            return
        raise ValueError("path must be the public BLS CPI archive index or release")

    def get_text(self, path: str) -> str:
        self._validate_path(path)
        delay = self.retry_policy.initial_backoff_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            response = self._client.get(path)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    raise ValueError("BLS archive response must be HTML")
                return response.text
            if attempt == self.retry_policy.max_attempts:
                response.raise_for_status()
            self.sleep(delay)
            delay *= self.retry_policy.multiplier
        raise RuntimeError("unreachable retry state")

    def collect_text(self, path: str, store: ImmutableRawStore) -> RawArtifact:
        text = self.get_text(path)
        return store.save(
            {"source_url": f"{BLS_BASE_URL}{path}", "text": text},
            source="bls",
            endpoint=path,
            observed_at=self.clock(),
        )
