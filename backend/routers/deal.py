"""
Deal Intelligence REST endpoint — Phase 3.
"""
from fastapi import APIRouter, HTTPException

from backend.agents.deal import get_deal_agent
from backend.logger import get_logger
from backend.models import DealRequest

router = APIRouter()


@router.post("/api/deal/analyze")
async def analyze_deal(request: DealRequest):
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
    logger.separator(f"DEAL ANALYSIS REQUEST — {request.target_symbol}")

    try:
        agent = get_deal_agent()
        result = await agent.analyze(
            target_symbol=request.target_symbol,
            peer_symbols=request.peer_symbols,
            acquirer_market_share=request.acquirer_market_share,
            target_market_share=request.target_market_share,
            other_market_shares=request.other_market_shares,
            wacc=request.wacc,
            terminal_growth=request.terminal_growth,
            control_premium=request.control_premium,
        )

        # Flag when all valuations fell back to mock data
        dcf_source = result.get("valuations", {}).get("dcf", {}).get("data_source", "")
        if dcf_source == "mock":
            result["warning"] = (
                "Live financial data was unavailable for this ticker. "
                "All valuation figures are illustrative estimates only. "
                "Verify independently before use in a real transaction."
            )

        logger.separator(f"DEAL ANALYSIS COMPLETE — {request.target_symbol}")
        return result

    except Exception as e:
        logger.error("Deal analysis error", e)
        raise HTTPException(status_code=500, detail="Internal server error")
