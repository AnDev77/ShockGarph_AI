from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from shockgraph_collector.treasury_rates import TreasuryYieldCollector
from shockgraph_data_pipeline.market_calendar import nasdaq_2026_sessions, nasdaq_sessions
from shockgraph_data_pipeline.raw_store import ImmutableRawStore
from shockgraph_risk.daily import VolatilityForecast
from shockgraph_risk.macro_panel import build_macro_risk_panel

from scripts.evaluate_snapshot_holdout import main
from scripts.evaluate_traditional_holdout import load_indicators
from scripts.evaluate_traditional_holdout import main as traditional_main


def _manifest(tmp_path: Path) -> Path:
    sessions = nasdaq_2026_sessions(date(2026, 1, 5), date(2026, 1, 30))[:12]
    entries = []
    for end, session in enumerate(sessions):
        name = f"capture-{end}.csv"
        content = "session_date,observed_at,available_at,close,adjusted_close,volume\n"
        for index, prior in enumerate(sessions[: end + 1]):
            content += (
                f"{prior.session_date},{prior.close_at.isoformat()},"
                f"{(prior.close_at + timedelta(minutes=2)).isoformat()},"
                f"{100 + index},{100 + index},\n"
            )
        (tmp_path / name).write_text(content, encoding="utf-8")
        entries.append({
            "path": name, "end": session.session_date.isoformat(),
            "captured_at": (session.close_at + timedelta(minutes=5)).isoformat(),
        })
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1, "source": "synthetic", "start": str(sessions[0].session_date),
        "end": str(sessions[-1].session_date), "holdout_start": str(sessions[5].session_date),
        "evaluation_at": (sessions[-1].close_at + timedelta(minutes=10)).isoformat(),
        "prediction_delay_minutes": 10,
        "snapshots": entries,
    }), encoding="utf-8")
    return manifest


