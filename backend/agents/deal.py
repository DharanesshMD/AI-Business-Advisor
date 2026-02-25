"""
Deal Intelligence Agent for ARIA — Phase 3.

Provides M&A target analysis using three valuation methods:
  1. DCF (Discounted Cash Flow)
  2. Comparable Companies (EV/EBITDA, P/E multiples)
  3. Precedent Transactions (premium-to-market estimate)

Also runs FTC Herfindahl-Hirschman Index (HHI) regulatory risk analysis
to flag deals that may attract antitrust scrutiny.

Market data is sourced from yfinance with graceful fallback to mock values.
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional

logger = logging.getLogger("advisor.deal")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default WACC components (used when live data is unavailable)
_DEFAULT_WACC = 0.10          # 10% discount rate
_DEFAULT_GROWTH_RATE = 0.03   # 3% terminal growth rate

# HHI thresholds per DOJ/FTC horizontal merger guidelines
_HHI_UNCONCENTRATED = 1_500
_HHI_MODERATE = 2_500
# Delta thresholds that trigger scrutiny
_HHI_DELTA_MODERATE = 100
_HHI_DELTA_HIGH = 200


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _fetch_ticker_info(symbol: str) -> Dict[str, Any]:
    """Fetch yfinance info dict; return empty dict on failure."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return info
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {symbol}: {e}")
        return {}


def _fetch_financials(symbol: str) -> Dict[str, Optional[float]]:
    """
    Extract key financial metrics needed for DCF and comps.
    Returns a dict with float values (None when unavailable).
    """
    info = _fetch_ticker_info(symbol)

    def _get(key: str) -> Optional[float]:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "market_cap":        _get("marketCap"),
        "enterprise_value":  _get("enterpriseValue"),
        "ebitda":            _get("ebitda"),
        "free_cash_flow":    _get("freeCashflow"),
        "revenue":           _get("totalRevenue"),
        "net_income":        _get("netIncomeToCommon"),
        "total_debt":        _get("totalDebt"),
        "cash":              _get("totalCash"),
        "shares_outstanding":_get("sharesOutstanding"),
        "current_price":     _get("currentPrice") or _get("regularMarketPrice"),
        "pe_ratio":          _get("trailingPE"),
        "ev_ebitda":         _get("enterpriseToEbitda"),
        "revenue_growth":    _get("revenueGrowth"),
        "profit_margins":    _get("profitMargins"),
        "sector":            info.get("sector"),
        "industry":          info.get("industry"),
        "company_name":      info.get("longName") or symbol,
    }


# ---------------------------------------------------------------------------
# Valuation engines
# ---------------------------------------------------------------------------

