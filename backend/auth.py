"""
Authentication and Authorization middleware.
Secures endpoints via JWT if REQUIRE_AUTH is True.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Security, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.config import get_settings

security = HTTPBearer(auto_error=False)


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[str]:
    """
    Validates the JWT token if authentication is enabled.
    Returns the user ID (subject) or raises 401.
    If REQUIRE_AUTH is False, always returns "anonymous".
    """
    settings = get_settings()
    
    if not settings.REQUIRE_AUTH:
        return "anonymous"
        
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token structure")
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_ws(websocket: WebSocket) -> Optional[str]:
    """
    Extracts and validates JWT from WebSocket headers or query params.
    """
    settings = get_settings()
    if not settings.REQUIRE_AUTH:
        return "anonymous"

    # Try headers first (Sec-WebSocket-Protocol or Authorization)
    token = None
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # Fallback to query param
    if not token:
        token = websocket.query_params.get("token")
        
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token structure")
        return user_id
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")