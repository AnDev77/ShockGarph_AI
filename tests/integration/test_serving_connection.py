from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shockgraph_analytics.connection import (
    REQUIRED_SCOPES,
    REQUIRED_USES,
    AuthorizationRecord,
    ServingManifest,
)
from shockgraph_api.app import create_app

from scripts.build_cpi_serving_snapshot import (
    build_snapshot,
    canonical,
    create_demo_manifest,
    inspect_inputs,
    load_quotes,
    write_immutable,
)

CHECKED = datetime(2026, 10, 10, tzinfo=UTC)


def licensed_test_manifest(tmp_path: Path) -> Path:
    """합성 자료를 실제 출처 코드 경로 검사용으로만 표시한다. 금융 실측값이 아니다."""
    manifest = create_demo_manifest(tmp_path)
    value = json.loads(manifest.read_text())
    value.update(
        source_kind="licensed_historical",
        source_reference="synthetic_test_only",
        authorization_record="authorization.json",
    )
    manifest.write_text(canonical(value))
    releases = manifest.parent / "releases.csv"
    releases.write_text(
        releases.read_text().replace(
            "https://example.invalid/synthetic/",
            "https://www.bls.gov/news.release/archives/cpi_",
        )
    )
    record = AuthorizationRecord(
        reference="synthetic_test_only_no_provider_permission",
        data_scopes=REQUIRED_SCOPES,
        uses=REQUIRED_USES,
    )
    (manifest.parent / "authorization.json").write_text(canonical(record.model_dump(mode="json")))
    return manifest


def test_demo_conversion_is_repeatable_and_never_loads_as_actual(tmp_path):
    manifest = create_demo_manifest(tmp_path)
    first = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    second = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    assert first == second
    assert first["status"] == "snapshot_built"
    snapshot = Path(first["snapshot"])
    data = json.loads(snapshot.read_text())
    assert len(data["observations"]) == 36 and data["source_kind"] == "synthetic"
    assert snapshot.parent.name == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="differs"):
        write_immutable(snapshot, "{}")
    client = TestClient(
        create_app(
            scenario_dataset_path=snapshot, connection_audit_path=Path(first["readiness_report"])
        )
    )
    assert client.get("/v1/portfolios/cpi").json()["result"] is None
    assert client.get("/v1/data-readiness/cpi").json()["status"] == "pending"


def test_audit_lists_missing_sources_and_gates_processing_before_read(tmp_path):
    manifest = licensed_test_manifest(tmp_path)
    (manifest.parent / "authorization.json").unlink()
    # If processing were attempted this would be an input error, rather than an authorization gap.
    (manifest.parent / "releases.csv").write_text("invalid secret input")
    (manifest.parent / "consensus.json").unlink()
    outcome = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    assert outcome["snapshot"] is None
    assert outcome["blocker_codes"] == ["consensus_json_missing", "authorization_missing"]
    client = TestClient(create_app(connection_audit_path=Path(outcome["readiness_report"])))
    body = client.get("/v1/data-readiness/cpi").json()
    assert body["status"] == "pending" and body["snapshot_sha256"] is None
    assert body["audit_status"] == "blocked"
    assert str(tmp_path) not in json.dumps(body) and "secret input" not in json.dumps(body)
    pending = client.get("/v1/portfolios/cpi").json()
    assert {b["code"] for b in pending["blockers"]} == {
        "consensus_json_missing",
        "authorization_missing",
        "snapshot_missing",
    }


@pytest.mark.parametrize("change", ["expired", "scope", "use"])
def test_incomplete_authorization_blocks_conversion(tmp_path, change):
    manifest = licensed_test_manifest(tmp_path)
    path = manifest.parent / "authorization.json"
    record = json.loads(path.read_text())
    if change == "expired":
        record["valid_until"] = CHECKED.isoformat()
    elif change == "scope":
        record["data_scopes"].remove("consensus")
    else:
        record["uses"].remove("derived_publication")
    path.write_text(canonical(record))
    result = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    assert result["blocker_codes"] == ["authorization_invalid"]
    assert result["snapshot"] is None


