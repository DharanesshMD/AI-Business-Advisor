"""
Unit tests for the health endpoint and basic REST contract.
Uses TestClient with mocked state so no real services are needed.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def client():
    """Spin up a test client with all external services mocked."""
    with (
        patch("backend.state.checkpointer", None),
        patch("backend.state.db_conn", None),
        patch("backend.quotas.check_quota", return_value=True),
    ):
        from fastapi.testclient import TestClient
        from backend.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self, client):
        body = client.get("/health").json()
        assert "status" in body
        assert "version" in body
        assert "model" in body

    def test_health_status_is_healthy(self, client):
        assert client.get("/health").json()["status"] == "healthy"


class TestChatEndpoint:
    def test_empty_message_returns_422(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client):
        resp = client.post("/api/chat", json={"message": "x" * 4_001})
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, client):
        resp = client.post("/api/chat", json={"location": "India"})
        assert resp.status_code == 422


class TestPortfolioEndpoint:
    def test_empty_holdings_returns_422(self, client):
        resp = client.post("/api/portfolio/analyze", json={"holdings": []})
        assert resp.status_code == 422

    def test_invalid_symbol_returns_422(self, client):
        resp = client.post("/api/portfolio/analyze", json={
            "holdings": [{"symbol": "AAP1", "quantity": 10, "purchase_price": 150}]
        })
        assert resp.status_code == 422

    def test_negative_quantity_returns_422(self, client):
        resp = client.post("/api/portfolio/analyze", json={
            "holdings": [{"symbol": "AAPL", "quantity": -1, "purchase_price": 150}]
        })
        assert resp.status_code == 422

    def test_simulations_too_large_returns_422(self, client):
        resp = client.post("/api/portfolio/analyze", json={
            "holdings": [{"symbol": "AAPL", "quantity": 10, "purchase_price": 150}],
            "simulations": 50_000,
        })
        assert resp.status_code == 422

    def test_too_many_holdings_returns_422(self, client):
        holdings = [
            {"symbol": f"T{i:02d}", "quantity": 1, "purchase_price": 100}
            for i in range(51)
        ]
        resp = client.post("/api/portfolio/analyze", json={"holdings": holdings})
        assert resp.status_code == 422


class TestValidateEndpoint:
    def test_empty_session_returns_422(self, client):
        resp = client.post("/api/validate", json={
            "message_content": "Some text", "session_id": ""
        })
        assert resp.status_code == 422

    def test_empty_content_returns_422(self, client):
        resp = client.post("/api/validate", json={
            "message_content": "", "session_id": "abc"
        })
        assert resp.status_code == 422

    def test_no_history_returns_is_valid_true(self, client):
        """When no history exists for the session, validator should pass gracefully."""
        resp = client.post("/api/validate", json={
            "message_content": "AAPL at $180", "session_id": "nonexistent-session"
        })
        assert resp.status_code == 200
        assert resp.json().get("is_valid") is True


class TestDealEndpoint:
    _VALID_PAYLOAD = {
        "target_symbol": "MSFT",
        "peer_symbols": ["AAPL", "GOOGL"],
        "acquirer_market_share": 20.0,
        "target_market_share": 10.0,
    }

    def test_missing_target_symbol_returns_422(self, client):
        payload = {k: v for k, v in self._VALID_PAYLOAD.items() if k != "target_symbol"}
        resp = client.post("/api/deal/analyze", json=payload)
        assert resp.status_code == 422

    def test_invalid_target_symbol_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "target_symbol": "MS1FT",    # digit not allowed
        })
        assert resp.status_code == 422

    def test_invalid_peer_symbol_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "peer_symbols": ["AAPL", "GO1GL"],   # digit in peer
        })
        assert resp.status_code == 422

    def test_too_many_peers_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "peer_symbols": [f"T{i:02d}" for i in range(11)],  # 11 > max 10
        })
        assert resp.status_code == 422

    def test_zero_acquirer_share_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "acquirer_market_share": 0.0,
        })
        assert resp.status_code == 422

    def test_wacc_out_of_range_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "wacc": 0.99,   # > 0.50 limit
        })
        assert resp.status_code == 422

    def test_control_premium_out_of_range_returns_422(self, client):
        resp = client.post("/api/deal/analyze", json={
            **self._VALID_PAYLOAD,
            "control_premium": 1.5,   # > 1.00 limit
        })
        assert resp.status_code == 422
