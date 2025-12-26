"""
Comprehensive logging system for AI Business Advisor.
Captures every step: model thinking, function calling, API interactions, and more.
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
from functools import wraps
import time
import os

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Color codes for console output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Categories
    SYSTEM = "\033[96m"      # Cyan - System/startup
    USER = "\033[92m"        # Green - User inputs
    AI = "\033[93m"          # Yellow - AI responses
    TOOL = "\033[95m"        # Magenta - Tool calls
    API = "\033[94m"         # Blue - API calls
    ERROR = "\033[91m"       # Red - Errors
    DEBUG = "\033[90m"       # Gray - Debug info
    THINKING = "\033[38;5;208m"  # Orange - Model thinking
    WEBSOCKET = "\033[38;5;51m"  # Cyan-blue - WebSocket events


class DetailedFormatter(logging.Formatter):
    """Custom formatter with colors and detailed timestamps."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.SYSTEM,
        logging.WARNING: Colors.THINKING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.ERROR + Colors.BOLD,
    }
    
    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp with milliseconds
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Get color based on level
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        
        # Custom prefixes based on category (stored in record.category if set)
        category = getattr(record, 'category', 'SYSTEM')
        category_colors = {
            'SYSTEM': Colors.SYSTEM,
            'USER': Colors.USER,
            'AI': Colors.AI,
            'TOOL': Colors.TOOL,
            'API': Colors.API,
            'ERROR': Colors.ERROR,
            'DEBUG': Colors.DEBUG,
            'THINKING': Colors.THINKING,
            'WEBSOCKET': Colors.WEBSOCKET,
            'GRAPH': Colors.THINKING,
        }
        
        color = category_colors.get(category, color)
        
        # Format the message
        formatted = f"{color}[{timestamp}] [{category:10}] {record.getMessage()}{Colors.RESET}"
        
        return formatted


