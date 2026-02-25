"""
Unit tests for input validation models (backend/models.py).
No external services required.
"""
import pytest
from pydantic import ValidationError

from backend.models import (
    ChatRequest,
    HoldingModel,
    PortfolioRequest,
    ValidateRequest,
)


# ---------------------------------------------------------------------------
# HoldingModel
# ---------------------------------------------------------------------------

class TestHoldingModel:
    def test_valid_holding(self):
        h = HoldingModel(symbol="AAPL", quantity=10, purchase_price=150.0)
        assert h.symbol == "AAPL"
        assert h.quantity == 10
        assert h.purchase_price == 150.0

    def test_symbol_normalised_to_uppercase(self):
        h = HoldingModel(symbol="aapl", quantity=1, purchase_price=100.0)
        assert h.symbol == "AAPL"

    def test_symbol_strips_whitespace(self):
        h = HoldingModel(symbol=" MSFT ", quantity=1, purchase_price=100.0)
        assert h.symbol == "MSFT"

    def test_symbol_too_long_rejected(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="TOOLONGTICKER", quantity=1, purchase_price=100.0)

    def test_symbol_with_digits_rejected(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAP1", quantity=1, purchase_price=100.0)

    def test_symbol_empty_rejected(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="", quantity=1, purchase_price=100.0)

    def test_quantity_must_be_positive(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAPL", quantity=0, purchase_price=100.0)

    def test_quantity_negative_rejected(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAPL", quantity=-5, purchase_price=100.0)

    def test_quantity_upper_bound(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAPL", quantity=2_000_000, purchase_price=100.0)

    def test_price_must_be_positive(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAPL", quantity=10, purchase_price=0)

    def test_price_negative_rejected(self):
        with pytest.raises(ValidationError):
            HoldingModel(symbol="AAPL", quantity=10, purchase_price=-1.0)


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------

class TestChatRequest:
    def test_valid_chat_request(self):
        r = ChatRequest(message="What is a startup?")
        assert r.message == "What is a startup?"
        assert r.location == "India"  # default

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_message_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 4_001)

    def test_location_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", location="x" * 101)

    def test_session_id_optional(self):
        r = ChatRequest(message="hi")
        assert r.session_id is None


# ---------------------------------------------------------------------------
# PortfolioRequest
# ---------------------------------------------------------------------------

class TestPortfolioRequest:
    def _holding(self, symbol="AAPL"):
        return {"symbol": symbol, "quantity": 10, "purchase_price": 150.0}

    def test_valid_portfolio_request(self):
        r = PortfolioRequest(holdings=[self._holding()])
        assert len(r.holdings) == 1
        assert r.simulations == 1000  # default

    def test_empty_holdings_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[])

    def test_too_many_holdings_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[self._holding(f"T{i:02d}") for i in range(51)])

    def test_simulations_lower_bound(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[self._holding()], simulations=50)

    def test_simulations_upper_bound(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[self._holding()], simulations=20_000)

    def test_days_lower_bound(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[self._holding()], days=0)

    def test_days_upper_bound(self):
        with pytest.raises(ValidationError):
            PortfolioRequest(holdings=[self._holding()], days=400)


# ---------------------------------------------------------------------------
# ValidateRequest
# ---------------------------------------------------------------------------

class TestValidateRequest:
    def test_valid_validate_request(self):
        r = ValidateRequest(message_content="Some content", session_id="abc123")
        assert r.session_id == "abc123"

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            ValidateRequest(message_content="", session_id="abc")

    def test_empty_session_rejected(self):
        with pytest.raises(ValidationError):
            ValidateRequest(message_content="content", session_id="")
