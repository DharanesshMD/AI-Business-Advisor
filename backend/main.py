"""
FastAPI application entry point — slim orchestrator.
All endpoint logic lives in backend/routers/.
"""

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver

import backend.state as state
import backend.db as db
from backend.config import get_settings
from backend.logger import get_logger
from backend.models import HealthResponse
from backend.routers import chat, portfolio, validation

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

settings = get_settings()
_DB_PATH  = "memory.sqlite"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger()
    logger.separator("AI BUSINESS ADVISOR - STARTUP")
    logger.system(f"Version : {settings.APP_VERSION}")
    logger.system(f"Model   : {settings.MODEL_NAME}")
    logger.system(f"Debug   : {settings.DEBUG}")

    try:
        state.db_conn      = sqlite3.connect(_DB_PATH, check_same_thread=False)
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

    yield

    logger.separator("AI BUSINESS ADVISOR - SHUTDOWN")
    state.connections.clear()
    state.conversation_histories.clear()
    if state.db_conn:
        state.db_conn.close()
        logger.system("SQLite connection closed.")
    await db.close_pool()
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

app.include_router(chat.router)
app.include_router(portfolio.router)
app.include_router(validation.router)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse("frontend/index.html")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        model=settings.MODEL_NAME,
    )


# Mount static files (non-fatal if frontend dir is absent)
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except Exception:
    pass


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
