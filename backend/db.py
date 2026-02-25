"""
PostgreSQL-backed conversation persistence for AI Business Advisor.
Replaces the in-memory conversation_histories dict with a durable store
so history survives restarts and scales across processes.

Schema (auto-created on first connect):
    sessions (session_id TEXT PK, created_at TIMESTAMPTZ, last_active TIMESTAMPTZ)
    messages  (id SERIAL PK, session_id TEXT FK, role TEXT, content TEXT,
               tool_call_id TEXT, created_at TIMESTAMPTZ)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger("advisor.db")

# Module-level pool (set in main.py lifespan via init_pool())
_pool = None

# Maximum conversation history window to return
_HISTORY_WINDOW = 10


async def init_pool(postgres_uri: str) -> None:
    """
    Create an asyncpg connection pool.
    Called once during application startup.
    """
    global _pool
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(postgres_uri, min_size=2, max_size=10)
        await _ensure_schema()
        logger.info("PostgreSQL connection pool initialised.")
    except Exception as e:
        logger.warning(
            f"PostgreSQL unavailable ({e}). Conversation history will not persist across restarts."
        )
        _pool = None


async def close_pool() -> None:
    """Drain and close the connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def is_available() -> bool:
    """Return True when the PostgreSQL pool is ready."""
    return _pool is not None


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

async def _ensure_schema() -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id  TEXT PRIMARY KEY,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_active TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS messages (
                id           SERIAL PRIMARY KEY,
                session_id   TEXT        NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                role         TEXT        NOT NULL,   -- human | ai | tool | system
                content      TEXT        NOT NULL,
                tool_call_id TEXT,                   -- populated for ToolMessage rows
                is_validation BOOLEAN    NOT NULL DEFAULT FALSE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id, created_at DESC);
        """)


# ---------------------------------------------------------------------------
# Public API — mirrors the in-memory dict interface used by the routers
# ---------------------------------------------------------------------------

async def get_history(session_id: str, validation: bool = False) -> List[BaseMessage]:
    """
    Retrieve the last _HISTORY_WINDOW messages for a session.
    Falls back to empty list if PostgreSQL is unavailable.
    """
    if not _pool:
        return []

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, tool_call_id
            FROM messages
            WHERE session_id = $1 AND is_validation = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            session_id,
            validation,
            _HISTORY_WINDOW,
        )

    # Rows come back newest-first; reverse for chronological order
    messages: List[BaseMessage] = []
    for row in reversed(rows):
        role, content, tool_call_id = row["role"], row["content"], row["tool_call_id"]
        if role == "human":
            messages.append(HumanMessage(content=content))
        elif role == "ai":
            messages.append(AIMessage(content=content))
        elif role == "tool":
            messages.append(ToolMessage(content=content, tool_call_id=tool_call_id or ""))
        elif role == "system":
            messages.append(SystemMessage(content=content))
    return messages


async def append_message(
    session_id: str,
    message: BaseMessage,
    validation: bool = False,
) -> None:
    """
    Persist a single message for a session.
    Silently no-ops if PostgreSQL is unavailable.
    """
    if not _pool:
        return

    role = _role_of(message)
    if role is None:
        return

    tool_call_id = getattr(message, "tool_call_id", None)
    content = str(message.content)

    async with _pool.acquire() as conn:
        # Upsert the session row first
        await conn.execute(
            """
            INSERT INTO sessions (session_id)
            VALUES ($1)
            ON CONFLICT (session_id) DO UPDATE SET last_active = NOW()
            """,
            session_id,
        )
        await conn.execute(
            """
            INSERT INTO messages (session_id, role, content, tool_call_id, is_validation)
            VALUES ($1, $2, $3, $4, $5)
            """,
            session_id,
            role,
            content,
            tool_call_id,
            validation,
        )


async def delete_session(session_id: str) -> None:
    """Remove all messages for a session (called on WebSocket disconnect)."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE session_id = $1", session_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _role_of(msg: BaseMessage) -> Optional[str]:
    if isinstance(msg, HumanMessage):
        return "human"
    if isinstance(msg, AIMessage):
        return "ai"
    if isinstance(msg, ToolMessage):
        return "tool"
    if isinstance(msg, SystemMessage):
        return "system"
    return None
