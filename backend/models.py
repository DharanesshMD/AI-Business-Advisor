"""
Pydantic request / response models with strict input validation.
"""
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared / sub-models
# ---------------------------------------------------------------------------

class HoldingModel(BaseModel):
    """A single portfolio holding with validated fields."""

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol (e.g. AAPL)",
    )
    quantity: float = Field(
        ..., gt=0, le=1_000_000, description="Number of shares held"
    )
    purchase_price: float = Field(
        ..., gt=0, le=1_000_000, description="Price per share at time of purchase"
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{1,10}$", v):
            raise ValueError("symbol must be 1–10 uppercase ASCII letters only")
        return v


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Synchronous REST chat request."""

    message: str = Field(..., min_length=1, max_length=4_000)
    location: Optional[str] = Field("India", max_length=100)
    session_id: Optional[str] = Field(None, max_length=128)


class ChatResponse(BaseModel):
    """Synchronous REST chat response."""

    response: str
    session_id: str


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class PortfolioRequest(BaseModel):
    """Portfolio analysis request."""

    holdings: List[HoldingModel] = Field(
        ..., min_length=1, max_length=50, description="List of portfolio holdings"
    )
    simulations: int = Field(
        1000,
        ge=100,
        le=10_000,
        description="Monte Carlo simulation count (100–10 000)",
    )
    days: int = Field(30, ge=1, le=365, description="Look-back / forecast window in days")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    """Manual validation request."""

    message_content: str = Field(..., min_length=1, max_length=50_000)
    session_id: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health-check response."""

    status: str
    version: str
    model: str
