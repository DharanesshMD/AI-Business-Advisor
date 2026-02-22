"""
DuckDuckGo Search Engine - Free, no API key required.
Uses the new ddgs package (successor to duckduckgo-search).
"""

import asyncio
from typing import Optional
from ddgs import DDGS

from backend.logger import get_logger


class DuckDuckGoEngine:
    """DuckDuckGo search engine wrapper."""
    
    def __init__(self):
        self.logger = get_logger()
        self.name = "duckduckgo"
    
    async def search(
        self, 
        query: str, 
        max_results: int = 10,
        region: str = "wt-wt",  # Worldwide
        time_range: Optional[str] = None  # d, w, m, y
    ) -> list[dict]:
        """
        Search DuckDuckGo for results.
        
        Args:
            query: Search query
            max_results: Maximum results to return
            region: Region code (wt-wt for worldwide)
            time_range: Time filter (d=day, w=week, m=month, y=year)
        
        Returns:
            List of search results with title, url, content
        """
        self.logger.separator(f"DUCKDUCKGO SEARCH: {query}")
        
        try:
            import time
            start_time = time.time()
            
            # Run sync DDG in executor to not block
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, 
                self._sync_search, 
                query, 
                max_results, 
                region, 
                time_range
            )
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.api_response("DuckDuckGo", 200, duration_ms)
            self.logger.debug(f"DuckDuckGo returned {len(results)} results")
            
            return results
            
        except Exception as e:
            self.logger.error("DuckDuckGo search error", e)
            return []
    
    def _sync_search(
        self, 
        query: str, 
        max_results: int,
        region: str,
        time_range: Optional[str]
    ) -> list[dict]:
        """Synchronous search wrapper."""
        ddgs = DDGS()
        raw_results = list(ddgs.text(
            query, 
            max_results=max_results,
            region=region,
            timelimit=time_range
        ))
        
        # Normalize to standard format
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "content": r.get("body", r.get("snippet", "")),
                "source": "duckduckgo"
            })
        
        return results
    
    async def search_news(self, query: str, max_results: int = 10) -> list[dict]:
        """Search DuckDuckGo news."""
        self.logger.separator(f"DUCKDUCKGO NEWS: {query}")
        
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._sync_news_search,
                query,
                max_results
            )
            return results
        except Exception as e:
            self.logger.error("DuckDuckGo news search error", e)
            return []
    
    def _sync_news_search(self, query: str, max_results: int) -> list[dict]:
        """Synchronous news search."""
        ddgs = DDGS()
        raw_results = list(ddgs.news(query, max_results=max_results))
        
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", r.get("link", "")),
                "content": r.get("body", ""),
                "date": r.get("date", ""),
                "source": "duckduckgo_news"
            })
        
        return results


# Singleton instance
_engine = None

def get_duckduckgo_engine() -> DuckDuckGoEngine:
    """Get singleton DuckDuckGo engine instance."""
    global _engine
    if _engine is None:
        _engine = DuckDuckGoEngine()
    return _engine
