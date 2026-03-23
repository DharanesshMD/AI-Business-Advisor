"""
Tools for the Business Advisor Agent.
Includes web search and regulation lookup capabilities using either Tavily or Perplexity.
"""

import time
import os
import json
from langchain_core.tools import tool
from tavily import TavilyClient
import openai
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
    
    if provider and provider.lower() == "auto":
        return _web_search_auto(query, max_results)
    elif provider and provider.lower() == "perplexity":
        return _web_search_perplexity(query, max_results)
    elif provider and provider.lower() == "duckduckgo":
        return _web_search_duckduckgo(query, max_results)
    elif provider and provider.lower() == "scrapling":
        return _web_search_scrapling(query, max_results)
    else:
        return _web_search_tavily(query, max_results)


def _web_search_auto(query: str, max_results: int) -> str:
    """Query all 4 search providers in parallel and combine results.
    Uses as_completed with 5s timeout so scrapling doesn't block fast providers."""
    import concurrent.futures
    logger = get_logger()
    logger.separator(f"WEB SEARCH (AUTO - All 4 Providers): {query}")

    start_time = time.time()

    def search_tavily():
        try:
            return ("tavily", _web_search_tavily(query, max_results))
        except Exception as e:
            return ("tavily", f"Error: {str(e)}")

    def search_perplexity():
        try:
            return ("perplexity", _web_search_perplexity(query, max_results))
        except Exception as e:
            return ("perplexity", f"Error: {str(e)}")

    def search_duckduckgo():
        try:
            return ("duckduckgo", _web_search_duckduckgo(query, max_results))
        except Exception as e:
            return ("duckduckgo", f"Error: {str(e)}")

    def search_scrapling():
        try:
            return ("scrapling", _web_search_scrapling(query, max_results))
        except Exception as e:
            return ("scrapling", f"Error: {str(e)}")

    # Run all 4 searches in parallel with as_completed + timeout
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(search_tavily),
            executor.submit(search_perplexity),
            executor.submit(search_duckduckgo),
            executor.submit(search_scrapling),
        ]
        # Use as_completed with 5s timeout — scrapling may be slower
        for future in concurrent.futures.as_completed(futures, timeout=15):
            try:
                results.append(future.result(timeout=5))
            except (concurrent.futures.TimeoutError, Exception) as e:
                logger.debug(f"Auto mode: a provider timed out or errored: {e}")

    duration_ms = (time.time() - start_time) * 1000
    logger.api_response("AUTO (All 4)", 200, duration_ms)

    # Combine and format results
    combined = ["**🚀 Combined Search Results (All 4 Providers)**\n"]
    combined.append(f"*Query completed in {duration_ms:.0f}ms using Tavily + Perplexity + DuckDuckGo + Scrapling*\n")
    combined.append("---\n")

    for provider_name, result in results:
        icon = {"tavily": "🔵", "perplexity": "🟣", "duckduckgo": "🟢", "scrapling": "🕷️"}.get(provider_name, "⚪")
        combined.append(f"\n### {icon} {provider_name.capitalize()} Results\n")
        combined.append(result)
        combined.append("\n")

    combined.append("\n---\n*Combined from 4 sources for comprehensive coverage (including deep-scraped content)*")

    return "\n".join(combined)


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
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an artificial intelligence assistant and you need to "
                    "engage in a helpful, detailed, polite conversation with a user."
                ),
            },
            {
                "role": "user",
                "content": query,
            },
        ]

        response = client.chat.completions.create(
            model="sonar-pro",
            messages=messages,
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.api_response("Perplexity", 200, duration_ms)
        
        # Perplexity API returns citations and markdown text
        formatted_results = ["**Sources:**"]
        formatted_results.append(response.choices[0].message.content)
        
        return "\n".join(formatted_results)
    
    except Exception as e:
        logger.error(f"Web Search Error (Perplexity)", e)
        return f"Search error: {str(e)}"


def _web_search_duckduckgo(query: str, max_results: int) -> str:
    """DuckDuckGo search - free, no API key required."""
    logger = get_logger()
    logger.separator(f"WEB SEARCH (DuckDuckGo): {query}")
    
    try:
        from backend.search.engines.duckduckgo import get_duckduckgo_engine
        import asyncio
        
        logger.api_request("DuckDuckGo", "search", f"query='{query}', max_results={max_results}")
        
        start_time = time.time()
        engine = get_duckduckgo_engine()
        
        # Run async search in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, engine.search(query, max_results))
                results = future.result()
        else:
            results = loop.run_until_complete(engine.search(query, max_results))
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.api_response("DuckDuckGo", 200, duration_ms)
        logger.debug(f"DuckDuckGo returned {len(results)} results")
        
        formatted_results = ["**Sources (DuckDuckGo - Free):**"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:300]
            formatted_results.append(f"\n{i}. **{title}**\n   URL: {url}\n   {content}...")
        
        return "\n".join(formatted_results)
    
    except Exception as e:
        logger.error(f"Web Search Error (DuckDuckGo)", e)
        return f"Search error: {str(e)}"


def _web_search_scrapling(query: str, max_results: int) -> str:
    """Scrapling deep-scrape search - discovers URLs via DDG then extracts full page content."""
    logger = get_logger()
    logger.separator(f"WEB SEARCH (Scrapling Deep Scrape): {query}")

    try:
        from backend.search.engines.scrapling_engine import get_scrapling_engine
        import asyncio

        logger.api_request("Scrapling", "deep_scrape", f"query='{query}', max_results={max_results}")

        start_time = time.time()
        engine = get_scrapling_engine()

        # Run async search in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, engine.search(query, max_results))
                results = future.result()
        else:
            results = loop.run_until_complete(engine.search(query, max_results))

        duration_ms = (time.time() - start_time) * 1000

        logger.api_response("Scrapling", 200, duration_ms)
        logger.debug(f"Scrapling returned {len(results)} results")

        formatted_results = ["**Sources (Scrapling - Deep Scraped):**"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:500]  # Longer snippets — that's the point
            source_type = result.get("source", "scrapling")
            source_badge = {
                "scrapling": "🕷️ Deep",
                "scrapling_cached": "⚡ Cached",
                "scrapling_fallback": "🔄 Fallback",
                "scrapling_ddg_fallback": "🟢 DDG",
            }.get(source_type, "🕷️")
            formatted_results.append(
                f"\n{i}. [{source_badge}] **{title}**\n   URL: {url}\n   {content}..."
            )

        return "\n".join(formatted_results)

    except ImportError:
        logger.debug("Scrapling not installed, falling back to DuckDuckGo")
        return _web_search_duckduckgo(query, max_results)
    except Exception as e:
        logger.error(f"Web Search Error (Scrapling)", e)
        # Graceful fallback to DuckDuckGo
        logger.debug("Scrapling failed, falling back to DuckDuckGo")
        try:
            return _web_search_duckduckgo(query, max_results)
        except Exception:
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
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an artificial intelligence assistant and you need to "
                    "engage in a helpful, detailed, polite conversation with a user."
                ),
            },
            {
                "role": "user",
                "content": query,
            },
        ]

        response = client.chat.completions.create(
            model="sonar-pro",
            messages=messages,
        )
        
        duration_ms = (time.time() - start_time) * 1000
        logger.api_response("Perplexity", 200, duration_ms)
        
        formatted_results = [f"**Regulatory Information for {topic} in {location}:**\n"]
        formatted_results.append("**Official Sources & Requirements:**")
        formatted_results.append(response.choices[0].message.content)
            
        formatted_results.append("\n\n⚠️ *Note: Regulations change frequently.*")
        return "\n".join(formatted_results)

    except Exception as e:
        logger.error("Regulation search error (Perplexity)", e)
        return f"Error: {str(e)}"


