"""
FastAPI application entry point — slim orchestrator.
All endpoint logic lives in backend/routers/.
"""

import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

import backend.cache as cache
import backend.state as state
import backend.db as db
from backend.config import get_settings
from backend.logger import get_logger
from backend.models import HealthResponse
from backend.routers import audit, chat, deal, portfolio, validation

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

settings = get_settings()
_DB_PATH = "memory.sqlite"

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger()
    logger.separator("AI BUSINESS ADVISOR - STARTUP")
    logger.system(f"Version : {settings.APP_VERSION}")
    logger.system(f"Model : {settings.MODEL_NAME}")
    logger.system(f"Debug : {settings.DEBUG}")

    try:
        state.db_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        state.checkpointer = SqliteSaver(state.db_conn)
        state.checkpointer.setup()
        logger.system(f"SQLite checkpointer ready at {_DB_PATH}")
    except Exception as e:
        logger.error("Failed to initialise SQLite checkpointer", e)

    # Initialise PostgreSQL connection pool (non-fatal if unavailable)
    await db.init_pool(settings.POSTGRES_URI)
    if db.is_available():
        logger.system("PostgreSQL pool ready — conversation history will persist.")
    else:
        logger.system("PostgreSQL unavailable — using in-memory history only.")

    # Initialise Redis cache (non-fatal if unavailable)
    await cache.init_redis()
    cache_status = await cache.get_cache_stats()
    if cache_status.get("enabled"):
        logger.system(f"Redis cache ready — {cache_status.get('total_keys', 0)} cached entries")
    else:
        logger.system("Redis unavailable — caching disabled")

    yield

    logger.separator("AI BUSINESS ADVISOR - SHUTDOWN")
    state.connections.clear()
    state.conversation_histories.clear()
    if state.db_conn:
        state.db_conn.close()
        logger.system("SQLite connection closed.")
    await db.close_pool()
    await cache.close_redis()
    logger.system("Goodbye!")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered business advisory chatbot with real-time web search.",
    lifespan=lifespan,
)

app.state.limiter = state.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(audit.router)
app.include_router(chat.router)
app.include_router(deal.router)
app.include_router(portfolio.router)
app.include_router(validation.router)

# ---------------------------------------------------------------------------
# Frontend Serving / Core routes
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    # Mount the frontend directory to serve the UI at the root
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    @app.get("/")
    @app.head("/")
    async def root():
        return {"status": "AI Business Advisor API is running (Frontend not found)"}

@app.get("/health", response_model=HealthResponse)
@app.head("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        model=settings.MODEL_NAME,
    )




# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )