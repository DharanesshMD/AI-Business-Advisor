"""
Risk Management Agent for ARIA.
Monitors portfolio risk metrics and alerts on anomalies or constraint violations.
"""

import logging
from typing import Dict, List, Any
import numpy as np

from backend.agents.portfolio import get_portfolio_agent

logger = logging.getLogger("advisor.risk")

class RiskAgent:
    """
    Agent responsible for operational risk monitoring and hedging advice.
    """
    
    def __init__(self):
        self.portfolio_agent = get_portfolio_agent()

    async def check_portfolio_risk(self, holdings: List[Dict], constraints: Dict[str, float] = None) -> Dict[str, Any]:
        """
        Analyze portfolio risk against constraints.
        
        Constraints Example:
        {
            "max_var_95": 0.05,        # Max daily VaR 5%
            "min_sharpe": 1.0,         # Minimum acceptable Sharpe
            "max_single_position": 0.25 # Max 25% in one asset
        }
        """
        constraints = constraints or {}
        
        # 1. Get base analytics
        analysis = await self.portfolio_agent.analyze_portfolio(holdings)
        
        if "error" in analysis:
            return analysis
            
        metrics = analysis.get("metrics", {})
        risk_metrics = analysis.get("risk", {})
        valid_holdings = analysis.get("holdings", [])
        
        alerts = []
        status = "Healthy"
        
        # 2. Check Constraints
        
        # VaR Check
        current_var = risk_metrics.get("var_95", 0)
        max_var = constraints.get("max_var_95", 0.05)
        if current_var > max_var:
            alerts.append({
                "type": "High Risk",
                "message": f"Portfolio VaR ({current_var:.2%}) exceeds limit ({max_var:.2%}).",
                "rec": "Consider diversifying or adding hedges."
            })
            status = "Warning"
            
        # Sharpe Check
        current_sharpe = metrics.get("sharpe_ratio", 0)
        min_sharpe = constraints.get("min_sharpe", 0.5)
        if current_sharpe < min_sharpe:
            alerts.append({
                "type": "Low Performance",
                "message": f"Sharpe Ratio ({current_sharpe}) is below threshold ({min_sharpe}).",
                "rec": "Review underperforming assets."
            })
            
        # Concentration Risk
        max_pos_limit = constraints.get("max_single_position", 0.40)
        for h in valid_holdings:
            weight = h.get("weight", 0)
            if weight > max_pos_limit:
                alerts.append({
                    "type": "Concentration Risk",
                    "message": f"Position {h['symbol']} constitutes {weight:.1%} of portfolio.",
                    "rec": f"Reduce {h['symbol']} exposure to below {max_pos_limit:.0%}."
                })
                status = "Warning"
                
        # 3. Generate Hedging Recommendations (Simple Logic)
        hedging_suggestions = []
        if status == "Warning" or current_var > 0.03:
            hedging_suggestions.append("Consider buying protective puts on major customized indices.")
            if any(h['weight'] > 0.3 for h in valid_holdings):
                hedging_suggestions.append("Use collar strategy for concentrated positions.")
        
        return {
            "status": status,
            "alerts": alerts,
            "metrics": {
                "var_metrics": risk_metrics,
                "perf_metrics": metrics
            },
            "hedging_suggestions": hedging_suggestions
        }

_risk_agent = None
def get_risk_agent():
    global _risk_agent
    if _risk_agent is None:
        _risk_agent = RiskAgent()
    return _risk_agent
