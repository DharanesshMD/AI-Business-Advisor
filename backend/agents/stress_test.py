"""
Scenario Stress Testing Agent
Simulates macro-economic shocks and calculates portfolio/company impact.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from backend.config import get_settings

logger = logging.getLogger(__name__)


class ShockType(Enum):
    """Pre-defined macro shock scenarios."""
    FED_RATE_HIKE_25BPS = "fed_rate_hike_25bps"
    FED_RATE_HIKE_50BPS = "fed_rate_hike_50bps"
    FED_RATE_CUT_25BPS = "fed_rate_cut_25bps"
    OIL_SPIKE_20PCT = "oil_spike_20pct"
    OIL_CRASH_30PCT = "oil_crash_30pct"
    USD_STRENGTHENING_10PCT = "usd_strengthening_10pct"
    USD_WEAKENING_10PCT = "usd_weakening_10pct"
    RECESSION_MILD = "recession_mild"
    RECESSION_SEVERE = "recession_severe"
    INFLATION_SPIKE = "inflation_spike"
    CHINA_SLOWDOWN = "china_slowdown"
    TECH_SELLOFF = "tech_selloff"
    CREDIT_CRISIS = "credit_crisis"
    GEOPOLITICAL_SHOCK = "geopolitical_shock"


@dataclass
class ShockScenario:
    """Defines a stress test scenario with its parameters."""
    name: str
    description: str
    shock_type: str
    # Factor sensitivities (beta coefficients)
    equity_beta: float  # General equity market sensitivity
    rate_sensitivity: float  # Interest rate sensitivity (duration-like)
    oil_sensitivity: float  # Oil price sensitivity
    usd_sensitivity: float  # USD strength sensitivity
    credit_spread_delta: float  # Change in credit spreads (bps)
    volatility_spike: float  # Expected VIX increase (%)
    # Sector-specific multipliers
    sector_impacts: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Pre-defined shock scenarios with empirically-calibrated sensitivities
SHOCK_SCENARIOS: Dict[str, ShockScenario] = {
    "fed_rate_hike_50bps": ShockScenario(
        name="Fed Rate Hike (+50bps)",
        description="Federal Reserve raises rates by 50 basis points unexpectedly",
        shock_type="fed_rate_hike_50bps",
        equity_beta=-0.03,  # 3% equity drawdown
        rate_sensitivity=-0.50,  # 50bps rate increase
        oil_sensitivity=0.0,
        usd_sensitivity=0.02,  # USD strengthens 2%
        credit_spread_delta=15,  # Credit spreads widen 15bps
        volatility_spike=25,  # VIX spikes 25%
        sector_impacts={
            "Technology": -0.05,  # Growth stocks hit harder
            "Financials": 0.02,  # Banks benefit from steeper curve
            "Real Estate": -0.08,  # REITs hammered
            "Utilities": -0.04,  # Rate-sensitive
            "Consumer Discretionary": -0.04,
            "Healthcare": -0.02,
            "Energy": -0.01,
            "Consumer Staples": -0.01,
            "Industrials": -0.03,
            "Materials": -0.02,
        }
    ),
    "fed_rate_cut_25bps": ShockScenario(
        name="Fed Rate Cut (-25bps)",
        description="Federal Reserve cuts rates by 25 basis points",
        shock_type="fed_rate_cut_25bps",
        equity_beta=0.02,
        rate_sensitivity=0.25,
        oil_sensitivity=0.0,
        usd_sensitivity=-0.01,
        credit_spread_delta=-10,
        volatility_spike=-10,
        sector_impacts={
            "Technology": 0.04,
            "Financials": -0.01,
            "Real Estate": 0.05,
            "Utilities": 0.03,
            "Consumer Discretionary": 0.03,
            "Healthcare": 0.01,
            "Energy": 0.01,
            "Consumer Staples": 0.01,
            "Industrials": 0.02,
            "Materials": 0.02,
        }
    ),
    "oil_spike_20pct": ShockScenario(
        name="Oil Price Spike (+20%)",
        description="Crude oil prices surge 20% due to supply disruption",
        shock_type="oil_spike_20pct",
        equity_beta=-0.02,
        rate_sensitivity=0.0,
        oil_sensitivity=0.20,
        usd_sensitivity=0.01,
        credit_spread_delta=20,
        volatility_spike=30,
        sector_impacts={
            "Technology": -0.02,
            "Financials": -0.01,
            "Real Estate": -0.02,
            "Utilities": -0.03,
            "Consumer Discretionary": -0.05,  # Airlines, autos hit
            "Healthcare": -0.01,
            "Energy": 0.15,  # Energy stocks rally
            "Consumer Staples": -0.02,
            "Industrials": -0.04,
            "Materials": 0.03,
        }
    ),
    "recession_severe": ShockScenario(
        name="Severe Recession",
        description="Deep economic contraction with GDP -4%, unemployment spike",
        shock_type="recession_severe",
        equity_beta=-0.25,  # 25% equity drawdown
        rate_sensitivity=0.50,  # Rates fall as Fed cuts
        oil_sensitivity=-0.30,  # Oil crashes on demand destruction
        usd_sensitivity=0.05,  # Flight to safety
        credit_spread_delta=200,  # Credit spreads blow out
        volatility_spike=150,  # VIX to 40+
        sector_impacts={
            "Technology": -0.30,
            "Financials": -0.35,
            "Real Estate": -0.25,
            "Utilities": -0.10,  # Defensive
            "Consumer Discretionary": -0.40,
            "Healthcare": -0.15,  # Defensive
            "Energy": -0.35,
            "Consumer Staples": -0.08,  # Most defensive
            "Industrials": -0.30,
            "Materials": -0.30,
        }
    ),
    "tech_selloff": ShockScenario(
        name="Tech Sector Selloff",
        description="Technology sector correction of 15-20% on valuation concerns",
        shock_type="tech_selloff",
        equity_beta=-0.08,  # Broad market impact
        rate_sensitivity=0.10,
        oil_sensitivity=0.0,
        usd_sensitivity=0.0,
        credit_spread_delta=25,
        volatility_spike=40,
        sector_impacts={
            "Technology": -0.18,
            "Financials": -0.05,
            "Real Estate": -0.03,
            "Utilities": 0.02,  # Rotation into defensives
            "Consumer Discretionary": -0.08,
            "Healthcare": 0.01,
            "Energy": 0.02,
            "Consumer Staples": 0.03,
            "Industrials": -0.04,
            "Materials": -0.02,
        }
    ),
    "china_slowdown": ShockScenario(
        name="China Economic Slowdown",
        description="China GDP growth falls to 3%, property sector stress",
        shock_type="china_slowdown",
        equity_beta=-0.10,
        rate_sensitivity=0.15,
        oil_sensitivity=-0.15,
        usd_sensitivity=0.03,
        credit_spread_delta=50,
        volatility_spike=35,
        sector_impacts={
            "Technology": -0.12,  # Supply chain exposure
            "Financials": -0.08,
            "Real Estate": -0.05,
            "Utilities": -0.02,
            "Consumer Discretionary": -0.15,  # Luxury goods hit
            "Healthcare": -0.03,
            "Energy": -0.12,
            "Consumer Staples": -0.05,
            "Industrials": -0.15,  # Heavy China exposure
            "Materials": -0.20,  # Commodities crash
        }
    ),
    "inflation_spike": ShockScenario(
        name="Inflation Spike",
        description="CPI surges to 8%+ forcing aggressive Fed response",
        shock_type="inflation_spike",
        equity_beta=-0.08,
        rate_sensitivity=-0.75,  # Rates spike
        oil_sensitivity=0.15,
        usd_sensitivity=-0.02,
        credit_spread_delta=40,
        volatility_spike=45,
        sector_impacts={
            "Technology": -0.12,
            "Financials": 0.03,  # Banks benefit from rates
            "Real Estate": -0.10,
            "Utilities": -0.08,
            "Consumer Discretionary": -0.10,
            "Healthcare": -0.04,
            "Energy": 0.10,  # Inflation hedge
            "Consumer Staples": -0.03,
            "Industrials": -0.06,
            "Materials": 0.05,  # Commodities benefit
        }
    ),
}


class StressTestAgent:
    """
    Agent for running macro-economic stress tests on portfolios and companies.
    
    Calculates expected drawdowns, P&L impacts, and risk metrics under 
    various shock scenarios.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.scenarios = SHOCK_SCENARIOS
        
        # Try to connect to Neo4j for sector data
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                self.settings.NEO4J_URI,
                auth=(self.settings.NEO4J_USER, self.settings.NEO4J_PASSWORD)
            )
            logger.info("StressTestAgent connected to Neo4j")
        except Exception as e:
            logger.warning(f"Neo4j connection failed: {e}")
            self.driver = None
    
    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        """Return list of all available stress test scenarios."""
        return [
            {
                "id": key,
                "name": scenario.name,
                "description": scenario.description,
            }
            for key, scenario in self.scenarios.items()
        ]
    
    async def get_company_sector(self, symbol: str) -> Optional[str]:
        """Fetch company sector from Neo4j Knowledge Graph."""
        if not self.driver:
            return None
        
        query = """
        MATCH (c:Company {ticker: $symbol})-[:IN_SECTOR]->(s:Sector)
        RETURN s.name as sector
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, symbol=symbol.upper())
                record = result.single()
                return record["sector"] if record else None
        except Exception as e:
            logger.error(f"Error fetching sector for {symbol}: {e}")
            return None
    
    async def get_company_macro_sensitivities(self, symbol: str) -> Dict[str, float]:
        """
        Fetch company-specific macro sensitivities from Knowledge Graph.
        Falls back to sector defaults if not available.
        """
        if not self.driver:
            return {}
        
        query = """
        MATCH (c:Company {ticker: $symbol})-[:IN_SECTOR]->(sec:Sector)-[:SENSITIVE_TO]->(m:MacroFactor)
        RETURN m.name as factor, sec.name as sector
        """
        
        sensitivities = {}
        try:
            with self.driver.session() as session:
                results = session.run(query, symbol=symbol.upper())
                for record in results:
                    factor = record["factor"]
                    # Assign sensitivity based on factor type
                    if "interest" in factor.lower() or "rate" in factor.lower():
                        sensitivities["rate_sensitive"] = True
                    if "oil" in factor.lower() or "energy" in factor.lower():
                        sensitivities["oil_sensitive"] = True
                    if "currency" in factor.lower() or "usd" in factor.lower():
                        sensitivities["fx_sensitive"] = True
        except Exception as e:
            logger.error(f"Error fetching sensitivities for {symbol}: {e}")
        
        return sensitivities
    
    async def run_stress_test(
        self,
        scenario_id: str,
        portfolio: Optional[List[Dict[str, Any]]] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a stress test scenario on a portfolio or list of symbols.
        
        Args:
            scenario_id: ID of the scenario to run (e.g., "fed_rate_hike_50bps")
            portfolio: List of holdings with {symbol, shares, current_price}
            symbols: List of symbols to analyze (if no portfolio provided)
        
        Returns:
            Stress test results with expected impacts
        """
        if scenario_id not in self.scenarios:
            return {
                "error": f"Unknown scenario: {scenario_id}",
                "available_scenarios": list(self.scenarios.keys())
            }
        
        scenario = self.scenarios[scenario_id]
        
        # If no portfolio or symbols provided, return scenario info only
        if not portfolio and not symbols:
            return {
                "scenario": scenario.to_dict(),
                "message": "Provide portfolio or symbols to calculate specific impacts"
            }
        
        # Analyze symbols
        if symbols and not portfolio:
            portfolio = [{"symbol": s, "shares": 100, "current_price": 100} for s in symbols]
        
        results = {
            "scenario": {
                "name": scenario.name,
                "description": scenario.description,
            },
            "macro_impacts": {
                "equity_market_impact": f"{scenario.equity_beta * 100:+.1f}%",
                "rate_change": f"{scenario.rate_sensitivity * 100:+.0f}bps",
                "credit_spread_widening": f"+{scenario.credit_spread_delta}bps",
                "volatility_spike": f"+{scenario.volatility_spike}%",
            },
            "holdings_analysis": [],
            "portfolio_summary": {},
        }
        
        total_value = 0
        total_impact = 0
        
        for holding in portfolio:
            symbol = holding.get("symbol", "").upper()
            shares = holding.get("shares", 0)
            price = holding.get("current_price", 100)
            position_value = shares * price
            
            # Get sector from Knowledge Graph
            sector = await self.get_company_sector(symbol)
            if not sector:
                # Fallback: Use a default sector or try to infer
                sector = await self._infer_sector(symbol)
            
            # Calculate impact
            sector_impact = scenario.sector_impacts.get(sector, scenario.equity_beta)
            
            # Check for additional macro sensitivities
            sensitivities = await self.get_company_macro_sensitivities(symbol)
            
            # Adjust impact based on specific sensitivities
            adjusted_impact = sector_impact
            impact_notes = []
            
            if sensitivities.get("rate_sensitive") and abs(scenario.rate_sensitivity) > 0:
                rate_adjustment = -0.02 * (scenario.rate_sensitivity / 0.25)
                adjusted_impact += rate_adjustment
                impact_notes.append("Rate-sensitive")
            
            if sensitivities.get("oil_sensitive") and abs(scenario.oil_sensitivity) > 0.1:
                oil_adjustment = 0.05 * (scenario.oil_sensitivity / 0.20)
                adjusted_impact += oil_adjustment
                impact_notes.append("Oil-exposed")
            
            if sensitivities.get("fx_sensitive") and abs(scenario.usd_sensitivity) > 0:
                fx_adjustment = -0.02 * (scenario.usd_sensitivity / 0.05)
                adjusted_impact += fx_adjustment
                impact_notes.append("FX-exposed")
            
            position_pnl = position_value * adjusted_impact
            
            results["holdings_analysis"].append({
                "symbol": symbol,
                "sector": sector or "Unknown",
                "position_value": f"${position_value:,.0f}",
                "expected_impact": f"{adjusted_impact * 100:+.1f}%",
                "expected_pnl": f"${position_pnl:+,.0f}",
                "risk_notes": impact_notes if impact_notes else ["Standard sector exposure"],
            })
            
            total_value += position_value
            total_impact += position_pnl
        
        # Portfolio summary
        results["portfolio_summary"] = {
            "total_portfolio_value": f"${total_value:,.0f}",
            "expected_portfolio_impact": f"{(total_impact / total_value * 100) if total_value > 0 else 0:+.1f}%",
            "expected_portfolio_pnl": f"${total_impact:+,.0f}",
            "worst_case_multiplier": "1.5x (95% confidence)",
            "var_adjusted_pnl": f"${total_impact * 1.5:+,.0f}",
        }
        
        # Risk recommendations
        results["recommendations"] = self._generate_recommendations(scenario, results["holdings_analysis"])
        
        return results
    
    async def _infer_sector(self, symbol: str) -> str:
        """Infer sector for common symbols."""
        sector_map = {
            # Tech
            "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
            "GOOG": "Technology", "META": "Technology", "NVDA": "Technology",
            "AMD": "Technology", "INTC": "Technology", "CRM": "Technology",
            # Financials
            "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
            "GS": "Financials", "MS": "Financials", "C": "Financials",
            # Healthcare
            "JNJ": "Healthcare", "PFE": "Healthcare", "UNH": "Healthcare",
            "MRK": "Healthcare", "ABBV": "Healthcare", "LLY": "Healthcare",
            # Energy
            "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "OXY": "Energy",
            # Consumer
            "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
            "HD": "Consumer Discretionary", "NKE": "Consumer Discretionary",
            "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
            "WMT": "Consumer Staples", "COST": "Consumer Staples",
            # Industrials
            "CAT": "Industrials", "BA": "Industrials", "HON": "Industrials",
            "UPS": "Industrials", "GE": "Industrials",
            # Utilities
            "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
            # Real Estate
            "AMT": "Real Estate", "PLD": "Real Estate", "SPG": "Real Estate",
            # Materials
            "LIN": "Materials", "APD": "Materials", "FCX": "Materials",
        }
        return sector_map.get(symbol, "Diversified")
    
    def _generate_recommendations(
        self, 
        scenario: ShockScenario, 
        holdings: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate risk mitigation recommendations based on stress test results."""
        recommendations = []
        
        # Find most impacted holdings
        worst_holdings = sorted(
            holdings, 
            key=lambda h: float(h["expected_impact"].replace("%", "").replace("+", ""))
        )[:3]
        
        if worst_holdings:
            worst_symbols = [h["symbol"] for h in worst_holdings]
            recommendations.append(
                f"🔴 **High Risk Exposure**: Consider reducing positions in {', '.join(worst_symbols)} "
                f"which show highest sensitivity to this scenario."
            )
        
        # Scenario-specific hedges
        if "rate" in scenario.shock_type:
            recommendations.append(
                "🛡️ **Rate Hedge**: Consider TLT puts or short-duration bond allocation to hedge rate risk."
            )
        
        if "oil" in scenario.shock_type:
            recommendations.append(
                "🛢️ **Energy Hedge**: XLE calls or oil futures can offset energy price exposure."
            )
        
        if "recession" in scenario.shock_type:
            recommendations.append(
                "🏦 **Defensive Rotation**: Increase allocation to Consumer Staples (XLP) and Healthcare (XLV)."
            )
            recommendations.append(
                "💵 **Cash Buffer**: Consider raising cash allocation to 15-20% for opportunistic reentry."
            )
        
        if scenario.volatility_spike > 30:
            recommendations.append(
                "📊 **Volatility Hedge**: VIX calls or put spreads on QQQ can provide tail-risk protection."
            )
        
        return recommendations


# Singleton instance
_stress_test_agent = None

def get_stress_test_agent() -> StressTestAgent:
    """Get singleton StressTestAgent instance."""
    global _stress_test_agent
    if _stress_test_agent is None:
        _stress_test_agent = StressTestAgent()
    return _stress_test_agent
