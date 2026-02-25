"""
Pytest configuration and shared fixtures for AI Business Advisor tests.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Event loop policy (needed for pytest-asyncio with FastAPI)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# App client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_client():
    """Return a synchronous TestClient with lifespan disabled."""
    # Patch away external services so unit tests don't hit real APIs
    with (
        patch("backend.state.db_conn",          None),
        patch("backend.state.checkpointer",     None),
    ):
        from backend.main import app
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


# ---------------------------------------------------------------------------
# Mock portfolio agent
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_portfolio_agent():
    agent = MagicMock()
    agent.analyze_portfolio = AsyncMock(return_value={
        "holdings": [
            {
                "symbol": "AAPL",
                "quantity": 10,
                "current_price": 175.0,
                "current_value": 1750.0,
                "purchase_price": 150.0,
                "pnl": 250.0,
                "pnl_pct": 16.67,
                "weight": 0.5,
                "data_source": "yfinance",
            }
        ],
        "portfolio_summary": {
            "total_value": 3500.0,
            "total_pnl": 500.0,
            "total_pnl_pct": 16.67,
        },
        "risk_metrics": {
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.5,
            "var_95": -0.025,
            "cvar_95": -0.038,
        },
        "data_source": "yfinance",
    })
    return agent


# ---------------------------------------------------------------------------
# Mock graph
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_advisor_graph():
    from langchain_core.messages import AIMessage
    graph = MagicMock()
    graph.invoke.return_value = {
        "messages": [AIMessage(content="This is a test response from ARIA.")]
    }
    return graph