@tool
def search_domain_experts(
    topic: str, 
    expertise_type: Optional[str] = None,
    location: Optional[str] = None,
    max_results: int = 5
) -> str:
    """
    Find domain experts, case studies, and real-world approaches for a business topic.
    
    ALWAYS use this tool for business queries to enrich responses with:
    - Real experts who have solved similar problems
    - Their published approaches and methodologies
    - Case studies and success stories
    - Expert profiles (name, title, company, location)
    
    Args:
        topic: Business topic or problem (e.g., "SaaS pricing strategy", "startup fundraising")
        expertise_type: Type of expert to find (e.g., "founder", "consultant", "investor", "author")
        location: Geographic filter (optional, e.g., "Silicon Valley", "India")
        max_results: Number of experts to find (default: 5)
    
    Returns:
        JSON with experts array containing name, title, company, location, approach, and source_url
    """
    provider = get_search_provider()
    logger = get_logger()
    logger.separator(f"DOMAIN EXPERT SEARCH: {topic}")
    
    try:
        # Build expert-focused search query
        query_parts = [f'"{topic}"']
        
        if expertise_type:
            query_parts.append(expertise_type)
        else:
            query_parts.append("(expert OR founder OR CEO OR consultant OR author)")
        
        query_parts.append("(approach OR strategy OR methodology OR case study OR interview)")
        
        if location:
            query_parts.append(location)
        
        query = " ".join(query_parts)
        
        logger.api_request("Expert Search", "search", f"query='{query}'")
        start_time = time.time()
        
        # Use Tavily or Perplexity based on provider
        if provider and provider.lower() == "perplexity":
            client = get_perplexity_client()
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an artificial intelligence assistant and you need to "
                        "engage in a helpful, detailed, polite conversation with a user."
                    ),
                },
                {
                    "role": "user",
                    "content": query,
                },
            ]

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=messages,
            )
            raw_results = [{
                "title": "Perplexity Search Result",
                "url": "",
                "content": response.choices[0].message.content
            }]
        else:
            client = get_tavily_client()
            response = client.search(
                query=query,
                max_results=max_results,
                include_answer=True,
                search_depth="advanced"
            )
            raw_results = response.get("results", [])
        
        duration_ms = (time.time() - start_time) * 1000
        logger.api_response("Expert Search", 200, duration_ms)
        
        # Parse results into structured expert data
        experts = []
        case_studies = []
        
        for result in raw_results:
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")
            
            # Heuristic extraction of expert info from search results
            expert_entry = {
                "source_title": title,
                "source_url": url,
                "snippet": content[:500] if content else "",
                "extracted_info": {
                    "possible_expert": True if any(kw in title.lower() for kw in ["ceo", "founder", "expert", "interview", "says", "shares"]) else False,
                    "possible_case_study": True if any(kw in title.lower() for kw in ["case study", "how", "strategy", "approach"]) else False
                }
            }
            
            if expert_entry["extracted_info"]["possible_case_study"]:
                case_studies.append({
                    "title": title,
                    "url": url,
                    "summary": content[:300] if content else ""
                })
            else:
                experts.append(expert_entry)
        
        result_data = {
            "topic": topic,
            "expertise_type": expertise_type,
            "location": location,
            "search_provider": provider or "tavily",
            "results_count": len(raw_results),
            "experts_found": experts[:max_results],
            "case_studies": case_studies[:3],
            "instructions": "Use the snippets to extract expert names, titles, companies, and their approaches. Present as a table in your response."
        }
        
        logger.debug(f"Found {len(experts)} potential experts, {len(case_studies)} case studies")
        
        return json.dumps(result_data, indent=2)
    
    except Exception as e:
        logger.error("Domain expert search error", e)
        return json.dumps({"error": str(e), "topic": topic})


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
        except (KeyError, AttributeError):
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


