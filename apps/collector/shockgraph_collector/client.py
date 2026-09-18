from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

import httpx
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

PRODUCTION_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
ALLOWED_BASE_URLS = frozenset({PRODUCTION_BASE_URL, DEMO_BASE_URL})
PUBLIC_PATHS = (
    "/events",
    "/markets",
    "/series",
    "/historical",
    "/exchange/status",
    "/exchange/schedule",
    "/exchange/announcements",
)
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must be non-negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")


class KalshiPublicClient:
    def __init__(
        self,
        *,
        base_url: str = PRODUCTION_BASE_URL,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        if normalized_base_url not in ALLOWED_BASE_URLS:
            raise ValueError("base_url must be an approved Kalshi public or demo endpoint")
        self.base_url = normalized_base_url
        self.retry_policy = retry_policy or RetryPolicy()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep or time.sleep
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "shockgraph-ai-collector/0.1"},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/") or "://" in path:
            raise ValueError("path must be a public read endpoint")
        if not any(path == prefix or path.startswith(f"{prefix}/") for prefix in PUBLIC_PATHS):
            raise ValueError("path must be a public read endpoint")

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_path(path)
        delay = self.retry_policy.initial_backoff_seconds

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            response = self._client.get(path, params=dict(params or {}))
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("public API response must be a JSON object")
                return payload
            if attempt == self.retry_policy.max_attempts:
                response.raise_for_status()
            self.sleep(delay)
            delay *= self.retry_policy.multiplier

        raise RuntimeError("unreachable retry state")

    def collect_json(
        self,
        path: str,
        store: ImmutableRawStore,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawArtifact:
        payload = self.get_json(path, params=params)
        return store.save(
            payload,
            source="kalshi",
            endpoint=path,
            request_params=params,
            observed_at=self.clock(),
        )

    def collect_pages(
        self,
        path: str,
        store: ImmutableRawStore,
        *,
        collection_key: str,
        params: Mapping[str, Any] | None = None,
        max_pages: int = 100,
    ) -> tuple[RawArtifact, ...]:
        if not collection_key:
            raise ValueError("collection_key is required")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        base_params = dict(params or {})
        cursor: str | None = None
        seen_cursors: set[str] = set()
        artifacts: list[RawArtifact] = []

        for _ in range(max_pages):
            page_params = dict(base_params)
            if cursor is not None:
                page_params["cursor"] = cursor
            payload = self.get_json(path, params=page_params)
            if not isinstance(payload.get(collection_key), list):
                raise ValueError(f"response field {collection_key!r} must be a list")
            artifacts.append(
                store.save(
                    payload,
                    source="kalshi",
                    endpoint=path,
                    request_params=page_params,
                    observed_at=self.clock(),
                )
            )

            next_cursor = payload.get("cursor", "")
            if not isinstance(next_cursor, str):
                raise ValueError("response cursor must be a string")
            if not next_cursor:
                return tuple(artifacts)
            if next_cursor in seen_cursors:
                raise ValueError("response cursor repeated; refusing an infinite pagination loop")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise RuntimeError(f"pagination exceeded max_pages={max_pages}")
