"""
Test for DuckDuckGo search engine integration.
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.search.engines.duckduckgo import get_duckduckgo_engine
import asyncio

async def test_duckduckgo():
    """Test the DuckDuckGo search engine."""
    print("Testing DuckDuckGo search engine...")
    
    engine = get_duckduckgo_engine()
    results = await engine.search("startup funding strategies 2024", max_results=5)
    
    print(f"Found {len(results)} results:")
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r.get('title', 'No title')}")
        print(f"   URL: {r.get('url', '')}")
        print(f"   Snippet: {r.get('content', '')[:100]}...")
    
    assert len(results) > 0, "No results returned"
    print("\n✅ DuckDuckGo search test passed!")

if __name__ == "__main__":
    asyncio.run(test_duckduckgo())