@tool
def audit_risk_assessment(
    inherent_risk: str,
    control_risk: str,
    total_revenue: Optional[float] = None,
    total_assets: Optional[float] = None,
    pre_tax_income: Optional[float] = None,
    gross_profit: Optional[float] = None,
    industry: Optional[str] = None,
    is_public_company: bool = False,
) -> str:
    """
    Compute audit risk assessment and performance materiality.

    Uses the audit risk model: Audit Risk = Inherent Risk × Control Risk × Detection Risk.
    Also calculates materiality using standard benchmarks (5% pre-tax income, 0.5% revenue,
    1% total assets, 2% gross profit).

    Use this tool when the user asks about:
    - Planning an audit engagement
    - Setting materiality levels
    - Assessing audit risk
    - Determining the audit approach (substantive vs controls-reliance)

    Args:
        inherent_risk: Level of inherent risk — "high", "medium", or "low"
        control_risk: Level of control risk — "high", "medium", or "low"
        total_revenue: Company's total revenue (optional, for materiality)
        total_assets: Company's total assets (optional, for materiality)
        pre_tax_income: Company's pre-tax income (optional, for materiality)
        gross_profit: Company's gross profit (optional, for materiality)
        industry: Industry of the company (optional context)
        is_public_company: Whether the company is publicly listed (triggers SOX considerations)

    Returns:
        JSON with risk matrix, materiality calculations, and audit approach recommendations.
    """
    logger = get_logger()
    logger.separator("AUDIT RISK ASSESSMENT")

    try:
        import asyncio
        from backend.agents.audit import get_audit_agent

        agent = get_audit_agent()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.assess_audit_risk(
                    total_revenue=total_revenue,
                    total_assets=total_assets,
                    pre_tax_income=pre_tax_income,
                    gross_profit=gross_profit,
                    inherent_risk=inherent_risk,
                    control_risk=control_risk,
                    industry=industry,
                    is_public_company=is_public_company,
                ), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(
                agent.assess_audit_risk(
                    total_revenue=total_revenue,
                    total_assets=total_assets,
                    pre_tax_income=pre_tax_income,
                    gross_profit=gross_profit,
                    inherent_risk=inherent_risk,
                    control_risk=control_risk,
                    industry=industry,
                    is_public_company=is_public_company,
                )
            )

        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Audit risk assessment error", e)
        return f"Error assessing audit risk: {str(e)}"


