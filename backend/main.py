"""
FastAPI Backend for AI Business Advisor.
Provides WebSocket streaming and REST API endpoints.
"""

import json
import asyncio
import time
import queue
import threading
import contextvars
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from backend.config import get_settings
from backend.agents.graph import create_advisor_graph
from backend.agents.tools import set_search_provider
from backend.agents.portfolio import get_portfolio_agent
from backend.logger import get_logger


# Store active connections and their conversation history
connections: dict = {}
conversation_histories: dict = {}


class ThinkingLogCollector:
    """Collects thinking logs during graph execution for streaming to UI."""
    
    def __init__(self):
        self.logs = []
        self.lock = threading.Lock()
    
    def add(self, category: str, message: str, details: dict = None):
        """Add a thinking log entry."""
        with self.lock:
            entry = {
                "timestamp": time.time(),
                "category": category,
                "message": message,
                "details": details or {}
            }
            self.logs.append(entry)
    
    def get_new_logs(self, since_index: int = 0) -> list:
        """Get logs added since the given index."""
        with self.lock:
            return self.logs[since_index:]
    
    def get_all(self) -> list:
        """Get all collected logs."""
        with self.lock:
            return self.logs.copy()
    
    def clear(self):
        """Clear all logs."""
        with self.lock:
            self.logs = []


