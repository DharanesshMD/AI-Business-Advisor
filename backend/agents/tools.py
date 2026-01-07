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

from backend.agents.utils import (
    get_search_provider, 
    set_search_provider, 
    get_tavily_client, 
    get_perplexity_client
)


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


@tool
def analyze_portfolio_tool(holdings_json: str) -> str:
    """
    Analyze a financial portfolio to calculate risk metrics (VaR, CVaR), 
    performance ratios (Sharpe, Sortino), and run Monte Carlo simulations.
    
    Use this tool when the user asks to:
    - Analyze their stock portfolio
    - Calculate risk or Value at Risk (VaR)
    - Project future portfolio value
    - Check portfolio health
    
    Args:
        holdings_json: A JSON string representing the list of holdings.
                       Each item must have 'symbol' (str) and 'quantity' (float).
                       Optional: 'purchase_price' (float).
                       Example: '[{"symbol": "AAPL", "quantity": 10, "purchase_price": 150}, {"symbol": "NVDA", "quantity": 5}]'
    
    Returns:
        A JSON string containing the analysis results (metrics, risk, projections).
    """
    logger = get_logger()
    logger.separator(f"PORTFOLIO TOOL CALLED")
    
    try:
        import json
        from backend.agents.portfolio import get_portfolio_agent # Local Import
        holdings = json.loads(holdings_json)
        
        # Validate format
        if not isinstance(holdings, list):
            return "Error: holdings_json must parse to a list of dictionaries."
            
        logger.debug(f"Analyzing {len(holdings)} holdings...")
        
        # Get agent and run analysis (sync wrapper for async method)
        import asyncio
        agent = get_portfolio_agent()
        
        # We need to run the async method in a synchronous tool
        # Since we are already in an event loop (FastAPI), we shouldn't use run()
        # But this tool is run in a threadpool by LangChain, so we can use a new loop or run_coroutine_threadsafe
        # Simplest valid approach for LangChain tools:
        
        try:
             loop = asyncio.get_event_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             
        if loop.is_running():
            # If we are in a running loop (unlikely in threadpool, but possible), 
            # we might need to handle differently.
            # safe hack: run_in_executor
            future = asyncio.run_coroutine_threadsafe(agent.analyze_portfolio(holdings), loop)
            result = future.result()
        else:
            result = loop.run_until_complete(agent.analyze_portfolio(holdings))
            
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("Portfolio tool error", e)
        return f"Error analyzing portfolio: {str(e)}"


@tool
def analyze_sentiment_tool(symbol: str) -> str:
    """
    Analyze market sentiment for a specific stock symbol using news and social data.
    
    Use this tool when you need to:
    - Gauge market mood (Bullish/Bearish)
    - Understand why a stock is moving
    - Get a sentiment score (-1 to 1)
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, NVDA)
        
    Returns:
        JSON string with sentiment score, classification, and summary.
    """
    try:
        import asyncio
        import json
        from backend.agents.sentiment import get_sentiment_agent
        
        agent = get_sentiment_agent()
        
        # Async helper
        try:
             loop = asyncio.get_event_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(agent.analyze_sentiment(symbol), loop)
            result = future.result()
        else:
            result = loop.run_until_complete(agent.analyze_sentiment(symbol))
            
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error analyzing sentiment: {str(e)}"

@tool
def check_risk_tool(holdings_json: str) -> str:
    """
    Check if a portfolio violates common risk constraints.
    
    Use this tool to:
    - Validate if a portfolio is too risky
    - Check for concentration risk (too much in one asset)
    - Get hedging suggestions
    
    Args:
        holdings_json: JSON string of holdings list (same format as portfolio tool)
        
    Returns:
        JSON string with health status, alerts, and hedging advice.
    """
    try:
        import asyncio
        import json
        from backend.agents.risk import get_risk_agent
        
        holdings = json.loads(holdings_json)
        agent = get_risk_agent()
        
        # Default constraints
        constraints = {
            "max_var_95": 0.05,
            "min_sharpe": 0.5,
            "max_single_position": 0.25
        }
        
        try:
             loop = asyncio.get_event_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(agent.check_portfolio_risk(holdings, constraints), loop)
            result = future.result()
        else:
            result = loop.run_until_complete(agent.check_portfolio_risk(holdings, constraints))
            
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error checking risk: {str(e)}"

@tool
def search_filings_tool(symbol: str) -> str:
    """
    Search and analyze SEC 10-K filings for risk factors.
    
    Use this tool to:
    - Find fundamental risks (Regulatory, Supply Chain)
    - Extract "Risk Factors" from official documents
    - Populate the Knowledge Graph
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        JSON string with extracted risks.
    """
    try:
        import asyncio
        import json
        from backend.agents.filings import get_filings_agent
        
        agent = get_filings_agent()
        
        try:
             loop = asyncio.get_event_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(agent.analyze_risks(symbol), loop)
            result = future.result()
        else:
            result = loop.run_until_complete(agent.analyze_risks(symbol))
            
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error analyzing filings: {str(e)}"


