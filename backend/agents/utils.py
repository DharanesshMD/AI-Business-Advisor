"""
Utility functions for AI Agents.
"""
import os
from contextvars import ContextVar
from tavily import TavilyClient
from backend.logger import get_logger
from dotenv import load_dotenv
import openai

load_dotenv()

# Context Variable to store the search provider
search_provider_var: ContextVar[str] = ContextVar("search_provider", default="tavily")

def set_search_provider(provider: str):
    """Set the search provider for the current context."""
    get_logger().debug(f"DEBUG: Setting search provider to: '{provider}'")
    search_provider_var.set(provider)

def get_search_provider() -> str:
    """Get the current search provider."""
    return search_provider_var.get()

def get_tavily_client() -> TavilyClient:
    """Get Tavily client instance."""
    logger = get_logger()
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.error("TAVILY_API_KEY environment variable is required")
        raise ValueError("TAVILY_API_KEY environment variable is required")
    logger.debug(f"Tavily API Key loaded (length: {len(api_key)})")
    return TavilyClient(api_key=api_key)

def get_perplexity_client() -> openai.OpenAI:
    """Get Perplexity client instance (via OpenAI SDK)."""
    logger = get_logger()
    api_key = os.getenv("SONAR_API_KEY", "")
    if not api_key:
        logger.error("SONAR_API_KEY environment variable is required")
        raise ValueError("SONAR_API_KEY environment variable is required")
    logger.debug(f"Perplexity API Key loaded (length: {len(api_key)})")
    return openai.OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