@tool
def generate_audit_program(
    audit_area: str,
    risk_level: str = "medium",
    industry: Optional[str] = None,
    is_sox: bool = False,
) -> str:
    """
    Generate a structured audit program with objectives, assertions, and procedures.

    Covers major audit areas: revenue recognition, accounts receivable, accounts payable,
    inventory, fixed assets, payroll, and cash. Also generates programs for custom areas.

    Use this tool when the user asks about:
    - Audit procedures for a specific area
    - Creating an audit work program
    - Audit checklists or testing plans
    - What to test in an audit

    Args:
        audit_area: The area to audit (e.g., "revenue recognition", "accounts payable", "inventory")
        risk_level: Risk level — "high", "medium", or "low" (affects procedure selection)
        industry: Industry context (optional)
        is_sox: Whether SOX 404 procedures should be included

    Returns:
        JSON with audit objectives, key assertions, detailed procedures, and sample size guidance.
    """
    logger = get_logger()
    logger.separator(f"GENERATE AUDIT PROGRAM: {audit_area}")

    try:
        import asyncio
        from backend.agents.audit import get_audit_agent

        agent = get_audit_agent()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.generate_audit_program(audit_area, industry, is_sox, risk_level), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(
                agent.generate_audit_program(audit_area, industry, is_sox, risk_level)
            )

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error("Audit program generation error", e)
        return f"Error generating audit program: {str(e)}"


