"""
Deal Intelligence REST endpoint — Phase 3.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.agents.deal import get_deal_agent
from backend.auth import get_current_user
from backend.logger import get_logger
from backend.models import DealRequest
import backend.state as state

router = APIRouter()
limiter = state.limiter


@router.post("/api/deal/analyze")
@limiter.limit("5/minute")
async def analyze_deal(request: Request, deal_req: DealRequest, user: str = Depends(get_current_user)):
    """
    Run M&A deal intelligence analysis for a target company.

    Returns:
      - Company snapshot
      - DCF intrinsic value
      - Comparable-companies valuation
      - Precedent-transactions price estimate
      - HHI regulatory risk assessment
      - Overall verdict (valuation signal + regulatory risk + summary)
    """
    logger = get_logger()
    logger.separator(f"DEAL ANALYSIS REQUEST — {deal_req.target_symbol}")

    try:
        agent = get_deal_agent()
        result = await agent.analyze(
            target_symbol=deal_req.target_symbol,
            peer_symbols=deal_req.peer_symbols,
            acquirer_market_share=deal_req.acquirer_market_share,
            target_market_share=deal_req.target_market_share,
            other_market_shares=deal_req.other_market_shares,
            wacc=deal_req.wacc,
            terminal_growth=deal_req.terminal_growth,
            control_premium=deal_req.control_premium,
        )

        # Flag when all valuations fell back to mock data
        dcf_source = result.get("valuations", {}).get("dcf", {}).get("data_source", "")
        if dcf_source == "mock":
            result["warning"] = (
                "Live financial data was unavailable for this ticker. "
                "All valuation figures are illustrative estimates only. "
                "Verify independently before use in a real transaction."
            )

        logger.separator(f"DEAL ANALYSIS COMPLETE — {deal_req.target_symbol}")
        return result

    except Exception as e:
        logger.error("Deal analysis error", e)
        raise HTTPException(status_code=500, detail="Internal server error")
