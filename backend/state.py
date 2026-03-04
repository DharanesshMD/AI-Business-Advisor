"""
Shared application state for AI Business Advisor.
Centralises mutable state so it can be imported by routers without circular dependencies.
"""
from typing import Any, Dict, List, Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

def _rate_limit_key_func(request: Any) -> str:
    """
    Use authenticated user ID if present, otherwise fallback to IP address.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id and user_id != "anonymous":
        return f"user:{user_id}"
    return get_remote_address(request)


# Active WebSocket connections:  session_id -> WebSocket
connections: Dict[str, Any] = {}

# Conversation histories:  session_id -> list[BaseMessage]
#   A parallel key  "<session_id>_validation" stores untruncated ToolMessages.
conversation_histories: Dict[str, List[Any]] = {}

# LangGraph SQLite checkpointer (set during app lifespan startup)
checkpointer: Optional[Any] = None

# Raw SQLite connection kept alive for the checkpointer
db_conn: Optional[Any] = None

# Global rate limiter
limiter = Limiter(key_func=_rate_limit_key_func)