@tool
def evaluate_controls(
    control_environment: str = "medium",
    risk_assessment: str = "medium",
    control_activities: str = "medium",
    information_communication: str = "medium",
    monitoring: str = "medium",
    description: Optional[str] = None,
) -> str:
    """
    Evaluate internal controls using the COSO 2013 framework.

    Assesses five components: Control Environment, Risk Assessment, Control Activities,
    Information & Communication, and Monitoring Activities. Returns effectiveness ratings
    and recommendations for improvement.

    Use this tool when the user asks about:
    - Internal control evaluation
    - COSO framework assessment
    - SOX compliance readiness
    - Control weaknesses or deficiencies

    Args:
        control_environment: Rating for tone at the top, ethics, governance — "high", "medium", or "low"
        risk_assessment: Rating for how well risks are identified and managed — "high", "medium", or "low"
        control_activities: Rating for authorization, segregation, reconciliation controls — "high", "medium", or "low"
        information_communication: Rating for IT systems, reporting, and communication — "high", "medium", or "low"
        monitoring: Rating for ongoing monitoring and periodic evaluations — "high", "medium", or "low"
        description: Optional description of the entity's control environment

    Returns:
        JSON with component ratings, overall assessment, and specific recommendations.
    """
    logger = get_logger()
    logger.separator("EVALUATE INTERNAL CONTROLS (COSO)")

    try:
        import asyncio
        from backend.agents.audit import get_audit_agent

        agent = get_audit_agent()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.evaluate_internal_controls(
                    control_environment, risk_assessment, control_activities,
                    information_communication, monitoring, description,
                ), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(
                agent.evaluate_internal_controls(
                    control_environment, risk_assessment, control_activities,
                    information_communication, monitoring, description,
                )
            )

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error("Controls evaluation error", e)
        return f"Error evaluating controls: {str(e)}"


@tool
def analyze_audit_data(
    csv_data: str,
    analysis_type: str = "full",
    column: Optional[str] = None,
    amount_column: Optional[str] = None,
    date_column: Optional[str] = None,
) -> str:
    """
    Run audit data analytics on CSV data. Supports multiple analysis types.

    Available analysis types:
    - "full": Complete dataset profiling with anomaly detection
    - "duplicates": Find duplicate records
    - "benford": Benford's Law first-digit analysis for fraud detection
    - "gaps": Detect gaps in sequential numbers (invoice, check numbers)
    - "aging": Aging analysis for AR/AP (requires date and amount columns)
    - "sample": Statistical stratified sampling
    - "journal_entries": Journal entry testing for risk indicators
    - "three_way_match": PO/Invoice/Receipt matching

    Use this tool when the user:
    - Provides financial data (CSV format) for analysis
    - Asks for anomaly or fraud detection
    - Needs audit sampling
    - Wants aging or duplicate analysis
    - Asks about Benford's Law testing

    Args:
        csv_data: The CSV data as a text string (with headers)
        analysis_type: Type of analysis — "full", "duplicates", "benford", "gaps", "aging", "sample", "journal_entries", "three_way_match"
        column: Target column name for benford/gaps analysis
        amount_column: Column containing monetary amounts
        date_column: Column containing dates (for aging/journal entry analysis)

    Returns:
        JSON with analysis results, risk assessments, and flagged items.
    """
    logger = get_logger()
    logger.separator(f"AUDIT DATA ANALYSIS: {analysis_type}")

    try:
        import asyncio
        from backend.agents.audit_data import get_audit_data_engine

        engine = get_audit_data_engine()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Route to appropriate analysis method
        analysis_map = {
            "full": lambda: engine.analyze_dataset(csv_data, amount_column),
            "duplicates": lambda: engine.detect_duplicates(csv_data),
            "benford": lambda: engine.benford_analysis(csv_data, column or amount_column or "amount"),
            "gaps": lambda: engine.gap_analysis(csv_data, column or "invoice_number"),
            "aging": lambda: engine.aging_analysis(csv_data, date_column or "date", amount_column or "amount"),
            "sample": lambda: engine.stratified_sample(csv_data, amount_column or "amount"),
            "journal_entries": lambda: engine.journal_entry_testing(csv_data, amount_column or "amount", date_column or "date"),
            "three_way_match": lambda: engine.three_way_match(csv_data),
        }

        coro_fn = analysis_map.get(analysis_type.lower(), analysis_map["full"])

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro_fn(), loop)
            result = future.result()
        else:
            result = loop.run_until_complete(coro_fn())

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Audit data analysis error ({analysis_type})", e)
        return f"Error analyzing data: {str(e)}"