class FileFormatter(logging.Formatter):
    """Plain text formatter for file logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        category = getattr(record, 'category', 'SYSTEM')
        return f"[{timestamp}] [{category:10}] {record.getMessage()}"


class AdvisorLogger:
    """
    Centralized logger for AI Business Advisor.
    Provides methods for logging different types of events.
    """
    
    def __init__(self, name: str = "advisor"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Clear existing handlers
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(DetailedFormatter())
        self.logger.addHandler(console_handler)
        
        # File handler for persistent logs
        log_file = LOGS_DIR / f"advisor_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(FileFormatter())
        self.logger.addHandler(file_handler)
        
        # Detailed JSON log for structured analysis
        json_log_file = LOGS_DIR / f"advisor_{datetime.now().strftime('%Y%m%d')}.jsonl"
        self.json_log_path = json_log_file
        
        self.session_id: Optional[str] = None
        self.request_counter = 0
    
    def _log(self, level: int, category: str, message: str, **extra):
        """Internal logging method."""
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            __file__,
            0,
            message,
            args=(),
            exc_info=None,
            extra={'category': category}
        )
        record.category = category
        self.logger.handle(record)
        
        # Also write to JSON log
        self._write_json_log(category, message, extra)
    
    def _write_json_log(self, category: str, message: str, extra: dict):
        """Write structured log entry to JSON file."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "message": message,
            "session_id": self.session_id,
            "request_id": self.request_counter,
            **extra
        }
        try:
            with open(self.json_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, default=str) + '\n')
        except Exception:
            pass  # Don't fail on logging errors
    
    def set_session(self, session_id: str):
        """Set the current session ID."""
        self.session_id = session_id
        self.system(f"Session started: {session_id}")
    
    def new_request(self):
        """Increment request counter for a new user request."""
        self.request_counter += 1
        return self.request_counter
    
    # ========== Category-specific logging methods ==========
    
    def system(self, message: str, **extra):
        """Log system events (startup, shutdown, config)."""
        self._log(logging.INFO, 'SYSTEM', f"🔧 {message}", **extra)
    
    def user_input(self, message: str, location: str = None, **extra):
        """Log user input/messages."""
        location_info = f" [📍 {location}]" if location else ""
        self._log(logging.INFO, 'USER', f"👤 User{location_info}: {message}", **extra)
    
    def ai_response(self, content: str, tokens: int = None, **extra):
        """Log AI model responses."""
        token_info = f" [{tokens} tokens]" if tokens else ""
        # Truncate long responses for console
        display = content[:200] + "..." if len(content) > 200 else content
        self._log(logging.INFO, 'AI', f"🤖 AI Response{token_info}: {display}", 
                 full_content=content, **extra)
    
    def model_thinking(self, stage: str, details: str = None, **extra):
        """Log model reasoning/thinking steps."""
        detail_str = f" - {details}" if details else ""
        self._log(logging.INFO, 'THINKING', f"💭 Model Thinking [{stage}]{detail_str}", **extra)
    
    def tool_call_start(self, tool_name: str, arguments: dict, **extra):
        """Log when a tool is being called."""
        args_str = json.dumps(arguments, indent=2) if arguments else "{}"
        self._log(logging.INFO, 'TOOL', f"🔧 Tool Call START: {tool_name}", 
                 tool_name=tool_name, arguments=arguments, **extra)
        self._log(logging.DEBUG, 'TOOL', f"   Arguments: {args_str}")
    
    def tool_call_end(self, tool_name: str, result: str, duration_ms: float = None, **extra):
        """Log tool execution completion."""
        duration_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
        # Truncate long results for console
        display = result[:300] + "..." if len(result) > 300 else result
        self._log(logging.INFO, 'TOOL', f"✅ Tool Call END: {tool_name}{duration_str}", 
                 tool_name=tool_name, result=result, duration_ms=duration_ms, **extra)
        self._log(logging.DEBUG, 'TOOL', f"   Result: {display}")
    
    def tool_call_error(self, tool_name: str, error: str, **extra):
        """Log tool execution errors."""
        self._log(logging.ERROR, 'TOOL', f"❌ Tool Call FAILED: {tool_name} - {error}", 
                 tool_name=tool_name, error=error, **extra)
    
    def api_request(self, service: str, endpoint: str, payload_summary: str = None, **extra):
        """Log outgoing API requests."""
        payload_str = f" - {payload_summary}" if payload_summary else ""
        self._log(logging.INFO, 'API', f"📤 API Request: {service} -> {endpoint}{payload_str}", **extra)
    
    def api_response(self, service: str, status: int, duration_ms: float = None, **extra):
        """Log API responses."""
        duration_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
        emoji = "✅" if 200 <= status < 300 else "⚠️" if 300 <= status < 400 else "❌"
        self._log(logging.INFO, 'API', f"{emoji} API Response: {service} - Status {status}{duration_str}", **extra)
    
    def websocket_event(self, event_type: str, direction: str, data: dict = None, **extra):
        """Log WebSocket events."""
        arrow = "→" if direction == "out" else "←"
        data_str = json.dumps(data)[:100] if data else ""
        self._log(logging.INFO, 'WEBSOCKET', f"🔌 WS {arrow} [{event_type}] {data_str}", 
                 direction=direction, data=data, **extra)
    
    def graph_step(self, node_name: str, stage: str, details: str = None, **extra):
        """Log LangGraph execution steps."""
        detail_str = f" - {details}" if details else ""
        emoji = "▶️" if stage == "start" else "⏹️" if stage == "end" else "⏸️"
        self._log(logging.INFO, 'GRAPH', f"{emoji} Graph Node [{node_name}] {stage.upper()}{detail_str}", **extra)
    
    def llm_prompt(self, messages: list, **extra):
        """Log the full prompt being sent to the LLM."""
        self._log(logging.DEBUG, 'THINKING', "📋 LLM Prompt (full):", messages=messages, **extra)
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:100]
            self._log(logging.DEBUG, 'THINKING', f"   [{i}] {role}: {content}...")
    
    def llm_response_raw(self, response: dict, **extra):
        """Log the raw LLM response."""
        self._log(logging.DEBUG, 'THINKING', "📨 LLM Raw Response:", response=response, **extra)
    
    def error(self, message: str, exception: Exception = None, **extra):
        """Log errors."""
        exc_str = f": {str(exception)}" if exception else ""
        self._log(logging.ERROR, 'ERROR', f"❌ {message}{exc_str}", 
                 exception=str(exception) if exception else None, **extra)
    
    def debug(self, message: str, **extra):
        """Log debug information."""
        self._log(logging.DEBUG, 'DEBUG', f"🔍 {message}", **extra)
    
    def separator(self, title: str = ""):
        """Log a visual separator for readability."""
        line = "═" * 60
        if title:
            self._log(logging.INFO, 'SYSTEM', f"\n{line}\n  {title}\n{line}")
        else:
            self._log(logging.INFO, 'SYSTEM', line)


# Global logger instance
_logger: Optional[AdvisorLogger] = None


def get_logger() -> AdvisorLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = AdvisorLogger()
    return _logger


def log_execution_time(category: str = "DEBUG"):
    """Decorator to log function execution time."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger()
            start = time.time()
            logger.debug(f"Function {func.__name__} started")
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start) * 1000
                logger.debug(f"Function {func.__name__} completed in {duration:.0f}ms")
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error(f"Function {func.__name__} failed after {duration:.0f}ms", e)
                raise
        return wrapper
    return decorator


def log_async_execution_time(category: str = "DEBUG"):
    """Decorator to log async function execution time."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_logger()
            start = time.time()
            logger.debug(f"Async function {func.__name__} started")
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start) * 1000
                logger.debug(f"Async function {func.__name__} completed in {duration:.0f}ms")
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error(f"Async function {func.__name__} failed after {duration:.0f}ms", e)
                raise
        return wrapper
    return decorator
