"""
Response validation endpoint.
"""
from fastapi import APIRouter, Depends, Request
from langchain_core.messages import ToolMessage

from backend.agents.validator import ResponseValidator
from backend.auth import get_current_user
from backend.logger import get_logger
from backend.models import ValidateRequest
import backend.state as state

router = APIRouter()
limiter = state.limiter

# True singleton — reuse the same instance across requests
_validator: ResponseValidator | None = None


def _get_validator() -> ResponseValidator:
    global _validator
    if _validator is None:
        _validator = ResponseValidator()
    return _validator


@router.post("/api/validate")
@limiter.limit("5/minute")
async def validate_response(request: Request, validate_req: ValidateRequest, user: str = Depends(get_current_user)):
    """Manually validate an AI response for factual consistency against tool data."""
    logger = get_logger()
    logger.separator("MANUAL VALIDATION REQUEST")

    history     = state.conversation_histories.get(validate_req.session_id, [])
    val_history = state.conversation_histories.get(f"{validate_req.session_id}_validation", [])

    combined = val_history + [m for m in history if not isinstance(m, ToolMessage)]

    if not combined:
        logger.debug(f"No history found for session {validate_req.session_id}")
        return {"is_valid": True, "message": "No history available for validation."}

    validator = _get_validator()
    logger.debug(
        f"Validating message (len={len(validate_req.message_content)}): "
        f"{validate_req.message_content[:200]}..."
    )
    report = validator.validate_structured(validate_req.message_content, combined)

    if report["is_valid"]:
        logger.system("Manual validation: PASSED")
    else:
        logger.tool_call_error("validator", "Manual validation: FAILED")

    return report