@tool
def search_audit_standards(query: str, standard_type: Optional[str] = None) -> str:
    """
    Search for auditing standards, regulations, and best practices.

    Searches for ISA (International Standards on Auditing), GAAS, IIA Standards,
    PCAOB standards, SOX requirements, and other audit-related regulatory guidance.

    Use this tool when the user asks about:
    - Auditing standards (ISA, GAAS, PCAOB)
    - Internal audit standards (IIA IPPF)
    - SOX compliance requirements
    - Audit regulatory guidance
    - Best practices in auditing

    Args:
        query: The audit standards topic to search for
        standard_type: Optional filter — "ISA", "GAAS", "IIA", "PCAOB", "SOX", or None for all

    Returns:
        Search results with relevant standards information and sources.
    """
    logger = get_logger()
    logger.separator(f"AUDIT STANDARDS SEARCH: {query}")

    # Enhance query with audit context
    search_query = f"auditing standards {query}"
    if standard_type:
        search_query = f"{standard_type} {search_query}"
    search_query += " official guidance requirements"

    # Reuse existing web search infrastructure
    return web_search.invoke({"query": search_query, "max_results": 5})


@tool
def generate_audit_finding(
    condition: str,
    criteria: str,
    cause: Optional[str] = None,
    effect: Optional[str] = None,
    audit_area: Optional[str] = None,
) -> str:
    """
    Generate a structured audit finding in the standard Condition/Criteria/Cause/Effect format.

    Creates a formal audit finding with severity assessment, recommendations,
    and management response placeholders.

    Use this tool when the user:
    - Describes an audit issue that needs to be documented
    - Wants to format a finding for an audit report
    - Needs help writing audit observations
    - Asks about audit finding structure

    Args:
        condition: What was found (the actual state/problem observed)
        criteria: What should have been (the standard, policy, or requirement)
        cause: Why it happened (root cause, if known)
        effect: What is the impact (financial, operational, compliance)
        audit_area: The audit area this finding relates to (optional)

    Returns:
        JSON with structured finding including severity, recommendation, and status.
    """
    logger = get_logger()
    logger.separator("GENERATE AUDIT FINDING")

    try:
        import asyncio
        from backend.agents.audit import get_audit_agent

        agent = get_audit_agent()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                agent.generate_audit_finding(condition, criteria, cause, effect, audit_area), loop
            )
            result = future.result()
        else:
            result = loop.run_until_complete(
                agent.generate_audit_finding(condition, criteria, cause, effect, audit_area)
            )

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error("Audit finding generation error", e)
        return f"Error generating audit finding: {str(e)}"


def get_tools() -> list:
    """Get all available tools for the advisor agent."""
    logger = get_logger()
    tools = [
        web_search, 
        search_regulations, 
        search_domain_experts,
        analyze_portfolio_tool,
        analyze_sentiment_tool,
        check_risk_tool,
        search_filings_tool,
        validate_stock_price,
        query_knowledge_graph,
        run_stress_test,
        list_stress_scenarios,
        # Audit Analyst tools
        audit_risk_assessment,
        generate_audit_program,
        evaluate_controls,
        analyze_audit_data,
        search_audit_standards,
        generate_audit_finding,
    ]
    logger.system(f"Loading {len(tools)} tools: {[t.name for t in tools]}")
    return tools