@tool
def validate_stock_price(symbol: str) -> str:
    """
    Validate or check the current real-time price of a stock using Yahoo Finance.
    
    Use this tool when:
    - You need to confirm a stock price from a free, independent source.
    - You want to double-check the values returned by other tools.
    - The user specifically asks to check the "real" or "current" price.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, NVDA)
        
    Returns:
        JSON string with the current price, currency, and timestamp.
    """
    logger = get_logger()
    logger.separator(f"PRICE VALIDATION (Yahoo Finance): {symbol}")
    
    try:
        import yfinance as yf
        import json
        from datetime import datetime
        
        # specific to yfinance: period="1d" gets the latest data
        ticker = yf.Ticker(symbol)
        
        # fastinfo is often faster/more reliable for current price than history
        # but history is robust
        
        start_time = time.time()
        
        # Try fast_info first (it's often better for realtime)
        try:
            price = ticker.fast_info['last_price']
            currency = ticker.fast_info['currency']
            source = "fast_info"
        except:
             # Fallback to history
            history = ticker.history(period="1d", interval="1m")
            if not history.empty:
                price = history['Close'].iloc[-1]
                currency = "USD" # Assumption, but usually safe for US stocks or available in metadata
                source = "history_1m"
            else:
                # Fallback to daily
                history = ticker.history(period="1d")
                if not history.empty:
                    price = history['Close'].iloc[-1]
                    currency = "USD"
                    source = "history_1d"
                else:
                    return f"Error: Could not fetch price for {symbol}"

        duration_ms = (time.time() - start_time) * 1000
        logger.debug(f"Yahoo Finance returned price: {price} via {source}")

        result = {
            "symbol": symbol.upper(),
            "price": round(price, 2),
            "currency": currency,
            "timestamp": datetime.now().isoformat(),
            "source": "Yahoo Finance (Free)"
        }
        
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Price validation error for {symbol}", e)
        return f"Error fetching price: {str(e)}"


@tool
def query_knowledge_graph(symbol: str) -> str:
    """
    Query the Knowledge Graph to discover hidden risk correlations,
    supplier dependencies, and macro sensitivities for a company.
    
    Use this tool when you want to:
    - Find risks that aren't obvious from direct analysis
    - Discover how macro factors (interest rates, oil prices) affect a company
    - Identify supply chain risks from dependent suppliers
    - Get a holistic view of interconnected risks
    
    Note: Data must first be populated using the search_filings_tool.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, NVDA)
        
    Returns:
        JSON string with discovered relationships, risks, and insights.
    """
    logger = get_logger()
    logger.separator(f"KNOWLEDGE GRAPH QUERY: {symbol}")
    
    try:
        import asyncio
        import json
        from backend.agents.knowledge_graph import get_knowledge_graph_agent
        
        agent = get_knowledge_graph_agent()
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.discover_related_risks(symbol), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(agent.discover_related_risks(symbol))
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Knowledge Graph query error for {symbol}", e)
        return f"Error querying Knowledge Graph: {str(e)}"


@tool
def run_stress_test(scenario: str, symbols: str) -> str:
    """
    Run a macro-economic stress test on a portfolio or list of stocks.
    
    Simulates how different shock scenarios (Fed rate hikes, oil spikes, 
    recessions, tech selloffs) would impact the given holdings.
    
    Available scenarios:
    - fed_rate_hike_50bps: Fed raises rates 50bps unexpectedly
    - fed_rate_cut_25bps: Fed cuts rates 25bps
    - oil_spike_20pct: Oil prices surge 20%
    - recession_severe: Deep economic contraction
    - tech_selloff: Technology sector correction 15-20%
    - china_slowdown: China GDP growth falls to 3%
    - inflation_spike: CPI surges to 8%+
    
    Use this tool when users ask about:
    - "What if Fed raises rates?"
    - "How would a recession affect my portfolio?"
    - "Stress test my holdings"
    - "What's my downside risk if oil spikes?"
    
    Args:
        scenario: Scenario ID (e.g., "fed_rate_hike_50bps", "recession_severe")
        symbols: Comma-separated stock symbols (e.g., "AAPL,NVDA,MSFT")
        
    Returns:
        JSON with expected impacts per holding, portfolio-level P&L, and recommendations.
    """
    logger = get_logger()
    logger.separator(f"STRESS TEST: {scenario} on {symbols}")
    
    try:
        import asyncio
        import json
        from backend.agents.stress_test import get_stress_test_agent
        
        agent = get_stress_test_agent()
        
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        
        if not symbol_list:
            return json.dumps({"error": "No valid symbols provided"})
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.run_stress_test(scenario, symbols=symbol_list), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(
                agent.run_stress_test(scenario, symbols=symbol_list)
            )
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Stress test error: {scenario}", e)
        return f"Error running stress test: {str(e)}"


@tool
def list_stress_scenarios() -> str:
    """
    List all available macro-economic stress test scenarios.
    
    Use this when the user asks what stress tests are available or wants to 
    see the options before running a specific scenario.
    
    Returns:
        JSON list of available scenarios with names and descriptions.
    """
    logger = get_logger()
    logger.separator("LIST STRESS SCENARIOS")
    
    try:
        import json
        from backend.agents.stress_test import get_stress_test_agent
        
        agent = get_stress_test_agent()
        scenarios = agent.get_available_scenarios()
        
        return json.dumps(scenarios, indent=2)
        
    except Exception as e:
        logger.error("Error listing stress scenarios", e)
        return f"Error: {str(e)}"


def get_tools() -> list:
    """Get all available tools for the advisor agent."""
    logger = get_logger()
    tools = [
        web_search, 
        search_regulations, 
        analyze_portfolio_tool,
        analyze_sentiment_tool,
        check_risk_tool,
        search_filings_tool,
        validate_stock_price,
        query_knowledge_graph,
        run_stress_test,
        list_stress_scenarios
    ]
    logger.system(f"Loading {len(tools)} tools: {[t.name for t in tools]}")
    return tools


