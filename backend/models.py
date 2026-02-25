"""
Pydantic request / response models with strict input validation.
"""
import re
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Deal Intelligence (Phase 3)
# ---------------------------------------------------------------------------

class DealRequest(BaseModel):
    """M&A deal analysis request."""

    target_symbol: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker of the acquisition target (e.g. MSFT)",
    )
    peer_symbols: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Comparable-company tickers (0–10)",
    )
    acquirer_market_share: float = Field(
        ..., gt=0, le=100,
        description="Acquirer's current market share as a percentage (0–100)",
    )
    target_market_share: float = Field(
        ..., gt=0, le=100,
        description="Target's current market share as a percentage (0–100)",
    )
    other_market_shares: Optional[List[float]] = Field(
        None,
        description="Other players' market shares as percentages (optional)",
    )
    wacc: float = Field(
        0.10, ge=0.01, le=0.50,
        description="Discount rate / WACC for DCF (1%–50%, default 10%)",
    )
    terminal_growth: float = Field(
        0.03, ge=0.00, le=0.10,
        description="Terminal growth rate for DCF (0%–10%, default 3%)",
    )
    control_premium: float = Field(
        0.30, ge=0.00, le=1.00,
        description="Control premium for precedent transactions (0–100%, default 30%)",
    )

    @field_validator("target_symbol")
    @classmethod
    def validate_target_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{1,10}$", v):
            raise ValueError("target_symbol must be 1–10 uppercase ASCII letters only")
        return v

    @field_validator("peer_symbols", mode="before")
    @classmethod
    def validate_peer_symbols(cls, v: List[str]) -> List[str]:
        cleaned = []
        for sym in v:
            sym = str(sym).strip().upper()
            if not re.match(r"^[A-Z]{1,10}$", sym):
                raise ValueError(f"peer symbol '{sym}' must be 1–10 uppercase ASCII letters only")
            cleaned.append(sym)
        return cleaned
