"""
Portfolio analysis REST and WebSocket endpoints.
"""
import json
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.agents.portfolio import get_portfolio_agent
from backend.logger import get_logger
from backend.models import PortfolioRequest

router = APIRouter()


@router.post("/api/portfolio/analyze")
async def analyze_portfolio(request: PortfolioRequest):
    """
    Analyze a portfolio and return risk metrics, valuations, and projections.
    Holdings are now strictly validated via HoldingModel.
    """
    logger = get_logger()
    logger.separator("PORTFOLIO ANALYSIS REQUEST")

    try:
        agent   = get_portfolio_agent()
        # Convert validated Pydantic models back to dicts for the agent
        holdings_dicts = [h.model_dump() for h in request.holdings]
        result  = await agent.analyze_portfolio(holdings_dicts)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        # Warn the caller when mock / fallback data was used
        if result.get("data_source") == "mock":
            result["warning"] = (
                "Real-time market data was unavailable for one or more symbols. "
                "The figures shown are illustrative estimates, not live prices. "
                "Please verify independently before making investment decisions."
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Portfolio analysis error", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """Real-time portfolio update WebSocket."""
    logger = get_logger()
    await websocket.accept()
    session_id = str(id(websocket))
    logger.websocket_event("connect", "in", {"session_id": session_id, "type": "portfolio"})

    try:
        agent = get_portfolio_agent()

        while True:
            raw     = await websocket.receive_text()
            message = json.loads(raw)

            if message.get("action") == "analyze":
                raw_holdings = message.get("holdings", [])
                if not raw_holdings or len(raw_holdings) > 50:
                    await websocket.send_json({
                        "type":    "error",
                        "message": "holdings must be a list of 1–50 items.",
                    })
                    continue

                result = await agent.analyze_portfolio(raw_holdings)

                # Surface mock data warning on the WebSocket channel too
                if result.get("data_source") == "mock":
                    result["warning"] = (
                        "Real-time market data was unavailable. "
                        "Figures are illustrative only."
                    )

                await websocket.send_json({
                    "type":      "analysis_result",
                    "data":      result,
                    "timestamp": time.time(),
                })

    except WebSocketDisconnect:
        logger.system(f"Portfolio client {session_id} disconnected")
    except Exception as e:
        logger.error("Portfolio WS error", e)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass  # client may already be gone
