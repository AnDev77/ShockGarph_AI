from __future__ import annotations

from fastapi.testclient import TestClient
from shockgraph_api.app import create_app


def test_demo_readiness_and_explicit_real_data_pending_never_share_numbers() -> None:
    client = TestClient(create_app(service_mode="demo"))
    assert client.get("/health/ready").json()["scope"] == "synthetic_scenario_demo"
    for asset in ("SPY", "TLT"):
        for horizon in ("m5", "m30"):
            demo = client.get(
                "/v1/scenarios/cpi",
                params={"source": "demo", "asset_id": asset, "horizon": horizon},
            )
            assert demo.status_code == 200
            assert demo.json()["provenance"]["source_kind"] == "synthetic"
            assert len(demo.json()["scenarios"]) == 3
    actual = client.get("/v1/scenarios/cpi", params={"source": "actual"}).json()
    assert actual["status"] == "pending"
    assert actual["scenarios"] == []
    assert "consensus_mom" not in actual
    assert "as_of" not in actual


def test_invalid_configured_actual_dataset_fails_closed(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")
    client = TestClient(create_app(service_mode="historical", scenario_dataset_path=path))
    assert client.get("/health/ready").status_code == 503
    result = client.get("/v1/scenarios/cpi", params={"source": "actual"}).json()
    assert result["reason"] == "invalid_scenario_dataset"
    assert result["scenarios"] == []


def test_scenario_query_validation_and_public_origin(monkeypatch) -> None:
    monkeypatch.setenv("SHOCKGRAPH_WEB_ORIGINS", "https://test.example")
    client = TestClient(create_app(service_mode="demo"))
    assert client.get("/v1/scenarios/cpi", params={"asset_id": "QQQ"}).status_code == 422
    assert client.get("/v1/scenarios/cpi", params={"source": "unknown"}).status_code == 422
    response = client.get("/v1/scenarios/cpi", headers={"Origin": "https://test.example"})
    assert response.headers["access-control-allow-origin"] == "https://test.example"
    blocked = client.get("/v1/scenarios/cpi", headers={"Origin": "https://other.example"})
    assert "access-control-allow-origin" not in blocked.headers
