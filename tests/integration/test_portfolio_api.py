from fastapi.testclient import TestClient
from shockgraph_api.app import create_app


def test_portfolio_demo_actual_separation_and_weight_change():
    client = TestClient(create_app(service_mode="demo"))
    first = client.get("/v1/portfolios/cpi", params={"source": "demo"}).json()
    second = client.get(
        "/v1/portfolios/cpi",
        params={
            "source": "demo",
            "spy_weight": 1,
            "tlt_weight": 0,
            "portfolio_value": 1000,
        },
    ).json()
    assert first["status"] == second["status"] == "ready"
    assert first["result"]["expected_return"] != second["result"]["expected_return"]
    assert second["provenance"]["source_kind"] == "synthetic"
    assert second["result"]["expected_change_usd"] is not None
    pending = client.get("/v1/portfolios/cpi").json()
    assert pending["status"] == "pending"
    assert pending["result"] is None
    assert "consensus_mom" not in pending and "provenance" not in pending


def test_invalid_portfolio_requests_return_422_even_when_actual_data_missing():
    client = TestClient(create_app(service_mode="demo"))
    for params in [
        {"spy_weight": -0.1},
        {"spy_weight": 0.4, "tlt_weight": 0.4},
        {"spy_weight": "nan"},
        {"horizon": "d5"},
        {"source": "other"},
        {"portfolio_value": -1},
        {"portfolio_value": "inf"},
    ]:
        assert client.get("/v1/portfolios/cpi", params=params).status_code == 422
