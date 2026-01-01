"""
Sentiment Analysis Agent for ARIA.
Analyzes market news and social sentiment using LLMs.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timedelta

import finnhub
from openai import OpenAI

from backend.config import get_settings
from backend.agents.graph import create_openai_client
from backend.agents.utils import get_tavily_client

logger = logging.getLogger("advisor.sentiment")

class SentimentAgent:
    """
    Agent responsible for analyzing market sentiment from news and social media.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.llm_client = create_openai_client()
        
        if self.settings.FINNHUB_API_KEY:
            self.finnhub_client = finnhub.Client(api_key=self.settings.FINNHUB_API_KEY)
        else:
            self.finnhub_client = None

    async def get_company_news(self, symbol: str, days: int = 3) -> List[Dict]:
        """Fetch company news from Finnhub or fallback to Tavily."""
        news_items = []
        
        # 1. Try Finnhub first
        if self.finnhub_client:
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                
                # Finnhub sync call needs to be wrapped
                res = await asyncio.to_thread(
                    self.finnhub_client.company_news,
                    symbol, _from=start_date, to=today
                )
                
                for item in res[:10]: # Limit to 10 items
                    news_items.append({
                        "source": "Finnhub",
                        "headline": item.get('headline'),
                        "summary": item.get('summary'),
                        "url": item.get('url'),
                        "datetime": datetime.fromtimestamp(item.get('datetime')).isoformat()
                    })
                logger.info(f"Fetched {len(news_items)} news items from Finnhub for {symbol}")
            except Exception as e:
                logger.error(f"Finnhub news error: {e}")
        
        # 2. Fallback or Supplement with Tavily if few results
        if len(news_items) < 3:
            try:
                tavily = get_tavily_client()
                query = f"latest financial news for {symbol} stock market"
                
                res = await asyncio.to_thread(
                    tavily.search,
                    query=query,
                    topic="news",
                    max_results=5
                )
                
                for item in res.get('results', []):
                    news_items.append({
                        "source": "Tavily",
                        "headline": item.get('title'),
                        "summary": item.get('content'),
                        "url": item.get('url'),
                        "datetime": datetime.now().isoformat() # Approx
                    })
                logger.info(f"Fetched additional news from Tavily for {symbol}")
            except Exception as e:
                logger.error(f"Tavily news error: {e}")
                
        return news_items

    async def analyze_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Analyze sentiment for a given symbol.
        Returns a score (-1 to 1) and classification.
        """
        news = await self.get_company_news(symbol)
        
        if not news:
            return {
                "symbol": symbol,
                "score": 0.0,
                "classification": "Neutral",
                "summary": "No recent news found.",
                "news_count": 0
            }
            
        # Prepare context for LLM
        news_text = "\n\n".join([f"- {item['headline']}: {item['summary']}" for item in news])
        
        prompt = f"""
        Analyze the sentiment of the following news for the stock '{symbol}'.
        
        News Items:
        {news_text}
        
        Task:
        1. Assign a sentiment score from -1.0 (Very Bearish) to 1.0 (Very Bullish).
        2. Classify as 'Bullish', 'Bearish', or 'Neutral'.
        3. Provide a brief 1-sentence explanation.
        
        Return JSON format:
        {{
            "score": float,
            "classification": str,
            "explanation": str
        }}
        """
        
        try:
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=self.settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, # Low temp for consistent scoring
                max_tokens=150,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return {
                "symbol": symbol,
                "score": result.get("score", 0.0),
                "classification": result.get("classification", "Neutral"),
                "summary": result.get("explanation", "Analysis failed"),
                "news_count": len(news),
                "top_news": news[:3]
            }
            
        except Exception as e:
            logger.error(f"Sentiment LLM error: {e}")
            return {
                "symbol": symbol,
                "score": 0.0,
                "classification": "Error",
                "summary": "Failed to analyze sentiment.",
                "news_count": len(news)
            }

_sentiment_agent = None
def get_sentiment_agent():
    global _sentiment_agent
    if _sentiment_agent is None:
        _sentiment_agent = SentimentAgent()
    return _sentiment_agent
