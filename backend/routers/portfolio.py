"""
Portfolio analysis REST and WebSocket endpoints.
"""
import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from backend.agents.portfolio import get_portfolio_agent
from backend.agents.risk import get_risk_agent
from backend.auth import get_current_user, get_current_user_ws
from backend.logger import get_logger
from backend.models import PortfolioRequest
from backend.quotas import verify_portfolio_quota
import backend.state as state

router = APIRouter()
limiter = state.limiter


@router.post("/api/portfolio/analyze")
@limiter.limit("5/minute")
async def analyze_portfolio(request: Request, portfolio_req: PortfolioRequest, user_id: str = Depends(verify_portfolio_quota)):
    """
    Analyze a portfolio and return risk metrics, valuations, and projections.
    Holdings are now strictly validated via HoldingModel.
    """
    logger = get_logger()
    logger.separator("PORTFOLIO ANALYSIS REQUEST")

    try:
        agent   = get_portfolio_agent()
        # Convert validated Pydantic models back to dicts for the agent
        holdings_dicts = [h.model_dump() for h in portfolio_req.holdings]
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
async def websocket_portfolio(websocket: WebSocket, user: str = Depends(get_current_user_ws)):
    """Real-time portfolio update WebSocket."""
    logger = get_logger()
    await websocket.accept()
    session_id = str(id(websocket))
    logger.websocket_event("connect", "in", {"session_id": session_id, "type": "portfolio"})
    
    monitor_task = None

    async def _monitor_loop(holdings, constraints):
        """Background task for continuous risk monitoring."""
        risk_agent = get_risk_agent()
        try:
            while True:
                logger.debug(f"Running scheduled risk check for {session_id}")
                result = await risk_agent.check_portfolio_risk(holdings, constraints)
                
                # Push alerts if any exist
                alerts = result.get("alerts", [])
                if alerts:
                    await websocket.send_json({
                        "type": "risk_alert",
                        "alerts": alerts,
                        "status": result.get("status"),
                        "hedging_suggestions": result.get("hedging_suggestions", []),
                        "timestamp": time.time(),
                    })
                
                # Push full update
                await websocket.send_json({
                    "type": "monitoring_update",
                    "data": result,
                    "timestamp": time.time(),
                })
                
                await asyncio.sleep(60)  # Check every 60 seconds
        except asyncio.CancelledError:
            logger.debug(f"Monitoring task cancelled for {session_id}")
        except Exception as e:
            logger.error("Error in monitoring loop", e)

    try:
        agent = get_portfolio_agent()

        while True:
            raw     = await websocket.receive_text()
            message = json.loads(raw)
            action  = message.get("action")

            if action == "analyze":
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
                
            elif action == "monitor":
                raw_holdings = message.get("holdings", [])
                constraints = message.get("constraints", {})
                
                if not raw_holdings or len(raw_holdings) > 50:
                    await websocket.send_json({"type": "error", "message": "Invalid holdings for monitoring."})
                    continue
                    
                if monitor_task:
                    monitor_task.cancel()
                    
                monitor_task = asyncio.create_task(_monitor_loop(raw_holdings, constraints))
                await websocket.send_json({"type": "system", "message": "Started portfolio monitoring."})
                
            elif action == "stop_monitor":
                if monitor_task:
                    monitor_task.cancel()
                    monitor_task = None
                await websocket.send_json({"type": "system", "message": "Stopped portfolio monitoring."})

    except WebSocketDisconnect:
        logger.system(f"Portfolio client {session_id} disconnected")
    except Exception as e:
        logger.error("Portfolio WS error", e)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass  # client may already be gone
    finally:
        if monitor_task:
            monitor_task.cancel()