def test_cli_retains_raw_files_and_reports_provenance_without_private_paths(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    output = tmp_path / "report.json"
    arguments = ["--manifest", str(manifest), "--raw-root", str(tmp_path / "raw"),
                 "--output", str(output)]
    assert main(arguments) == 0
    first = output.read_text(encoding="utf-8")
    parsed = json.loads(first)
    assert parsed["report"]["snapshot_count"] == 12
    assert parsed["report"]["horizons"][0]["status"] == "blocked"
    assert parsed["report"]["horizons"][0]["labeled_holdout_count"] == 2
    assert parsed["report"]["horizons"][1]["reason"] == "insufficient_nonoverlapping_windows"
    assert parsed["report"]["public_performance_allowed"] is False
    assert len(parsed["snapshot_provenance"]) == 12
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 12
    assert str(tmp_path) not in first

    # Existing output is protected from replacement. A second report from the same
    # immutable inputs can be regenerated elsewhere with identical bytes.
    assert main(arguments) == 2
    second = tmp_path / "again.json"
    assert main([*arguments[:-1], str(second)]) == 0
    assert second.read_text(encoding="utf-8") == first


def test_cli_fails_closed_on_missing_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "capture-8.csv").write_text(
        (tmp_path / "capture-8.csv").read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    assert main(["--manifest", str(manifest), "--raw-root", str(tmp_path / "raw")]) == 2
    # The invalid import does not claim scores or emit proprietary local paths.
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid_input"
    assert "incomplete or invalid calendar coverage" in result["reason"]
    assert str(tmp_path) not in result["reason"]


def test_traditional_cli_uses_private_indicator_csv_and_blocks_too_short_holdout(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    indicators = tmp_path / "indicators.csv"
    lines = ["name,source,observed_at,available_at,value"]
    for index, item in enumerate(data["snapshots"]):
        captured = datetime.fromisoformat(item["captured_at"])
        lines.append(
            f"DGS10,synthetic,{(captured - timedelta(minutes=5)).isoformat()},"
            f"{(captured - timedelta(minutes=2)).isoformat()},{3 + index / 100}"
        )
    indicators.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "traditional.json"
    args = ["--manifest", str(manifest), "--indicators", str(indicators),
            "--raw-root", str(tmp_path / "raw"), "--output", str(output),
            "--allow-unverified-indicators"]
    assert traditional_main(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 4
    assert report["indicator_capture_times_supplied"] is False
    assert report["public_performance_allowed"] is False
    assert report["indicator_names"] == ["DGS10"]
    assert len(report["indicator_file_sha256"]) == 64
    assert report["horizons"][0]["status"] == "blocked"
    assert report["horizons"][0]["metrics"] is None
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
    assert traditional_main(args) == 2  # Do not overwrite an existing private report.


def test_traditional_cli_records_per_indicator_age_and_rejects_unknown_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _manifest(tmp_path)
    indicators = tmp_path / "indicators.csv"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    lines = ["name,source,observed_at,available_at,value"]
    for item in data["snapshots"]:
        captured = datetime.fromisoformat(item["captured_at"])
        observed = captured - timedelta(minutes=5)
        available = captured - timedelta(minutes=2)
        lines.append(f"DGS10,synthetic,{observed.isoformat()},{available.isoformat()},3.0")
    first = datetime.fromisoformat(data["snapshots"][0]["captured_at"])
    lines.append(f"NFCI_RISK,synthetic,{(first - timedelta(minutes=5)).isoformat()},"
                 f"{(first - timedelta(minutes=2)).isoformat()},0.2")
    indicators.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args = ["--manifest", str(manifest), "--indicators", str(indicators),
            "--raw-root", str(tmp_path / "raw"), "--indicator", "DGS10",
            "--indicator", "NFCI_RISK", "--indicator-age-hours", "DGS10=25",
            "--indicator-age-hours", "NFCI_RISK=240", "--allow-unverified-indicators"]
    assert traditional_main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["indicator_max_age_hours"] == {"DGS10": 25.0, "NFCI_RISK": 240.0}
    assert result["horizons"][0]["status"] == "blocked"

    assert traditional_main([*args, "--indicator-age-hours", "UNKNOWN=12"]) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["status"] == "invalid_input"
    assert "unknown indicator age" in rejected["reason"]


def test_indicator_capture_time_prevents_retroactive_use(tmp_path: Path) -> None:
    path = tmp_path / "indicators.csv"
    path.write_text(
        "name,source,observed_at,available_at,captured_at,value\n"
        "DGS10,source,2026-10-16T20:00:00Z,2026-10-19T20:16:00Z,"
        "2026-10-19T20:21:00Z,5.09\n",
        encoding="utf-8",
    )
    rows, _, capture_supplied = load_indicators(path)
    assert capture_supplied is True
    assert rows[0].available_at == datetime.fromisoformat("2026-10-19T20:21:00+00:00")
    forecasts = (
        VolatilityForecast("TLT", date(2026, 10, 19),
                           datetime.fromisoformat("2026-10-19T20:20:00+00:00"),
                           5, 0.02, 0.02, "a" * 64),
        VolatilityForecast("TLT", date(2026, 10, 20),
                           datetime.fromisoformat("2026-10-20T20:20:00+00:00"),
                           5, 0.02, 0.02, "b" * 64),
    )
    panel = build_macro_risk_panel(
        forecasts, rows, [], [], required_indicators=("DGS10",),
        max_indicator_age=timedelta(days=5), max_probability_age=timedelta(days=1),
        max_release_lead=timedelta(days=1), include_probability_research=False,
    )
    assert [row.forecast.session_date for row in panel.traditional_rows] == [date(2026, 10, 20)]
    assert panel.coverage.indicator_exclusions == (("DGS10", "missing_indicator", 1),)

    path.write_text(
        "name,source,observed_at,available_at,captured_at,value\n"
        "DGS10,source,2026-10-16T20:00:00Z,2026-10-19T20:16:00Z,"
        "2026-10-19T20:10:00Z,5.09\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="capture cannot precede provider availability"):
        load_indicators(path)


def test_strict_comparison_rejects_indicator_without_capture_time(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    indicators = tmp_path / "indicators.csv"
    indicators.write_text(
        "name,source,observed_at,available_at,value\n"
        "DGS10,synthetic,2026-01-05T21:00:00Z,2026-01-05T21:02:00Z,3.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="captured_at is required"):
        load_indicators(indicators, require_captured_at=True)
    assert traditional_main([
        "--manifest", str(manifest), "--indicators", str(indicators),
        "--raw-root", str(tmp_path / "raw"),
    ]) == 2


def test_strict_comparison_reports_capture_input_but_does_not_verify_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    indicators = tmp_path / "indicators.csv"
    lines = ["name,source,observed_at,available_at,captured_at,value"]
    for item in data["snapshots"]:
        captured_at = datetime.fromisoformat(item["captured_at"])
        lines.append(
            f"DGS10,synthetic,{(captured_at - timedelta(minutes=5)).isoformat()},"
            f"{(captured_at - timedelta(minutes=2)).isoformat()},"
            f"{captured_at.isoformat()},3.0"
        )
    indicators.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert traditional_main([
        "--manifest", str(manifest), "--indicators", str(indicators),
        "--raw-root", str(tmp_path / "raw"),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["indicator_capture_times_supplied"] is True
    assert report["indicator_capture_times_verified"] is False
    assert report["public_performance_allowed"] is False


def test_traditional_cli_reads_archived_treasury_dates_without_fake_release_times(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _manifest(tmp_path)
    raw_root = tmp_path / "raw"
    xml = (b'<feed xmlns="http://www.w3.org/2005/Atom" '
           b'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">'
           b'<entry><d:NEW_DATE>2026-01-05T00:00:00</d:NEW_DATE>'
           b'<d:BC_10YEAR>4.0</d:BC_10YEAR></entry></feed>')
    with TreasuryYieldCollector(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, content=xml, headers={"content-type": "application/xml"}
        )),
        clock=lambda: datetime.fromisoformat("2026-01-06T22:00:00+00:00"),
    ) as collector:
        collector.collect_month(2026, 1, ImmutableRawStore(raw_root))
    assert traditional_main([
        "--manifest", str(manifest), "--treasury-archive", str(raw_root),
        "--raw-root", str(raw_root), "--indicator-age-hours", "UST10Y_PAR=72",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["indicator_names"] == ["UST10Y_PAR"]
    assert report["indicator_raw_archive_checked"] is True
    assert report["indicator_capture_times_verified"] is False


def test_manifest_accepts_cross_year_sessions_and_rejects_false_holiday_price(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sessions = nasdaq_sessions(date(2024, 12, 23), date(2025, 1, 15))
    entries = []
    for index, session in enumerate(sessions):
        rows = ["session_date,observed_at,available_at,close,adjusted_close,volume"]
        for offset, prior in enumerate(sessions[: index + 1]):
            rows.append(
                f"{prior.session_date},{prior.close_at.isoformat()},"
                f"{(prior.close_at + timedelta(minutes=2)).isoformat()},"
                f"{100 + offset},{100 + offset},"
            )
        name = f"capture-{index}.csv"
        (tmp_path / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
        entries.append({"path": name, "end": str(session.session_date),
                        "captured_at": (session.close_at + timedelta(minutes=5)).isoformat()})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1, "source": "synthetic", "start": str(sessions[0].session_date),
        "end": str(sessions[-1].session_date), "holdout_start": "2025-01-10",
        "evaluation_at": (sessions[-1].close_at + timedelta(minutes=10)).isoformat(),
        "prediction_delay_minutes": 10, "snapshots": entries,
    }), encoding="utf-8")
    assert main(["--manifest", str(manifest), "--raw-root", str(tmp_path / "raw")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["snapshot_count"] == len(sessions)
    assert result["snapshot_provenance"][-1]["session_count"] == len(sessions)
    assert result["calendar_version"].startswith("nasdaq-us-equities-2024-2026")

    # A fabricated close on the special closure cannot be silently included as a session.
    broken = tmp_path / entries[-1]["path"]
    contents = broken.read_text(encoding="utf-8")
    broken.write_text(contents + "2025-01-09,2025-01-09T21:00:00Z,"
                      "2025-01-09T21:02:00Z,100,100,\n", encoding="utf-8")
    assert main(["--manifest", str(manifest), "--raw-root", str(tmp_path / "raw")]) == 2
    assert "incomplete or invalid calendar coverage" in capsys.readouterr().out
