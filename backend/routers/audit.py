"""
Audit Analyst REST endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.agents.audit import get_audit_agent
from backend.agents.audit_data import get_audit_data_engine
from backend.auth import get_current_user
from backend.logger import get_logger
from backend.models import AuditRiskRequest, AuditDataRequest, AuditProgramRequest
from backend.quotas import verify_portfolio_quota
import backend.state as state

router = APIRouter()
limiter = state.limiter


@router.post("/api/audit/risk-assessment")
@limiter.limit("5/minute")
async def audit_risk_assessment(request: Request, req: AuditRiskRequest, user_id: str = Depends(verify_portfolio_quota)):
    """
    Compute audit risk and materiality from financial inputs.

    Returns:
      - Risk matrix (inherent, control, detection risk)
      - Materiality calculations using standard benchmarks
      - Recommended audit approach
      - SOX considerations (if applicable)
    """
    logger = get_logger()
    logger.separator("AUDIT RISK ASSESSMENT REQUEST")

    try:
        agent = get_audit_agent()
        result = await agent.assess_audit_risk(
            total_revenue=req.total_revenue,
            total_assets=req.total_assets,
            pre_tax_income=req.pre_tax_income,
            gross_profit=req.gross_profit,
            inherent_risk=req.inherent_risk,
            control_risk=req.control_risk,
            industry=req.industry,
            is_public_company=req.is_public_company,
        )

        logger.separator("AUDIT RISK ASSESSMENT COMPLETE")
        return result

    except Exception as e:
        logger.error("Audit risk assessment error", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/audit/analyze-data")
@limiter.limit("5/minute")
async def analyze_audit_data(request: Request, req: AuditDataRequest, user_id: str = Depends(verify_portfolio_quota)):
    """
    Run audit data analytics on uploaded CSV data.

    Supports: full profiling, duplicates, Benford's Law, gap analysis,
    aging, stratified sampling, journal entry testing, three-way matching.
    """
    logger = get_logger()
    logger.separator(f"AUDIT DATA ANALYSIS REQUEST — {req.analysis_type}")

    try:
        engine = get_audit_data_engine()

        analysis_map = {
            "full": lambda: engine.analyze_dataset(
                req.csv_data,
                req.column_config.get("amount_column") if req.column_config else None,
            ),
            "duplicates": lambda: engine.detect_duplicates(req.csv_data),
            "benford": lambda: engine.benford_analysis(
                req.csv_data,
                (req.column_config or {}).get("column", "amount"),
            ),
            "gaps": lambda: engine.gap_analysis(
                req.csv_data,
                (req.column_config or {}).get("column", "invoice_number"),
            ),
            "aging": lambda: engine.aging_analysis(
                req.csv_data,
                (req.column_config or {}).get("date_column", "date"),
                (req.column_config or {}).get("amount_column", "amount"),
            ),
            "sample": lambda: engine.stratified_sample(
                req.csv_data,
                (req.column_config or {}).get("amount_column", "amount"),
            ),
            "journal_entries": lambda: engine.journal_entry_testing(
                req.csv_data,
                (req.column_config or {}).get("amount_column", "amount"),
                (req.column_config or {}).get("date_column", "date"),
            ),
            "three_way_match": lambda: engine.three_way_match(req.csv_data),
        }

        coro_fn = analysis_map.get(req.analysis_type, analysis_map["full"])
        result = await coro_fn()

        logger.separator(f"AUDIT DATA ANALYSIS COMPLETE — {req.analysis_type}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Audit data analysis error", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/audit/generate-program")
@limiter.limit("5/minute")
async def generate_audit_program(request: Request, req: AuditProgramRequest, user_id: str = Depends(verify_portfolio_quota)):
    """
    Generate a structured audit program for the specified area.

    Returns:
      - Audit objectives
      - Key assertions
      - Detailed procedures with types
      - SOX-specific procedures (if applicable)
      - Sample size guidance
    """
    logger = get_logger()
    logger.separator(f"AUDIT PROGRAM REQUEST — {req.audit_area}")

    try:
        agent = get_audit_agent()
        result = await agent.generate_audit_program(
            audit_area=req.audit_area,
            industry=req.industry,
            is_sox=req.is_sox,
            risk_level=req.risk_level,
        )

        logger.separator(f"AUDIT PROGRAM COMPLETE — {req.audit_area}")
        return result

    except Exception as e:
        logger.error("Audit program generation error", e)
        raise HTTPException(status_code=500, detail="Internal server error")
