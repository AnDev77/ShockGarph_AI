"""Archive the Treasury's public daily par-yield XML without inventing release times."""

from __future__ import annotations

import base64
import hashlib
import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Self
from zoneinfo import ZoneInfo

import httpx
from shockgraph_data_pipeline.raw_store import ImmutableRawStore, RawArtifact

TREASURY_URL = "https://home.treasury.gov"
TREASURY_PATH = "/resource-center/data-chart-center/interest-rates/pages/xml"
ATOM_NS = "http://www.w3.org/2005/Atom"
EDM_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices"
EASTERN = ZoneInfo("America/New_York")
MAX_RESPONSE_BYTES = 4_000_000


@dataclass(frozen=True, slots=True)
class TreasuryTenYearRate:
    observation_date: date
    value_percent: float
    captured_at: datetime
    raw_file_sha256: str


@dataclass(frozen=True, slots=True)
class TreasuryMonthlyCapture:
    captured_at: datetime
    observations: tuple[TreasuryTenYearRate, ...]
    raw_file_sha256: str
    raw_artifact: RawArtifact


def _parse_rates(contents: bytes, year: int, month: int, captured_at: datetime,
                 digest: str) -> tuple[TreasuryTenYearRate, ...]:
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as error:
        raise ValueError("Treasury feed must be valid XML") from error
    if root.tag != f"{{{ATOM_NS}}}feed":
        raise ValueError("Treasury response is not an Atom feed")
    rows = []
    seen: set[date] = set()
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        date_element = entry.find(f".//{{{EDM_NS}}}NEW_DATE")
        value_element = entry.find(f".//{{{EDM_NS}}}BC_10YEAR")
        if date_element is None or not date_element.text:
            raise ValueError("Treasury entry is missing NEW_DATE")
        try:
            observation_date = date.fromisoformat(date_element.text[:10])
        except ValueError as error:
            raise ValueError("Treasury observation date is invalid") from error
        if (observation_date.year, observation_date.month) != (year, month):
            raise ValueError("Treasury entry is outside the requested month")
        if observation_date > captured_at.astimezone(EASTERN).date():
            raise ValueError("Treasury entry is later than the local capture date")
        if observation_date in seen:
            raise ValueError("Treasury feed contains a duplicate observation date")
        seen.add(observation_date)
        if value_element is None or value_element.text is None or not value_element.text.strip():
            continue  # A missing tenor is missing data, never a zero rate.
        try:
            value = float(value_element.text)
        except ValueError as error:
            raise ValueError("Treasury 10-year yield is invalid") from error
        if not math.isfinite(value) or value < 0:
            raise ValueError("Treasury 10-year yield must be finite and nonnegative")
        rows.append(TreasuryTenYearRate(observation_date, value, captured_at, digest))
    if not rows:
        raise ValueError("Treasury response contains no 10-year yields")
    return tuple(sorted(rows, key=lambda row: row.observation_date))


class TreasuryYieldCollector:
    def __init__(
        self, *, transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self._client = httpx.Client(
            base_url=TREASURY_URL, transport=transport, timeout=20.0,
            follow_redirects=False, headers={"User-Agent": "shockgraph-ai-collector/0.1"},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def collect_month(
        self, year: int, month: int, store: ImmutableRawStore,
    ) -> TreasuryMonthlyCapture:
        if year < 1990 or not 1 <= month <= 12:
            raise ValueError("month must be within the Treasury par-yield feed range")
        params = {"data": "daily_treasury_yield_curve",
                  "field_tdr_date_value_month": f"{year:04d}{month:02d}"}
        response = self._client.get(TREASURY_PATH, params=params)
        if response.status_code != 200:
            raise ValueError(f"Treasury feed returned HTTP {response.status_code}")
        contents = response.content
        captured_at = self.clock()  # Set after the full response has been received.
        if captured_at.tzinfo is None or captured_at.utcoffset() != UTC.utcoffset(None):
            raise ValueError("collector clock must return UTC")
        if len(contents) > MAX_RESPONSE_BYTES:
            raise ValueError("Treasury response exceeds the monthly size limit")
        content_type = response.headers.get("content-type", "").lower()
        if "xml" not in content_type:
            raise ValueError("Treasury response does not have an XML content type")
        digest = hashlib.sha256(contents).hexdigest()
        raw = store.save(
            {"format": "application/xml", "body_base64": base64.b64encode(contents).decode("ascii"),
             "file_sha256": digest},
            source="us-treasury", endpoint=TREASURY_PATH,
            request_params=params, observed_at=captured_at,
        )
        rates = _parse_rates(contents, year, month, captured_at, digest)
        return TreasuryMonthlyCapture(captured_at, rates, digest, raw)
