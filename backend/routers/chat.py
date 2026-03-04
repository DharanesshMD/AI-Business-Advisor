"""
REST and WebSocket chat endpoints.
"""
import asyncio
import contextvars
import json
import re
import time
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from backend.agents.graph import create_advisor_graph
from backend.agents.tools import set_search_provider
from backend.auth import get_current_user, get_current_user_ws
from backend.cache import get_cached_response, set_cached_response
from backend.config import get_settings
import backend.db as db
from backend.logger import get_logger
from backend.models import ChatRequest, ChatResponse
from backend.quotas import verify_chat_quota
import backend.state as state

router = APIRouter()
settings = get_settings()
limiter = state.limiter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATEGORY_MAP = {
    "initialization":       {"icon": "⚙️",  "label": "Initializing"},
    "prompt_preparation":   {"icon": "📝",  "label": "Preparing Query"},
    "api_call":             {"icon": "🌐",  "label": "Connecting to AI"},
    "tool_decision":        {"icon": "🔍",  "label": "Deciding to Search"},
    "tool_start":           {"icon": "🔎",  "label": "Searching Web"},
    "tool_end":             {"icon": "✅",  "label": "Search Complete"},
    "response_received":    {"icon": "💬",  "label": "Processing Response"},
    "response_generation":  {"icon": "✍️",  "label": "Generating Answer"},
    "thinking":             {"icon": "💭",  "label": "Analyzing"},
    "graph_step":           {"icon": "▶️",  "label": "Processing"},
}

_REPLACEMENTS = {
    "Creating advisor graph":       "Setting up AI advisor...",
    "Starting graph stream execution": "Starting analysis...",
    "Running graph in executor":    "Processing your question...",
    "Graph execution completed":    "Analysis complete",
    "Model decided to call":        "Searching for",
    "Tool call START":              "Starting search",
    "Tool call END":                "Search finished",
    "Formatted result length":      "Retrieved information",
    "chat/completions":             "AI model",
    "NVIDIA NIM":                   "AI Service",
    "Perplexity":                   "Web Search (Perplexity)",
}

_CLEAN_PATTERNS = [
    (re.compile(r"<\|python_?tag\|>.*",           re.DOTALL | re.IGNORECASE), ""),
    (re.compile(r"<function.*?(?:</function>|$)", re.DOTALL | re.IGNORECASE), ""),
    (re.compile(r'\{"query":\s*"[^"]*"[^}]*\}'),                              ""),
    (re.compile(r"websearch|web_search|search_regulations", re.IGNORECASE),   ""),
    (re.compile(r"<\|[^|]*\|>"),                                              ""),
]


def _sanitize_log(entry: dict) -> dict:
    category = entry.get("category", "")
    message  = entry.get("message", "").replace("\\", "/")
    for old, new in _REPLACEMENTS.items():
        message = message.replace(old, new)
    mapped = _CATEGORY_MAP.get(category, {"icon": "💭", "label": "Thinking"})
    return {"icon": mapped["icon"], "label": mapped["label"],
            "message": message, "timestamp": entry.get("timestamp")}


def _clean_response(text: str) -> str:
    for pattern, repl in _CLEAN_PATTERNS:
        text = pattern.sub(repl, text)
    return text.strip()


