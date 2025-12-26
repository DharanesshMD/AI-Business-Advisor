"""
Tools for the Business Advisor Agent.
Includes web search and regulation lookup capabilities.
"""

import time
from langchain_core.tools import tool
from tavily import TavilyClient
from typing import Optional
import os
from dotenv import load_dotenv

from backend.logger import get_logger

# Load environment variables from .env file
load_dotenv()


def get_tavily_client() -> TavilyClient:
    """Get Tavily client instance."""
    logger = get_logger()
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.error("TAVILY_API_KEY environment variable is required")
        raise ValueError("TAVILY_API_KEY environment variable is required")
    logger.debug(f"Tavily API Key loaded (length: {len(api_key)})")
    # Initialize client with API key directly (per official SDK)
    return TavilyClient(api_key)


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
    logger = get_logger()
    logger.separator(f"WEB SEARCH: {query}")
    
    try:
        logger.api_request("Tavily", "search", f"query='{query}', max_results={max_results}")
        
        start_time = time.time()
        client = get_tavily_client()
        
        response = client.search(
            query=query,
            max_results=max_results,
        )
        
        duration_ms = (time.time() - start_time) * 1000
        result_count = len(response.get('results', []))
        
        logger.api_response("Tavily", 200, duration_ms)
        logger.debug(f"Tavily returned {result_count} results")
        
        # Log each result source
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            logger.debug(f"  Result {i}: {title[:50]}... ({url[:50]})")
        
        # Format results for the LLM
        formatted_results = []
        
        if response.get("answer"):
            logger.debug(f"Tavily AI answer: {response['answer'][:100]}...")
            formatted_results.append(f"**Summary:** {response['answer']}\n")
        
        formatted_results.append("**Sources:**")
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:300]  # Truncate for context
            formatted_results.append(f"\n{i}. **{title}**\n   URL: {url}\n   {content}...")
        
        final_result = "\n".join(formatted_results)
        logger.debug(f"Formatted result length: {len(final_result)} chars")
        
        return final_result
    
    except Exception as e:
        logger.error(f"Web Search Error", e)
        return f"Search error: {str(e)}. Please try a different query or proceed with general knowledge."


@tool
def search_regulations(
    topic: str,
    location: str,
    regulation_type: Optional[str] = None
) -> str:
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
    logger = get_logger()
    logger.separator(f"REGULATION SEARCH: {topic} in {location}")
    
    try:
        # Build a specific regulatory search query
        query_parts = [topic, "regulations", "requirements", location]
        if regulation_type:
            query_parts.insert(1, regulation_type)
            logger.debug(f"Regulation type filter: {regulation_type}")
        
        query = " ".join(query_parts) + " government official"
        logger.debug(f"Built query: {query}")
        
        logger.api_request("Tavily", "search (regulations)", f"query='{query}', search_depth=advanced")
        
        start_time = time.time()
        client = get_tavily_client()
        
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True,
            include_domains=["gov.in", "gov.uk", "gov", "government", "official"]  # Prefer official sources
        )
        
        duration_ms = (time.time() - start_time) * 1000
        result_count = len(response.get('results', []))
        
        logger.api_response("Tavily", 200, duration_ms)
        logger.debug(f"Regulation search returned {result_count} results")
        
        # Log each result source
        for i, result in enumerate(response.get("results", []), 1):
            url = result.get("url", "")
            is_gov = any(domain in url.lower() for domain in ['gov', 'government', 'official'])
            gov_badge = "[GOV]" if is_gov else "[OTHER]"
            logger.debug(f"  {gov_badge} Result {i}: {url[:60]}")
        
        # Format regulatory results
        formatted_results = [f"**Regulatory Information for {topic} in {location}:**\n"]
        
        if response.get("answer"):
            logger.debug(f"AI Overview: {response['answer'][:100]}...")
            formatted_results.append(f"**Overview:** {response['answer']}\n")
        
        formatted_results.append("**Official Sources & Requirements:**")
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:400]
            formatted_results.append(f"\n{i}. **{title}**\n   Source: {url}\n   {content}...")
        
        formatted_results.append("\n\n⚠️ *Note: Regulations change frequently. Always verify with official government sources before making business decisions.*")
        
        final_result = "\n".join(formatted_results)
        logger.debug(f"Formatted result length: {len(final_result)} chars")
        
        return final_result
    
    except Exception as e:
        logger.error(f"Regulation search error", e)
        return f"Regulation search error: {str(e)}. Please consult official government websites for {location}."


def get_tools() -> list:
    """Get all available tools for the advisor agent."""
    logger = get_logger()
    tools = [web_search, search_regulations]
    logger.system(f"Loading {len(tools)} tools: {[t.name for t in tools]}")
    return tools
