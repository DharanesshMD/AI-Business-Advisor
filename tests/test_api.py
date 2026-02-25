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