def sanitize_log_for_ui(log_entry: dict) -> dict:
    """Sanitize a log entry for display in the UI."""
    category = log_entry.get("category", "")
    message = log_entry.get("message", "")
    details = log_entry.get("details", {})
    
    # Map internal categories to user-friendly labels
    category_map = {
        "initialization": {"icon": "⚙️", "label": "Initializing"},
        "prompt_preparation": {"icon": "📝", "label": "Preparing Query"},
        "api_call": {"icon": "🌐", "label": "Connecting to AI"},
        "tool_decision": {"icon": "🔍", "label": "Deciding to Search"},
        "tool_start": {"icon": "🔎", "label": "Searching Web"},
        "tool_end": {"icon": "✅", "label": "Search Complete"},
        "response_received": {"icon": "💬", "label": "Processing Response"},
        "response_generation": {"icon": "✍️", "label": "Generating Answer"},
        "thinking": {"icon": "💭", "label": "Analyzing"},
        "graph_step": {"icon": "▶️", "label": "Processing"},
    }
    
    mapped = category_map.get(category, {"icon": "💭", "label": "Thinking"})
    
    # Sanitize the message - remove technical jargon
    sanitized_message = message
    
    # Remove file paths
    sanitized_message = sanitized_message.replace("\\", "/")
    
    # Make messages more user-friendly
    replacements = {
        "Creating advisor graph": "Setting up AI advisor...",
        "Starting graph stream execution": "Starting analysis...",
        "Running graph in executor": "Processing your question...",
        "Graph execution completed": "Analysis complete",
        "Model decided to call": "Searching for",
        "Tool call START": "Starting search",
        "Tool call END": "Search finished",
        "Formatted result length": "Retrieved information",
        "chat/completions": "AI model",
        "NVIDIA NIM": "AI Service",
        "Perplexity": "Web Search (Perplexity)",
    }
    
    for old, new in replacements.items():
        sanitized_message = sanitized_message.replace(old, new)
    
    return {
        "icon": mapped["icon"],
        "label": mapped["label"],
        "message": sanitized_message,
        "timestamp": log_entry.get("timestamp"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger = get_logger()
    logger.separator("AI BUSINESS ADVISOR - STARTUP")
    logger.system("Application starting up...")
    logger.system(f"Version: {settings.APP_VERSION}")
    logger.system(f"Model: {settings.MODEL_NAME}")
    logger.system(f"Debug Mode: {settings.DEBUG}")
    yield
    logger.separator("AI BUSINESS ADVISOR - SHUTDOWN")
    logger.system("Application shutting down...")
    logger.system(f"Active connections being closed: {len(connections)}")
    connections.clear()
    conversation_histories.clear()
    logger.system("Cleanup complete. Goodbye!")


# Initialize FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered business advisory chatbot with real-time web search and location-aware regulations",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MVP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    location: Optional[str] = "India"
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    session_id: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    model: str


class PortfolioRequest(BaseModel):
    """Request for portfolio analysis."""
    holdings: list[dict] # List of {'symbol': str, 'quantity': float, 'purchase_price': float}
    simulations: int = 1000
    days: int = 30


class ValidateRequest(BaseModel):
    """Request to validate a specific AI response."""
    message_content: str
    session_id: str


# REST Endpoints
@app.get("/", response_class=FileResponse)
async def serve_frontend():
    """Serve the frontend HTML."""
    return FileResponse("frontend/index.html")


@app.post("/api/validate")
async def validate_response(request: ValidateRequest):
    """
    Manually validate an AI response for consistency.
    """
    from backend.agents.validator import get_validator
    
    logger = get_logger()
    logger.separator(f"MANUAL VALIDATION REQUEST")
    
    # Get conversation history for this session to find ground truth (tool outputs)
    history = conversation_histories.get(request.session_id, [])
    
    if not history:
        logger.debug(f"No history found for session {request.session_id}")
        return {"is_valid": True, "message": "No history available for validation."}
    
    validator = get_validator()
    logger.debug(f"Validating message (len={len(request.message_content)}): {request.message_content[:200]}...")
    report = validator.validate_structured(request.message_content, history)
    
    if report["is_valid"]:
        logger.system("Manual validation: PASSED")
    else:
        logger.tool_call_error("validator", "Manual validation: FAILED")
        
    return report


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    logger = get_logger()
    logger.debug("Health check requested")
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        model=settings.MODEL_NAME
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Synchronous chat endpoint (non-streaming).
    Use WebSocket for streaming responses.
    """
    logger = get_logger()
    request_id = logger.new_request()
    
    logger.separator(f"REST API CHAT REQUEST #{request_id}")
    logger.user_input(request.message, request.location)
    
    session_id = request.session_id or str(id(request))
    history = conversation_histories.get(session_id, [])
    
    logger.debug(f"Session: {session_id}, History length: {len(history)}")
    
    try:
        start_time = time.time()
        
        graph = create_advisor_graph(request.location)
        history.append(HumanMessage(content=request.message))
        
        logger.model_thinking("graph_invoke", "Starting synchronous graph execution")
        
        result = graph.invoke({
            "messages": history,
            "location": request.location
        })
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Get the final response
        response = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                response = msg.content
                break
        
        logger.ai_response(response)
        logger.debug(f"Total request time: {duration_ms:.0f}ms")
        
        # Update history
        history.append(AIMessage(content=response))
        conversation_histories[session_id] = history[-20:]  # Keep last 20 messages
        
        logger.separator(f"REST API CHAT COMPLETE #{request_id}")
        
        return ChatResponse(response=response, session_id=session_id)
    
    except Exception as e:
        logger.error("Chat endpoint error", e)
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket Endpoint for Streaming
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat responses.
    
    Expected message format:
    {
        "type": "message",
        "content": "user message",
        "location": "India"  # optional
    }
    
    Response message types:
    - system: System messages
    - typing: Typing indicator
    - thinking: ARIA's thinking process logs for UI display
    - tool_status: Tool usage status
    - token: Response tokens
    - done: Completion signal
    - error: Error messages
    """
    logger = get_logger()
    
    await websocket.accept()
    session_id = str(id(websocket))
    connections[session_id] = websocket
    conversation_histories[session_id] = []
    
    logger.set_session(session_id)
    logger.separator(f"WEBSOCKET CONNECTION ESTABLISHED")
    logger.websocket_event("connect", "in", {"session_id": session_id})
    logger.debug(f"Total active connections: {len(connections)}")
    
    async def send_thinking_log(category: str, message: str, details: dict = None):
        """Send a thinking log to the UI."""
        log_entry = {
            "timestamp": time.time(),
            "category": category,
            "message": message,
            "details": details or {}
        }
        sanitized = sanitize_log_for_ui(log_entry)
        
        thinking_msg = {
            "type": "thinking",
            "content": sanitized
        }
        try:
            await websocket.send_json(thinking_msg)
            logger.websocket_event("thinking", "out", {"category": category})
        except Exception:
            pass  # Don't fail on send errors
    
    try:
        # Send welcome message
        welcome_msg = {
            "type": "system",
            "content": "Connected to ARIA - AI Business Advisor. How can I help you today?",
            "session_id": session_id
        }
        await websocket.send_json(welcome_msg)
        logger.websocket_event("system", "out", welcome_msg)
        
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            logger.websocket_event(message_data.get("type", "unknown"), "in", message_data)
            
            if message_data.get("type") == "message":
                request_id = logger.new_request()
                logger.separator(f"WEBSOCKET CHAT REQUEST #{request_id}")
                logger.debug(f"Received message keys: {list(message_data.keys())}")
                
                user_message = message_data.get("content", "")
                location = message_data.get("location", "India")
                search_provider = message_data.get("search_provider", "tavily")
                
                logger.user_input(user_message, location)
                logger.debug(f"Search provider: {search_provider}")
                
                # Set search provider context for this request
                set_search_provider(search_provider)
                
                if not user_message.strip():
                    logger.debug("Empty message received, skipping")
                    continue
                
                # Get conversation history
                history = conversation_histories.get(session_id, [])
                history.append(HumanMessage(content=user_message))
                
                logger.debug(f"Conversation history: {len(history)} messages")
                
                # Send typing indicator
                typing_msg = {"type": "typing", "content": True}
                await websocket.send_json(typing_msg)
                logger.websocket_event("typing", "out", typing_msg)
                
                # Initialize thinking logs collector
                thinking_logs = ThinkingLogCollector()
                
                try:
                    start_time = time.time()
                    
                    # Send initial thinking logs
                    await send_thinking_log("initialization", "Starting analysis of your question...")
                    await asyncio.sleep(0.1)
                    
                    await send_thinking_log("initialization", f"Location context: {location}")
                    await asyncio.sleep(0.1)
                    
                    # Create graph
                    logger.model_thinking("initialization", "Creating advisor graph")
                    await send_thinking_log("initialization", "Initializing AI advisor...")
                    
                    graph = create_advisor_graph(location)
                    
                    # Use streaming invoke to get step-by-step updates
                    full_response = ""
                    tool_used = False
                    tool_names_used = []
                    tool_queries = []
                    tool_messages = []  # Capture ToolMessage objects for validator
                    
                    # Create a queue for async communication
                    event_queue = asyncio.Queue()
                    
                    def run_graph():
                        """Run the graph and collect events."""
                        nonlocal full_response, tool_used, tool_names_used, tool_queries, tool_messages
                        logger.model_thinking("execution", "Starting graph stream execution")
                        step_count = 0
                        fact_check_report = None
                        
                        for step in graph.stream({"messages": history, "location": location}):
                            step_count += 1
                            for node_name, output in step.items():
                                logger.graph_step(node_name, "processing", f"Step {step_count}")
                                
                                # Collect events for the UI
                                if node_name == "tools":
                                    tool_used = True
                                    # Extract tool results and store ToolMessages for validator
                                    for msg in output.get("messages", []):
                                        if isinstance(msg, ToolMessage):
                                            # Capture ToolMessage for validation context
                                            tool_messages.append(msg)
                                            logger.debug(f"Captured ToolMessage: {msg.content[:100] if msg.content else 'empty'}...")
                                        if hasattr(msg, 'content'):
                                            # Log tool result summary
                                            result_preview = str(msg.content)[:100]
                                            thinking_logs.add("tool_end", f"Retrieved: {result_preview}...")
                                            
                                elif node_name == "agent":
                                    for msg in output.get("messages", []):
                                        if isinstance(msg, AIMessage):
                                            if msg.tool_calls:
                                                # AI wants to use tools
                                                for tc in msg.tool_calls:
                                                    tool_name = tc['name']
                                                    tool_args = tc.get('args', {})
                                                    query = tool_args.get('query', tool_args.get('topic', str(tool_args)))
                                                    
                                                    logger.model_thinking("tool_decision", f"Model decided to call: {tool_name}")
                                                    tool_names_used.append(tool_name)
                                                    tool_queries.append({"tool": tool_name, "query": query})
                                                    
                                                    thinking_logs.add("tool_decision", f"Deciding to search: {tool_name} (via {search_provider})")
                                                    thinking_logs.add("tool_start", f"Searching {search_provider.capitalize()} for: {query[:80]}...")
                                                    
                                            elif msg.content:
                                                logger.model_thinking("response_generation", f"Content generated: {len(msg.content)} chars")
                                                full_response = msg.content
                                                thinking_logs.add("response_generation", f"Generated response ({len(msg.content)} characters)")
                                
                                elif node_name == "fact_check":
                                    # Capture fact-check report
                                    for msg in output.get("messages", []):
                                        if isinstance(msg, SystemMessage):
                                            try:
                                                fact_check_data = json.loads(msg.content)
                                                if fact_check_data.get("type") == "fact_check":
                                                    fact_check_report = fact_check_data.get("report")
                                                    logger.debug(f"Captured fact-check report: {fact_check_report.get('summary', '')[:100]}...")
                                            except json.JSONDecodeError:
                                                pass
                        
                        logger.debug(f"Graph execution completed in {step_count} steps")
                        return full_response, fact_check_report
                    
                    # Run the graph in executor while streaming thinking logs
                    loop = asyncio.get_event_loop()
                    
                    # Send thinking log about connecting to AI
                    await send_thinking_log("api_call", "Connecting to NVIDIA AI service...")
                    await asyncio.sleep(0.1)
                    
                    await send_thinking_log("prompt_preparation", f"Analyzing: \"{user_message[:50]}...\"")
                    await asyncio.sleep(0.1)
                    
                    # Capture context to propagate search provider
                    ctx = contextvars.copy_context()
                    
                    # Create a task for the graph execution
                    graph_task = loop.run_in_executor(None, ctx.run, run_graph)
                    
                    # Poll for thinking logs while graph is running
                    last_log_index = 0
                    while not graph_task.done():
                        # Check for new thinking logs
                        new_logs = thinking_logs.get_new_logs(last_log_index)
                        for log in new_logs:
                            sanitized = sanitize_log_for_ui(log)
                            await websocket.send_json({
                                "type": "thinking",
                                "content": sanitized
                            })
                        last_log_index += len(new_logs)
                        await asyncio.sleep(0.1)
                    
                    # Get the result (now returns both response and fact-check report)
                    result, fact_check_report = await graph_task
                    
                    # Send any remaining logs
                    remaining_logs = thinking_logs.get_new_logs(last_log_index)
                    for log in remaining_logs:
                        sanitized = sanitize_log_for_ui(log)
                        await websocket.send_json({
                            "type": "thinking",
                            "content": sanitized
                        })
                    
                    execution_time = (time.time() - start_time) * 1000
                    logger.debug(f"Graph execution time: {execution_time:.0f}ms")
                    
                    # Send final thinking status
                    await send_thinking_log("response_received", f"Analysis complete ({execution_time:.0f}ms)")
                    
                    # Send tool status if tools were used
                    if tool_used:
                        for tool_info in tool_queries:
                            tool_name = tool_info["tool"]
                            query = tool_info["query"]
                            
                            start_msg = {
                                "type": "tool_status",
                                "status": "complete",
                                "tool": tool_name,
                                "query": query[:100],
                                "content": f"🔍 Searched via {search_provider.capitalize()}: {query[:60]}..."
                            }
                            await websocket.send_json(start_msg)
                            logger.websocket_event("tool_status", "out", start_msg)
                    
                    # Stream the response in chunks for better UX
                    if result:
                        # Clean any raw tool syntax that leaked into content
                        import re
                        clean_result = result
                        # Remove all variants of python/function tags
                        clean_result = re.sub(r'<\|python_?tag\|>.*', '', clean_result, flags=re.DOTALL | re.IGNORECASE)
                        clean_result = re.sub(r'<function.*?(?:</function>|$)', '', clean_result, flags=re.DOTALL | re.IGNORECASE)
                        clean_result = re.sub(r'\{"query":\s*"[^"]*"[^}]*\}', '', clean_result)
                        clean_result = re.sub(r'websearch|web_search|search_regulations', '', clean_result, flags=re.IGNORECASE)
                        # Remove any leftover special tokens
                        clean_result = re.sub(r'<\|[^|]*\|>', '', clean_result)
                        clean_result = clean_result.strip()
                        
                        if clean_result:
                            logger.ai_response(clean_result)
                            logger.debug(f"Streaming response in chunks...")
                            
                            # Hide thinking panel before showing response
                            await websocket.send_json({
                                "type": "thinking_done",
                                "content": ""
                            })
                            
                            chunk_size = 20
                            chunks_sent = 0
                            for i in range(0, len(clean_result), chunk_size):
                                chunk = clean_result[i:i+chunk_size]
                                chunk_msg = {"type": "token", "content": chunk}
                                await websocket.send_json(chunk_msg)
                                chunks_sent += 1
                                await asyncio.sleep(0.02)  # Small delay for smooth streaming effect
                            
                            logger.debug(f"Streamed {chunks_sent} chunks to client")
                            full_response = clean_result
                    
                    # Send fact-check report if available
                    if fact_check_report:
                        fact_check_msg = {
                            "type": "fact_check",
                            "content": fact_check_report
                        }
                        await websocket.send_json(fact_check_msg)
                        logger.websocket_event("fact_check", "out", {"verified": fact_check_report.get("verified_claims", 0), "failed": fact_check_report.get("failed_claims", 0)})
                    
                except Exception as e:
                    import traceback
                    logger.error("Error during graph execution", e)
                    logger.debug(f"Traceback: {traceback.format_exc()}")
                    
                    error_msg = {
                        "type": "error",
                        "content": f"Error generating response: {str(e)}"
                    }
                    await websocket.send_json(error_msg)
                    logger.websocket_event("error", "out", error_msg)
                    continue
                
                # Send completion signal
                done_msg = {"type": "done", "content": ""}
                await websocket.send_json(done_msg)
                logger.websocket_event("done", "out", done_msg)
                
                total_time = (time.time() - start_time) * 1000
                logger.debug(f"Total request handling time: {total_time:.0f}ms")
                
                # Update history - include ToolMessages for validation
                if full_response:
                    # Add tool messages first (they came before the AI response)
                    for tool_msg in tool_messages:
                        history.append(tool_msg)
                    history.append(AIMessage(content=full_response))
                    conversation_histories[session_id] = history[-30:]  # Increased to accommodate tool messages
                    logger.debug(f"History updated with {len(tool_messages)} tool messages, now {len(conversation_histories[session_id])} total messages")
                
                logger.separator(f"WEBSOCKET CHAT COMPLETE #{request_id}")
            
            elif message_data.get("type") == "ping":
                pong_msg = {"type": "pong"}
                await websocket.send_json(pong_msg)
                logger.websocket_event("pong", "out", pong_msg)
    
    except WebSocketDisconnect:
        logger.websocket_event("disconnect", "in", {"session_id": session_id, "reason": "client_disconnect"})
        logger.system(f"Client {session_id} disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket error", e)
        logger.websocket_event("error", "in", {"session_id": session_id, "error": str(e)})
    
    finally:
        # Cleanup
        if session_id in connections:
            del connections[session_id]
        if session_id in conversation_histories:
            del conversation_histories[session_id]
        logger.debug(f"Session {session_id} cleaned up. Active connections: {len(connections)}")


# Portfolio Analysis Endpoints
@app.post("/api/portfolio/analyze")
async def analyze_portfolio(request: PortfolioRequest):
    """
    Analyze a portfolio and return risk metrics, valuations, and projections.
    """
    logger = get_logger()
    logger.separator("PORTFOLIO ANALYSIS REQUEST")
    
    try:
        agent = get_portfolio_agent()
        result = await agent.analyze_portfolio(request.holdings)
        
        if "error" in result:
             raise HTTPException(status_code=400, detail=result["error"])
             
        return result
    except Exception as e:
        logger.error("Portfolio analysis error", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """
    WebSocket endpoint for real-time portfolio updates.
    
    Message format:
    {
        "action": "subscribe",
        "holdings": [...]
    }
    """
    logger = get_logger()
    await websocket.accept()
    
    session_id = str(id(websocket))
    logger.websocket_event("connect", "in", {"session_id": session_id, "type": "portfolio"})
    
    try:
        agent = get_portfolio_agent()
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("action") == "analyze":
                holdings = message.get("holdings", [])
                logger.info(f"WS Portfolio analysis for {len(holdings)} items")
                
                # Run analysis
                result = await agent.analyze_portfolio(holdings)
                
                # Send result
                await websocket.send_json({
                    "type": "analysis_result",
                    "data": result,
                    "timestamp": time.time()
                })
                
    except WebSocketDisconnect:
        logger.system(f"Portfolio client {session_id} disconnected")
    except Exception as e:
        logger.error("Portfolio WS error", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


# Mount static files for frontend assets
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except Exception:
    pass  # Frontend directory might not exist yet


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
