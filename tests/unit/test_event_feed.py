from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shockgraph_domain.event_feed import OfficialEvent, WatchedAsset, build_event_feed

RELEASE = datetime(2026, 10, 28, 18, 0, tzinfo=UTC)


def _event() -> OfficialEvent:
    return OfficialEvent(
        source="federal-reserve",
        event_id="fomc-2026-10",
        title="FOMC",
        scheduled_at=RELEASE,
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        related_symbols=("QQQ", "SPY"),
        released_at=RELEASE,
        available_at=RELEASE + timedelta(minutes=2),
        release_url="https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm",
    )


def test_feed_only_includes_explicitly_related_watched_assets() -> None:
    cards = build_event_feed(
        [WatchedAsset(" qqq "), WatchedAsset("TLT")], [_event()], as_of=RELEASE
    )

    assert len(cards) == 1
    assert cards[0].matched_symbols == ("QQQ",)
    assert build_event_feed([WatchedAsset("NVDA")], [_event()], as_of=RELEASE) == ()


def test_unavailable_release_is_not_exposed_until_first_usable_time() -> None:
    before = build_event_feed(
        [WatchedAsset("QQQ")], [_event()], as_of=RELEASE + timedelta(minutes=1)
    )[0]
    after = build_event_feed(
        [WatchedAsset("QQQ")], [_event()], as_of=RELEASE + timedelta(minutes=2)
    )[0]

    assert (before.status, before.released_at, before.release_url) == ("scheduled", None, None)
    assert (after.status, after.available_at, after.release_url) == (
        "published", RELEASE + timedelta(minutes=2), _event().release_url
    )


def test_invalid_event_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="available before publication"):
        OfficialEvent(
            source="fed", event_id="fomc", title="FOMC", scheduled_at=RELEASE,
            source_url="https://www.federalreserve.gov/", related_symbols=("QQQ",),
            released_at=RELEASE, available_at=RELEASE - timedelta(seconds=1),
            release_url="https://www.federalreserve.gov/release",
        )


def test_duplicate_source_identity_and_naive_query_time_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_event_feed([WatchedAsset("QQQ")], [_event(), _event()], as_of=RELEASE)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_event_feed([WatchedAsset("QQQ")], [_event()], as_of=RELEASE.replace(tzinfo=None))
