from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from shockgraph_data_pipeline.market_calendar import nasdaq_2026_sessions

from scripts.evaluate_snapshot_holdout import main


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
