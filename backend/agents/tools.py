"""
Tools for the Business Advisor Agent.
Includes web search and regulation lookup capabilities using either Tavily or Perplexity.
"""

import time
import os
from langchain_core.tools import tool
from tavily import TavilyClient
from perplexity import Perplexity
from typing import Optional
from dotenv import load_dotenv
from contextvars import ContextVar

from backend.logger import get_logger

# Load environment variables from .env file
load_dotenv()

# Context Variable to store the search provider for the current request context
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


def get_perplexity_client() -> Perplexity:
    """Get Perplexity client instance."""
    logger = get_logger()
    api_key = os.getenv("SONAR_API_KEY", "")
    if not api_key:
        logger.error("SONAR_API_KEY environment variable is required")
        raise ValueError("SONAR_API_KEY environment variable is required")
    logger.debug(f"Perplexity API Key loaded (length: {len(api_key)})")
    return Perplexity(api_key=api_key)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for current information about business topics, market trends, 
    regulations, and news.
    
    Use this tool when you need:
    - Current market data or trends
    - Recent news about industries or companies
    - Up-to-date government regulations
    - Competitor information
    - Economic indicators
    
    Args:
        query: The search query - be specific for better results
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        Search results with relevant information and sources
    """
    provider = get_search_provider()
    logger = get_logger()
    logger.debug(f"DEBUG: web_search responding with provider: '{provider}' (type: {type(provider)})")
    
    if provider and provider.lower() == "perplexity":
        return _web_search_perplexity(query, max_results)
    else:
        return _web_search_tavily(query, max_results)


def _web_search_tavily(query: str, max_results: int) -> str:
    logger = get_logger()
    logger.separator(f"WEB SEARCH (Tavily): {query}")
    
    try:
        logger.api_request("Tavily", "search", f"query='{query}', max_results={max_results}")
        
        start_time = time.time()
        client = get_tavily_client()
        
        response = client.search(query=query, max_results=max_results)
        
        duration_ms = (time.time() - start_time) * 1000
        result_count = len(response.get('results', []))
        
        logger.api_response("Tavily", 200, duration_ms)
        logger.debug(f"Tavily returned {result_count} results")
        
        formatted_results = []
        if response.get("answer"):
            formatted_results.append(f"**Summary:** {response['answer']}\n")
        
        formatted_results.append("**Sources:**")
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:300]
            formatted_results.append(f"\n{i}. **{title}**\n   URL: {url}\n   {content}...")
        
        return "\n".join(formatted_results)
    
    except Exception as e:
        logger.error(f"Web Search Error (Tavily)", e)
        return f"Search error: {str(e)}"


def _web_search_perplexity(query: str, max_results: int) -> str:
    logger = get_logger()
    logger.separator(f"WEB SEARCH (Perplexity): {query}")
    
    try:
        logger.api_request("Perplexity", "search", f"query='{query}', max_results={max_results}")
        
        start_time = time.time()
        client = get_perplexity_client()
        
        response = client.search.create(query=query, max_results=max_results)
        
        duration_ms = (time.time() - start_time) * 1000
        results = list(response.results)
        
        logger.api_response("Perplexity", 200, duration_ms)
        logger.debug(f"Perplexity returned {len(results)} results")
        
        formatted_results = ["**Sources:**"]
        for i, result in enumerate(results, 1):
            title = getattr(result, 'title', 'No title')
            url = getattr(result, 'url', '')
            snippet = getattr(result, 'snippet', '')
            date = getattr(result, 'date', '')
            date_str = f" ({date})" if date else ""
            formatted_results.append(f"\n{i}. **{title}**{date_str}\n   URL: {url}\n   {snippet}")
        
        return "\n".join(formatted_results)
    
    except Exception as e:
        logger.error(f"Web Search Error (Perplexity)", e)
        return f"Search error: {str(e)}"


@tool
def search_regulations(topic: str, location: str, regulation_type: Optional[str] = None) -> str:
    """
    Search for government regulations and compliance requirements specific to a location.
    
    Use this tool when you need:
    - Business registration requirements
    - Tax regulations and compliance
    - Industry-specific licenses and permits
    - Labor laws and employment regulations
    - Environmental compliance requirements
    
    Args:
        topic: The business topic or industry to search regulations for
        location: The geographic location (city, state, or country)
        regulation_type: Optional specific type (e.g., "tax", "license", "labor")
    
    Returns:
        Relevant regulatory information with sources
    """
    provider = get_search_provider()
    logger = get_logger()
    logger.debug(f"DEBUG: search_regulations responding with provider: '{provider}'")

    if provider and provider.lower() == "perplexity":
        return _search_regulations_perplexity(topic, location, regulation_type)
    else:
        return _search_regulations_tavily(topic, location, regulation_type)


def _search_regulations_tavily(topic: str, location: str, regulation_type: Optional[str]) -> str:
    logger = get_logger()
    logger.separator(f"REGULATION SEARCH (Tavily): {topic} in {location}")
    
    try:
        query_parts = [topic, "regulations", "requirements", location]
        if regulation_type:
            query_parts.insert(1, regulation_type)
        query = " ".join(query_parts) + " government official"
        
        logger.api_request("Tavily", "search (regulations)", f"query='{query}'")
        start_time = time.time()
        client = get_tavily_client()
        
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True,
            include_domains=["gov.in", "gov.uk", "gov", "government", "official"]
        )
        
        duration_ms = (time.time() - start_time) * 1000
        logger.api_response("Tavily", 200, duration_ms)
        
        formatted_results = [f"**Regulatory Information for {topic} in {location}:**\n"]
        if response.get("answer"):
            formatted_results.append(f"**Overview:** {response['answer']}\n")
        
        formatted_results.append("**Official Sources & Requirements:**")
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", 'No title')
            url = result.get("url", "")
            content = result.get("content", "")[:400]
            formatted_results.append(f"\n{i}. **{title}**\n   Source: {url}\n   {content}...")
            
        formatted_results.append("\n\n⚠️ *Note: Regulations change frequently.*")
        return "\n".join(formatted_results)

    except Exception as e:
        logger.error("Regulation search error (Tavily)", e)
        return f"Error: {str(e)}"


def _search_regulations_perplexity(topic: str, location: str, regulation_type: Optional[str]) -> str:
    logger = get_logger()
    logger.separator(f"REGULATION SEARCH (Perplexity): {topic} in {location}")
    
    try:
        query_parts = [topic, "regulations", "requirements", location]
        if regulation_type:
            query_parts.insert(1, regulation_type)
        query = " ".join(query_parts) + " government official"
        
        logger.api_request("Perplexity", "search", f"query='{query}'")
        start_time = time.time()
        client = get_perplexity_client()
        
        response = client.search.create(query=query, max_results=5)
        
        duration_ms = (time.time() - start_time) * 1000
        results = list(response.results)
        logger.api_response("Perplexity", 200, duration_ms)
        
        formatted_results = [f"**Regulatory Information for {topic} in {location}:**\n"]
        formatted_results.append("**Official Sources & Requirements:**")
        
        for i, result in enumerate(results, 1):
            title = getattr(result, 'title', 'No title')
            url = getattr(result, 'url', '')
            snippet = getattr(result, 'snippet', '')
            formatted_results.append(f"\n{i}. **{title}**\n   Source: {url}\n   {snippet}")
            
        formatted_results.append("\n\n⚠️ *Note: Regulations change frequently.*")
        return "\n".join(formatted_results)

    except Exception as e:
        logger.error("Regulation search error (Perplexity)", e)
        return f"Error: {str(e)}"


def get_tools() -> list:
    """Get all available tools for the advisor agent."""
    logger = get_logger()
    tools = [web_search, search_regulations]
    logger.system(f"Loading {len(tools)} tools: {[t.name for t in tools]}")
    return tools

