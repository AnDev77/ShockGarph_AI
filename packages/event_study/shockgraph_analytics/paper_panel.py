from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASSETS = ("SPY", "TLT", "GLD")
MONTHS = {
    name: number
    for number, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        start=1,
    )
}
MONTH_NAMES = {number: name.title() for name, number in MONTHS.items()}
TICKER_PATTERN = re.compile(r"^(?:KX)?CPI-(?P<year>\d{2})(?P<month>[A-Z]{3})$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def _visible_text(html: str) -> str:
    parser = _VisibleText()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def event_reference_month(event_ticker: str) -> date:
    match = TICKER_PATTERN.fullmatch(event_ticker)
    if match is None or match["month"] not in MONTHS:
        raise ValueError("require a CPI event ticker")
    return date(2000 + int(match["year"]), MONTHS[match["month"]], 1)


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def utc_only(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


class CpiReleaseVintage(_Record):
    event_id: Annotated[str, Field(pattern=r"^cpi-\d{4}-\d{2}$")]
    event_ticker: Annotated[str, Field(pattern=r"^(?:KX)?CPI-\d{2}[A-Z]{3}$")]
    reference_month: date
    release_at: datetime
    actual_mom_first: Annotated[float, Field(allow_inf_nan=False)]
    threshold: Annotated[float, Field(allow_inf_nan=False)] = 0.3
    outcome: Literal["yes", "no"]
    source_url: str
    raw_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def consistency(self) -> Self:
        if self.reference_month.day != 1:
            raise ValueError("reference month must use its first day")
        if event_reference_month(self.event_ticker) != self.reference_month:
            raise ValueError("event ticker and reference month differ")
        if self.event_id != f"cpi-{self.reference_month:%Y-%m}":
            raise ValueError("event id and reference month differ")
        next_month = (
            date(self.reference_month.year + 1, 1, 1)
            if self.reference_month.month == 12
            else date(self.reference_month.year, self.reference_month.month + 1, 1)
        )
        if not next_month <= self.release_at.date() <= next_month + timedelta(days=45):
            raise ValueError("release date must follow the reference month")
        if not math.isclose(self.threshold, 0.3, abs_tol=1e-12):
            raise ValueError("paper dataset requires the fixed 0.3 threshold")
        expected = "yes" if self.actual_mom_first > self.threshold else "no"
        if self.outcome != expected:
            raise ValueError("outcome must follow the strict threshold rule")
        if not self.source_url.startswith("https://www.bls.gov/news.release/archives/cpi_"):
            raise ValueError("source URL must be an official archived CPI release")
        return self


def parse_bls_cpi_release(
    html: str,
    *,
    event_ticker: str,
    source_url: str,
    raw_hash: str,
) -> CpiReleaseVintage:
    if not HASH_PATTERN.fullmatch(raw_hash):
        raise ValueError("raw hash must be a SHA-256 hex digest")
    text = _visible_text(html)
    title = re.search(
        r"CONSUMER PRICE INDEX[^A-Z0-9]+(?P<month>[A-Z]+)\s+(?P<year>\d{4})",
        text,
    )
    if title is None:
        raise ValueError("CPI reference month was not found")
    month_name = title["month"].title()
    try:
        month = datetime.strptime(month_name, "%B").month
    except ValueError as error:
        raise ValueError("invalid CPI reference month") from error
    reference_month = date(int(title["year"]), month, 1)
    if event_reference_month(event_ticker) != reference_month:
        raise ValueError("BLS reference month does not match the event ticker")

    embargo = re.search(
        r"embargoed until\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})\s+"
        r"(?P<ampm>[ap])\.m\.\s+\(ET\)\s+(?:\w+,\s+)?"
        r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if embargo is None:
        raise ValueError("BLS release time was not found")
    release_date = datetime.strptime(embargo["date"], "%B %d, %Y").date()
    hour = int(embargo["hour"]) % 12 + (12 if embargo["ampm"].lower() == "p" else 0)
    release_at = datetime.combine(
        release_date,
        datetime.min.time().replace(hour=hour, minute=int(embargo["minute"])),
        tzinfo=ZoneInfo("America/New_York"),
    ).astimezone(UTC)

    first_summary = re.search(
        r"The Consumer Price Index for All Urban Consumers \(CPI-U\)(?P<body>.{0,300})",
        text,
        flags=re.IGNORECASE,
    )
    if first_summary is None:
        raise ValueError("first-release all-items summary was not found")
    if re.search(
        r"The Consumer Price Index for All Urban Consumers \(CPI-U\).{0,200}?"
        r"over the\s+\d+\s+months",
        text,
        flags=re.IGNORECASE,
    ):
        raise ValueError("release does not contain a one-month CPI change")
    change = re.search(
        r"The Consumer Price Index for All Urban Consumers \(CPI-U\)\s+"
        r"(?P<verb>increased|rose|decreased|declined)\s+"
        r"(?P<value>\d+(?:\.\d+)?)\s+percent\b",
        text,
        flags=re.IGNORECASE,
    )
    unchanged = re.search(
        r"The Consumer Price Index for All Urban Consumers \(CPI-U\)\s+was unchanged\b",
        text,
        flags=re.IGNORECASE,
    )
    if change is None and unchanged is None:
        raise ValueError("first-release all-items monthly change was not found")
    if unchanged is not None:
        actual = 0.0
    else:
        assert change is not None
        actual = float(change["value"])
        if change["verb"].lower() in {"decreased", "declined"}:
            actual = -actual
    outcome: Literal["yes", "no"] = "yes" if actual > 0.3 else "no"
    return CpiReleaseVintage(
        event_id=f"cpi-{reference_month:%Y-%m}",
        event_ticker=event_ticker,
        reference_month=reference_month,
        release_at=release_at,
        actual_mom_first=actual,
        threshold=0.3,
        outcome=outcome,
        source_url=source_url,
        raw_hash=raw_hash,
    )


class AssetMinuteBar(_Record):
    asset_id: Literal["SPY", "TLT", "GLD"]
    price_at: datetime
    available_at: datetime
    open: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    high: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    low: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    close: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    volume: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    extended_hours: bool
    raw_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def consistency(self) -> Self:
        if self.price_at.second or self.price_at.microsecond:
            raise ValueError("price time must be minute-aligned")
        if self.available_at < self.price_at:
            raise ValueError("bar cannot be available before its price time")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high
        ):
            raise ValueError("OHLC bounds are inconsistent")
        return self


class AssetWindow(_Record):
    event_id: str
    asset_id: Literal["SPY", "TLT", "GLD"]
    horizon: str
    start_at: datetime
    end_at: datetime
    start_price: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    end_price: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    return_value: Annotated[float, Field(allow_inf_nan=False)]
    start_raw_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    end_raw_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@dataclass(frozen=True)
class AssetWindowResult:
    windows: tuple[AssetWindow, ...]
    coverage: tuple[dict[str, str], ...]
    common_event_ids: tuple[str, ...]


class EventAssetPanelRow(_Record):
    event_id: str
    event_ticker: str
    reference_month: date
    release_at: datetime
    actual_mom_first: Annotated[float, Field(allow_inf_nan=False)]
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    outcome: Literal["yes", "no"]
    market_ticker: str
    quote_end_at: datetime
    probability_yes: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    spread: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    asset_id: Literal["SPY", "TLT", "GLD"]
    horizon: str
    start_at: datetime
    end_at: datetime
    start_price: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    end_price: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    return_value: Annotated[float, Field(allow_inf_nan=False)]

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if not self.quote_end_at < self.release_at:
            raise ValueError("probability quote must be before release")
        if not self.start_at < self.release_at < self.end_at:
            raise ValueError("asset window must surround the release")
        return self


@dataclass(frozen=True)
class EventAssetPanelResult:
    rows: tuple[EventAssetPanelRow, ...]
    coverage: tuple[dict[str, str], ...]
    common_event_ids: tuple[str, ...]


def build_asset_windows(
    releases: list[CpiReleaseVintage],
    bars: list[AssetMinuteBar],
    *,
    horizons: dict[str, timedelta] | None = None,
) -> AssetWindowResult:
    selected_horizons = horizons or {"m5": timedelta(minutes=5), "m30": timedelta(minutes=30)}
    if not selected_horizons or any(
        not name or delta <= timedelta(0) for name, delta in selected_horizons.items()
    ):
        raise ValueError("horizons must be named positive durations")
    bar_keys = {(bar.asset_id, bar.price_at) for bar in bars}
    if len(bar_keys) != len(bars):
        raise ValueError("duplicate asset minute bar")
    by_key = {(bar.asset_id, bar.price_at): bar for bar in bars}
    windows: list[AssetWindow] = []
    coverage: list[dict[str, str]] = []
    completed: set[tuple[str, str, str]] = set()
    for release in sorted(releases, key=lambda row: (row.release_at, row.event_id)):
        start_at = release.release_at - timedelta(minutes=1)
        for horizon, delta in selected_horizons.items():
            end_at = release.release_at + delta
            for asset in ASSETS:
                start = by_key.get((asset, start_at))
                end = by_key.get((asset, end_at))
                if start is None or end is None:
                    coverage.append(
                        {
                            "event_id": release.event_id,
                            "asset_id": asset,
                            "horizon": horizon,
                            "status": "missing_start_bar" if start is None else "missing_end_bar",
                        }
                    )
                    continue
                if not start.extended_hours or not end.extended_hours:
                    coverage.append(
                        {
                            "event_id": release.event_id,
                            "asset_id": asset,
                            "horizon": horizon,
                            "status": "not_extended_hours",
                        }
                    )
                    continue
                windows.append(
                    AssetWindow(
                        event_id=release.event_id,
                        asset_id=asset,
                        horizon=horizon,
                        start_at=start_at,
                        end_at=end_at,
                        start_price=start.close,
                        end_price=end.close,
                        return_value=end.close / start.close - 1,
                        start_raw_hash=start.raw_hash,
                        end_raw_hash=end.raw_hash,
                    )
                )
                completed.add((release.event_id, asset, horizon))
    common = tuple(
        release.event_id
        for release in sorted(releases, key=lambda row: (row.release_at, row.event_id))
        if all(
            (release.event_id, asset, horizon) in completed
            for asset in ASSETS
            for horizon in selected_horizons
        )
    )
    return AssetWindowResult(tuple(windows), tuple(coverage), common)


def assemble_event_asset_panel(
    probability_events: list[dict[str, Any]],
    releases: list[CpiReleaseVintage],
    window_result: AssetWindowResult,
) -> EventAssetPanelResult:
    probability_by_ticker: dict[str, dict[str, Any]] = {}
    for event in probability_events:
        ticker = event.get("event_ticker")
        if not isinstance(ticker, str) or ticker in probability_by_ticker:
            raise ValueError("probability event tickers must be unique strings")
        probability_by_ticker[ticker] = event
    release_by_id = {release.event_id: release for release in releases}
    if len(release_by_id) != len(releases):
        raise ValueError("release event ids must be unique")

    coverage = list(window_result.coverage)
    eligible_event_ids: set[str] = set()
    for release in releases:
        probability = probability_by_ticker.get(release.event_ticker)
        if probability is None or probability.get("status") != "eligible":
            coverage.append(
                {
                    "event_id": release.event_id,
                    "asset_id": "ALL",
                    "horizon": "ALL",
                    "status": "probability_not_eligible",
                }
            )
            continue
        if probability.get("outcome") not in (None, "", release.outcome):
            raise ValueError("probability and BLS outcomes differ")
        eligible_event_ids.add(release.event_id)

    common = tuple(
        event_id for event_id in window_result.common_event_ids if event_id in eligible_event_ids
    )
    common_set = set(common)
    rows: list[EventAssetPanelRow] = []
    for window in window_result.windows:
        if window.event_id not in common_set:
            continue
        release = release_by_id[window.event_id]
        probability = probability_by_ticker[release.event_ticker]
        quote_value = probability.get("quote_end_at")
        if not isinstance(quote_value, str):
            raise ValueError("eligible probability requires quote_end_at")
        quote_end_at = datetime.fromisoformat(quote_value.replace("Z", "+00:00"))
        rows.append(
            EventAssetPanelRow(
                event_id=release.event_id,
                event_ticker=release.event_ticker,
                reference_month=release.reference_month,
                release_at=release.release_at,
                actual_mom_first=release.actual_mom_first,
                threshold=release.threshold,
                outcome=release.outcome,
                market_ticker=str(probability.get("market_ticker", "")),
                quote_end_at=quote_end_at,
                probability_yes=float(probability["probability_yes"]),
                spread=float(probability["spread"]),
                asset_id=window.asset_id,
                horizon=window.horizon,
                start_at=window.start_at,
                end_at=window.end_at,
                start_price=window.start_price,
                end_price=window.end_price,
                return_value=window.return_value,
            )
        )
    return EventAssetPanelResult(tuple(rows), tuple(coverage), common)