def _dcf_valuation(
    financials: Dict[str, Any],
    wacc: float = _DEFAULT_WACC,
    terminal_growth: float = _DEFAULT_GROWTH_RATE,
    forecast_years: int = 5,
    fcf_growth_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Simple Gordon-Growth DCF.

    Intrinsic value = PV of forecast FCF + PV of terminal value.
    Falls back to earnings-based estimate when FCF is unavailable.
    """
    fcf = financials.get("free_cash_flow")
    shares = financials.get("shares_outstanding")
    current_price = financials.get("current_price")

    data_source = "live"

    # Estimate FCF from net income when absent
    if not fcf:
        net_income = financials.get("net_income")
        if net_income:
            fcf = net_income * 0.8   # conservative FCF proxy
            data_source = "estimated"
        else:
            # Full mock fallback
            market_cap = financials.get("market_cap") or 1_000_000_000
            fcf = market_cap * 0.05  # 5% FCF yield assumption
            data_source = "mock"

    # FCF growth: use revenue growth * 0.8, or default 8%
    if fcf_growth_rate is None:
        rev_growth = financials.get("revenue_growth")
        fcf_growth_rate = (rev_growth * 0.8) if rev_growth else 0.08

    # Cap growth to realistic bounds
    fcf_growth_rate = max(-0.30, min(fcf_growth_rate, 0.50))

    # Forecast FCF
    pv_fcfs = 0.0
    current_fcf = fcf
    for year in range(1, forecast_years + 1):
        current_fcf *= (1 + fcf_growth_rate)
        pv_fcfs += current_fcf / ((1 + wacc) ** year)

    # Terminal value (Gordon Growth)
    terminal_fcf = current_fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** forecast_years)

    enterprise_value = pv_fcfs + pv_terminal

    # Equity value = EV - debt + cash
    debt = financials.get("total_debt") or 0.0
    cash = financials.get("cash") or 0.0
    equity_value = enterprise_value - debt + cash

    # Per-share intrinsic value
    intrinsic_per_share = None
    upside_pct = None
    if shares and shares > 0:
        intrinsic_per_share = equity_value / shares
        if current_price and current_price > 0:
            upside_pct = (intrinsic_per_share - current_price) / current_price * 100

    return {
        "method": "DCF",
        "data_source": data_source,
        "assumptions": {
            "wacc": wacc,
            "terminal_growth_rate": terminal_growth,
            "forecast_years": forecast_years,
            "fcf_growth_rate": round(fcf_growth_rate, 4),
        },
        "pv_forecast_fcf":       round(pv_fcfs),
        "pv_terminal_value":     round(pv_terminal),
        "enterprise_value":      round(enterprise_value),
        "equity_value":          round(equity_value),
        "intrinsic_value_per_share": round(intrinsic_per_share, 2) if intrinsic_per_share else None,
        "current_price":         current_price,
        "upside_pct":            round(upside_pct, 1) if upside_pct is not None else None,
    }


def _comps_valuation(
    target: Dict[str, Any],
    peers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Comparable-companies valuation using peer EV/EBITDA and P/E multiples.

    Calculates median peer multiples then applies them to the target's
    EBITDA and earnings to derive an implied enterprise/equity value.
    """
    # Collect peer multiples
    peer_ev_ebitda = [p["ev_ebitda"] for p in peers if p.get("ev_ebitda")]
    peer_pe        = [p["pe_ratio"]  for p in peers if p.get("pe_ratio")]

    def _median(lst: List[float]) -> Optional[float]:
        if not lst:
            return None
        s = sorted(lst)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    median_ev_ebitda = _median(peer_ev_ebitda)
    median_pe        = _median(peer_pe)

    # Apply multiples to target
    target_ebitda     = target.get("ebitda")
    target_net_income = target.get("net_income")
    target_shares     = target.get("shares_outstanding")
    current_price     = target.get("current_price")

    implied_ev_from_ebitda = None
    implied_equity_per_share_ev = None
    if median_ev_ebitda and target_ebitda:
        implied_ev_from_ebitda = median_ev_ebitda * target_ebitda
        # Equity value = EV - debt + cash
        debt = target.get("total_debt") or 0.0
        cash = target.get("cash") or 0.0
        eq = implied_ev_from_ebitda - debt + cash
        if target_shares and target_shares > 0:
            implied_equity_per_share_ev = eq / target_shares

    implied_price_from_pe = None
    if median_pe and target_net_income and target_shares and target_shares > 0:
        eps = target_net_income / target_shares
        implied_price_from_pe = median_pe * eps

    # Blended estimate (average of available methods)
    estimates = [v for v in [implied_equity_per_share_ev, implied_price_from_pe] if v]
    blended_price = sum(estimates) / len(estimates) if estimates else None

    upside_pct = None
    if blended_price and current_price and current_price > 0:
        upside_pct = (blended_price - current_price) / current_price * 100

    return {
        "method": "Comparable Companies",
        "peer_count": len(peers),
        "multiples": {
            "median_ev_ebitda": round(median_ev_ebitda, 2) if median_ev_ebitda else None,
            "median_pe":        round(median_pe, 2)        if median_pe        else None,
        },
        "implied_ev_from_ebitda":         round(implied_ev_from_ebitda) if implied_ev_from_ebitda else None,
        "implied_price_ev_ebitda_method": round(implied_equity_per_share_ev, 2) if implied_equity_per_share_ev else None,
        "implied_price_pe_method":        round(implied_price_from_pe, 2) if implied_price_from_pe else None,
        "blended_implied_price":          round(blended_price, 2) if blended_price else None,
        "current_price":                  current_price,
        "upside_pct":                     round(upside_pct, 1) if upside_pct is not None else None,
    }


def _precedent_transactions_valuation(
    target: Dict[str, Any],
    control_premium: float = 0.30,
) -> Dict[str, Any]:
    """
    Precedent Transactions estimate.

    Applies a control premium to the current market price — a simple but
    widely used first-pass for M&A offer price estimation.
    """
    current_price = target.get("current_price")
    market_cap    = target.get("market_cap")

    implied_offer_price = None
    implied_deal_equity = None

    if current_price:
        implied_offer_price = current_price * (1 + control_premium)
    if market_cap:
        implied_deal_equity = market_cap * (1 + control_premium)

    return {
        "method": "Precedent Transactions",
        "control_premium_applied": control_premium,
        "current_market_price":   current_price,
        "implied_offer_price":    round(implied_offer_price, 2) if implied_offer_price else None,
        "implied_deal_equity_value": round(implied_deal_equity) if implied_deal_equity else None,
        "note": (
            f"Estimate based on a {control_premium:.0%} control premium over current market price. "
            "Actual premiums vary by sector, deal structure, and competitive dynamics."
        ),
    }


# ---------------------------------------------------------------------------
# HHI regulatory analysis
# ---------------------------------------------------------------------------

def _hhi_analysis(
    acquirer_market_share: float,
    target_market_share: float,
    other_shares: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Compute pre-deal and post-deal HHI and assess antitrust risk.

    HHI = sum of squared market shares (as percentages, 0-100).
    DOJ/FTC thresholds:
      < 1,500         — Unconcentrated (unlikely to challenge)
      1,500 – 2,500   — Moderately concentrated (scrutiny if delta > 100)
      > 2,500         — Highly concentrated (scrutiny if delta > 200; presumed harmful > 200)
    """
    other_shares = other_shares or []

    # All shares as percentages 0-100
    all_shares_pre = [acquirer_market_share, target_market_share] + other_shares
    # Normalise if they look like decimals (0-1)
    if all(s <= 1.0 for s in all_shares_pre):
        all_shares_pre = [s * 100 for s in all_shares_pre]
        acquirer_market_share *= 100
        target_market_share   *= 100

    remainder = max(0.0, 100.0 - sum(all_shares_pre))
    if remainder > 0:
        all_shares_pre.append(remainder)

    hhi_pre = sum(s ** 2 for s in all_shares_pre)

    # Post-deal: merge acquirer + target share
    combined_share = acquirer_market_share + target_market_share
    all_shares_post = [combined_share] + other_shares
    remainder_post = max(0.0, 100.0 - sum(all_shares_post))
    if remainder_post > 0:
        all_shares_post.append(remainder_post)
    hhi_post = sum(s ** 2 for s in all_shares_post)

    delta_hhi = hhi_post - hhi_pre

    # Classify
    if hhi_post < _HHI_UNCONCENTRATED:
        concentration = "Unconcentrated"
        risk = "Low"
        assessment = "Market remains unconcentrated post-merger. Antitrust challenge unlikely."
    elif hhi_post < _HHI_MODERATE:
        concentration = "Moderately Concentrated"
        if delta_hhi > _HHI_DELTA_MODERATE:
            risk = "Medium"
            assessment = (
                f"Post-deal HHI is {hhi_post:.0f} (+{delta_hhi:.0f}), entering moderately "
                "concentrated territory with a delta above 100. Regulators may investigate."
            )
        else:
            risk = "Low-Medium"
            assessment = (
                f"Post-deal HHI is {hhi_post:.0f} (+{delta_hhi:.0f}). Moderately concentrated "
                "but delta below 100. Unlikely to trigger formal review."
            )
    else:
        concentration = "Highly Concentrated"
        if delta_hhi > _HHI_DELTA_HIGH:
            risk = "High"
            assessment = (
                f"Post-deal HHI is {hhi_post:.0f} (+{delta_hhi:.0f}). Highly concentrated with "
                "delta above 200 — deal is presumed anticompetitive under DOJ/FTC guidelines. "
                "Expect significant regulatory scrutiny or required divestitures."
            )
        else:
            risk = "Medium-High"
            assessment = (
                f"Post-deal HHI is {hhi_post:.0f} (+{delta_hhi:.0f}). Highly concentrated market "
                "but delta below 200. Regulators will likely review; outcome depends on market definition."
            )

    return {
        "pre_deal_hhi":      round(hhi_pre),
        "post_deal_hhi":     round(hhi_post),
        "delta_hhi":         round(delta_hhi),
        "market_concentration": concentration,
        "regulatory_risk":   risk,
        "assessment":        assessment,
        "acquirer_share_pct": round(acquirer_market_share, 1),
        "target_share_pct":   round(target_market_share, 1),
        "combined_share_pct": round(combined_share, 1),
    }


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class DealIntelligenceAgent:
    """
    Phase 3 Deal Intelligence Agent.

    Orchestrates DCF, comparable-companies, and precedent-transactions
    valuation alongside HHI regulatory risk analysis.
    """

    async def analyze(
        self,
        target_symbol: str,
        peer_symbols: List[str],
        acquirer_market_share: float,
        target_market_share: float,
        other_market_shares: Optional[List[float]] = None,
        wacc: float = _DEFAULT_WACC,
        terminal_growth: float = _DEFAULT_GROWTH_RATE,
        control_premium: float = 0.30,
    ) -> Dict[str, Any]:
        """
        Run full deal analysis for a potential acquisition target.

        Returns a structured report with:
          - Company snapshot
          - DCF valuation
          - Comparable-companies valuation
          - Precedent-transactions estimate
          - HHI regulatory risk
          - Overall verdict
        """
        loop = asyncio.get_event_loop()

        # Fetch target + peer financials concurrently via thread pool
        # (yfinance is synchronous)
        target_fin_future = loop.run_in_executor(None, _fetch_financials, target_symbol)
        peer_futures = [
            loop.run_in_executor(None, _fetch_financials, sym)
            for sym in peer_symbols
        ]

        target_fin = await target_fin_future
        peer_fins  = await asyncio.gather(*peer_futures)

        # Valuations (CPU-only, run inline)
        dcf    = _dcf_valuation(target_fin, wacc=wacc, terminal_growth=terminal_growth)
        comps  = _comps_valuation(target_fin, list(peer_fins))
        prec   = _precedent_transactions_valuation(target_fin, control_premium=control_premium)
        hhi    = _hhi_analysis(acquirer_market_share, target_market_share, other_market_shares)

        # Aggregate implied price range
        implied_prices = [
            v for v in [
                dcf.get("intrinsic_value_per_share"),
                comps.get("blended_implied_price"),
                prec.get("implied_offer_price"),
            ]
            if v is not None
        ]
        price_range = {
            "low":    round(min(implied_prices), 2) if implied_prices else None,
            "high":   round(max(implied_prices), 2) if implied_prices else None,
            "median": round(sorted(implied_prices)[len(implied_prices) // 2], 2)
                      if implied_prices else None,
        }

        # Simple verdict
        current_price = target_fin.get("current_price")
        verdict = _generate_verdict(
            current_price, price_range, hhi["regulatory_risk"], dcf["data_source"]
        )

        return {
            "target": {
                "symbol":       target_symbol.upper(),
                "name":         target_fin.get("company_name", target_symbol),
                "sector":       target_fin.get("sector"),
                "industry":     target_fin.get("industry"),
                "market_cap":   target_fin.get("market_cap"),
                "current_price":current_price,
            },
            "peers_analyzed": [p.get("company_name", s) for p, s in zip(peer_fins, peer_symbols)],
            "valuations": {
                "dcf":                    dcf,
                "comparable_companies":   comps,
                "precedent_transactions": prec,
            },
            "implied_price_range":      price_range,
            "regulatory_analysis":      hhi,
            "verdict":                  verdict,
        }


def _generate_verdict(
    current_price: Optional[float],
    price_range: Dict[str, Optional[float]],
    regulatory_risk: str,
    data_source: str,
) -> Dict[str, str]:
    """Generate a plain-English deal verdict from valuation + regulatory inputs."""
    lines = []

    # Valuation verdict
    low  = price_range.get("low")
    high = price_range.get("high")
    if current_price and low and high:
        if current_price < low:
            val_verdict = "ATTRACTIVE"
            lines.append(
                f"Current market price (${current_price:.2f}) is below all valuation estimates "
                f"(${low:.2f}–${high:.2f}), suggesting the target may be undervalued."
            )
        elif current_price > high:
            val_verdict = "RICH"
            lines.append(
                f"Current market price (${current_price:.2f}) exceeds the implied range "
                f"(${low:.2f}–${high:.2f}). Acquirer may need to justify a strategic premium."
            )
        else:
            val_verdict = "FAIR VALUE"
            lines.append(
                f"Current market price (${current_price:.2f}) sits within the implied range "
                f"(${low:.2f}–${high:.2f}), indicating fair value."
            )
    else:
        val_verdict = "INSUFFICIENT DATA"
        lines.append("Valuation data is limited; treat estimates with caution.")

    # Regulatory verdict
    lines.append(f"Regulatory risk is rated {regulatory_risk} based on HHI analysis.")

    if data_source == "mock":
        lines.append(
            "NOTE: Financial figures are estimates (live data unavailable). "
            "Verify all numbers before use in a real transaction."
        )

    return {
        "valuation_signal": val_verdict,
        "regulatory_risk":  regulatory_risk,
        "summary":          " ".join(lines),
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_deal_agent: Optional[DealIntelligenceAgent] = None


def get_deal_agent() -> DealIntelligenceAgent:
    global _deal_agent
    if _deal_agent is None:
        _deal_agent = DealIntelligenceAgent()
    return _deal_agent