class _ThinkingCollector:
    def __init__(self):
        self.logs: list = []
        self._lock = threading.Lock()

    def add(self, category: str, message: str) -> None:
        with self._lock:
            self.logs.append({"timestamp": time.time(),
                               "category": category, "message": message})

    def since(self, idx: int) -> list:
        with self._lock:
            return self.logs[idx:]


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@router.post("/api/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, chat_req: ChatRequest, user_id: str = Depends(verify_chat_quota)):
    """Synchronous (non-streaming) chat endpoint with LLM response caching."""
    logger = get_logger()
    request_id = logger.new_request()
    location = chat_req.location or "India"

    logger.separator(f"REST API CHAT REQUEST #{request_id}")
    logger.user_input(chat_req.message, location)

    session_id = chat_req.session_id or str(id(chat_req))
    logger.debug(f"Session: {session_id}")

    # Check cache for exact query match
    cached = await get_cached_response(chat_req.message)
    if cached:
        logger.debug(f"Cache HIT - returning cached response")
        return ChatResponse(
            response=cached.get("content", ""),
            session_id=session_id,
        )

    try:
        graph = create_advisor_graph(location, checkpointer=state.checkpointer)
        config = {"configurable": {"thread_id": session_id}}
        result = graph.invoke(
            {"messages": [HumanMessage(content=chat_req.message)], "location": location},
            config,
        )

        response = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                response = str(msg.content)
                break

        # Cache simple responses (no tool calls) for 1 hour
        if response and not any(isinstance(m, ToolMessage) for m in result.get("messages", [])):
            await set_cached_response(chat_req.message, {"content": response}, ttl_seconds=3600)

        # Persist to PostgreSQL (no-op if unavailable)
        await db.append_message(session_id, HumanMessage(content=chat_req.message))
        if response:
            await db.append_message(session_id, AIMessage(content=response))

        logger.separator(f"REST API CHAT COMPLETE #{request_id}")
        return ChatResponse(response=response, session_id=session_id)

    except Exception as e:
        logger.error("Chat endpoint error", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, user: str = Depends(get_current_user_ws)):
    """Streaming WebSocket chat endpoint."""
    logger = get_logger()
    await websocket.accept()

    session_id = str(id(websocket))
    state.connections[session_id] = websocket

    # Seed in-memory history from PostgreSQL (empty list if DB unavailable)
    db_history = await db.get_history(session_id)
    state.conversation_histories[session_id] = db_history

    logger.set_session(session_id)
    logger.separator("WEBSOCKET CONNECTION ESTABLISHED")
    logger.websocket_event("connect", "in", {"session_id": session_id})

    async def _send_thinking(category: str, message: str) -> None:
        entry = {"timestamp": time.time(), "category": category, "message": message}
        try:
            await websocket.send_json({"type": "thinking", "content": _sanitize_log(entry)})
        except Exception:
            pass  # Non-fatal: don't break the main loop on a failed log send

    try:
        await websocket.send_json({
            "type": "system",
            "content": "Connected to ARIA - AI Business Advisor. How can I help you today?",
            "session_id": session_id,
        })

        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)
            logger.websocket_event(data.get("type", "unknown"), "in", data)

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if data.get("type") != "message":
                continue

            # --- unpack & validate incoming message ---
            user_message    = str(data.get("content", "")).strip()
            location        = str(data.get("location", "India"))[:100]
            search_provider = str(data.get("search_provider", "tavily"))
            if search_provider not in {"tavily", "perplexity", "duckduckgo", "auto"}:
                search_provider = "tavily"

            if not user_message:
                continue

            # message length guard (4 000 chars matches ChatRequest)
            if len(user_message) > 4_000:
                await websocket.send_json({
                    "type": "error",
                    "content": "Message too long. Please keep messages under 4 000 characters.",
                })
                continue

            request_id = logger.new_request()
            logger.separator(f"WEBSOCKET CHAT REQUEST #{request_id}")
            logger.user_input(user_message, location)
            logger.debug(f"Search provider: {search_provider}")

            set_search_provider(search_provider)

            history = state.conversation_histories.get(session_id, [])
            history.append(HumanMessage(content=user_message))

            await websocket.send_json({"type": "typing", "content": True})

            thinking   = _ThinkingCollector()
            full_response      = ""
            tool_messages      = []
            tool_queries       = []
            fact_check_report  = None

            try:
                start_time = time.time()
                await _send_thinking("initialization", "Starting analysis of your question...")
                await asyncio.sleep(0.1)
                await _send_thinking("initialization", f"Location context: {location}")
                await asyncio.sleep(0.1)
                await _send_thinking("api_call", "Connecting to NVIDIA AI service...")
                await asyncio.sleep(0.1)
                await _send_thinking("prompt_preparation", f'Analyzing: "{user_message[:50]}..."')
                await asyncio.sleep(0.1)

                graph  = create_advisor_graph(location, checkpointer=state.checkpointer)
                config = {"configurable": {"thread_id": session_id}}
                ctx    = contextvars.copy_context()
                loop   = asyncio.get_event_loop()

                def _run_graph():
                    nonlocal full_response, tool_messages, tool_queries, fact_check_report
                    _fc_report = None
                    for step in graph.stream({"messages": history, "location": location}, config):
                        for node_name, output in step.items():
                            if node_name == "tools":
                                for msg in output.get("messages", []):
                                    if isinstance(msg, ToolMessage):
                                        tool_messages.append(msg)
                                    if hasattr(msg, "content"):
                                        preview = str(msg.content)[:100]
                                        thinking.add("tool_end", f"Retrieved: {preview}...")

                            elif node_name == "agent":
                                for msg in output.get("messages", []):
                                    if isinstance(msg, AIMessage):
                                        if msg.tool_calls:
                                            for tc in msg.tool_calls:
                                                args  = tc.get("args", {})
                                                query = args.get("query", args.get("topic", str(args)))
                                                tool_queries.append({"tool": tc["name"], "query": query})
                                                thinking.add("tool_decision", f"Deciding to search: {tc['name']}")
                                                thinking.add("tool_start", f"Searching for: {str(query)[:80]}...")
                                        elif msg.content:
                                            full_response = str(msg.content)
                                            thinking.add("response_generation",
                                                         f"Generated response ({len(full_response)} chars)")

                            elif node_name == "fact_check":
                                for msg in output.get("messages", []):
                                    if isinstance(msg, SystemMessage):
                                        try:
                                            fc_data = json.loads(str(msg.content))
                                            if fc_data.get("type") == "fact_check":
                                                _fc_report = fc_data.get("report")
                                        except (json.JSONDecodeError, TypeError, ValueError):
                                            pass
                    fact_check_report = _fc_report
                    return full_response

                graph_task = loop.run_in_executor(None, ctx.run, _run_graph)

                # Stream thinking logs while graph runs
                last_idx = 0
                while not graph_task.done():
                    new_logs = thinking.since(last_idx)
                    for log in new_logs:
                        await websocket.send_json({"type": "thinking",
                                                   "content": _sanitize_log(log)})
                    last_idx += len(new_logs)
                    await asyncio.sleep(0.1)

                await graph_task  # ensure exceptions surface

                # Flush remaining logs
                for log in thinking.since(last_idx):
                    await websocket.send_json({"type": "thinking",
                                               "content": _sanitize_log(log)})

                elapsed_ms = (time.time() - start_time) * 1000
                await _send_thinking("response_received", f"Analysis complete ({elapsed_ms:.0f}ms)")

                # Send tool statuses
                for tq in tool_queries:
                    await websocket.send_json({
                        "type":    "tool_status",
                        "status":  "complete",
                        "tool":    tq["tool"],
                        "query":   tq["query"][:100],
                        "content": f"🔍 Searched via {search_provider.capitalize()}: {tq['query'][:60]}...",
                    })

                # Stream response
                clean = _clean_response(full_response)
                if clean:
                    await websocket.send_json({"type": "thinking_done", "content": ""})
                    for i in range(0, len(clean), 20):
                        await websocket.send_json({"type": "token", "content": clean[i:i + 20]})
                        await asyncio.sleep(0.02)
                    full_response = clean

                # Send fact-check report if any
                if fact_check_report:
                    await websocket.send_json({"type": "fact_check", "content": fact_check_report})

            except Exception as e:
                import traceback
                logger.error("Error during graph execution", e)
                logger.debug(f"Traceback: {traceback.format_exc()}")
                await websocket.send_json({"type": "error",
                                           "content": "An error occurred while generating a response."})
                continue

            # Done signal
            await websocket.send_json({"type": "done", "content": ""})
            logger.separator(f"WEBSOCKET CHAT COMPLETE #{request_id}")

            # Update history (in-memory + PostgreSQL)
            if full_response:
                val_key = f"{session_id}_validation"
                val_hist = state.conversation_histories.setdefault(val_key, [])
                val_hist.extend(tool_messages)
                state.conversation_histories[val_key] = val_hist[-10:]

                # Persist human message
                await db.append_message(session_id, HumanMessage(content=user_message))

                for tm in tool_messages:
                    trunc = (tm.content[:500] + "... [truncated]"
                             if len(tm.content) > 500 else tm.content)
                    truncated_tm = ToolMessage(content=trunc, tool_call_id=tm.tool_call_id)
                    history.append(truncated_tm)
                    await db.append_message(session_id, truncated_tm)
                    await db.append_message(val_key, tm, validation=True)

                ai_msg = AIMessage(content=full_response)
                history.append(ai_msg)
                await db.append_message(session_id, ai_msg)
                state.conversation_histories[session_id] = history[-10:]

    except WebSocketDisconnect:
        logger.system(f"Client {session_id} disconnected")
    except Exception as e:
        logger.error("WebSocket error", e)
    finally:
        state.connections.pop(session_id, None)
        state.conversation_histories.pop(session_id, None)
        state.conversation_histories.pop(f"{session_id}_validation", None)
        logger.debug(f"Session {session_id} cleaned up.")