def test_snapshot_and_audit_must_match_but_built_without_snapshot_is_pending(tmp_path):
    manifest = licensed_test_manifest(tmp_path)
    output = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    snapshot, audit = Path(output["snapshot"]), Path(output["readiness_report"])
    client = TestClient(create_app(scenario_dataset_path=snapshot, connection_audit_path=audit))
    assert client.get("/v1/data-readiness/cpi").json()["status"] == "ready"
    assert client.get("/v1/portfolios/cpi").json()["status"] == "ready"
    missing = TestClient(create_app(connection_audit_path=audit))
    assert missing.get("/v1/data-readiness/cpi").json()["status"] == "pending"
    value = json.loads(audit.read_text())
    value["snapshot_sha256"] = "0" * 64
    bad = tmp_path / "mismatch.json"
    bad.write_text(canonical(value))
    client = TestClient(create_app(scenario_dataset_path=snapshot, connection_audit_path=bad))
    assert client.get("/v1/portfolios/cpi").json()["status"] == "pending"
    assert "readiness_invalid" in {
        b["code"] for b in client.get("/v1/data-readiness/cpi").json()["blockers"]
    }


def test_aggregate_curve_summary_is_rejected_and_original_quote_fields_work(tmp_path):
    path = create_demo_manifest(tmp_path)
    manifest = ServingManifest.model_validate_json(path.read_bytes())
    quotes = json.loads((path.parent / "quotes.json").read_text())
    original = {
        "schema_version": "kalshi-cpi-threshold-curve-v1",
        "event_ticker": manifest.target_event_id,
        "as_of": manifest.as_of.isoformat(),
        "contract_definition": "single_decimal_cpi_mom_strictly_greater_percentage_point",
        "quotes": [{**q, "status": "eligible", "quote_end_at": q["observed_at"]} for q in quotes],
    }
    loaded = load_quotes(canonical(original).encode(), manifest)
    assert [q.probability_above for q in loaded] == [0.75, 0.4]
    original["schema_version"] = "kalshi-cpi-threshold-curve-summary-v1"
    with pytest.raises(ValueError, match="aggregate"):
        load_quotes(canonical(original).encode(), manifest)


def test_input_presence_is_not_content_validation_and_malformed_input_is_blocked(tmp_path):
    path = create_demo_manifest(tmp_path)
    (path.parent / "quotes.json").write_text("[]")
    presence = build_snapshot(path, tmp_path, check_only=True, checked_at=CHECKED)
    assert presence["status"] == "inputs_present" and presence["snapshot"] is None
    processed = build_snapshot(path, tmp_path, checked_at=CHECKED)
    assert processed["blocker_codes"] == ["input_invalid"]
    assert processed["snapshot"] is None


def test_missing_manifest_and_corrupt_audit_fail_closed(tmp_path):
    _, _, audit, _ = inspect_inputs(tmp_path / "missing.json", CHECKED)
    assert audit.status == "blocked" and all(i.status == "missing" for i in audit.inputs)
    bad = tmp_path / "bad.json"
    bad.write_text('{"private_path":"/never/display"}')
    client = TestClient(create_app(connection_audit_path=bad))
    response = client.get("/v1/data-readiness/cpi").json()
    assert response["status"] == "pending" and "/never/display" not in json.dumps(response)


def test_sample_shortfall_is_distinct_from_connection_success(tmp_path):
    manifest = licensed_test_manifest(tmp_path)
    release_path = manifest.parent / "releases.csv"
    lines = release_path.read_text().splitlines(keepends=True)
    release_path.write_text("".join(lines[:4]))
    output = build_snapshot(manifest, tmp_path, checked_at=CHECKED)
    client = TestClient(
        create_app(
            scenario_dataset_path=Path(output["snapshot"]),
            connection_audit_path=Path(output["readiness_report"]),
        )
    )
    body = client.get("/v1/data-readiness/cpi").json()
    assert body["status"] == "insufficient_data"
    assert body["blockers"][0]["code"] == "scenario_sample_shortfall"
    assert client.get("/v1/portfolios/cpi").json()["result"] is None
