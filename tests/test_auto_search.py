"""
Test for Auto search mode (all 3 providers in parallel).
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.utils import set_search_provider
from backend.agents.tools import web_search

def test_auto_search():
    """Test the auto search mode that queries all 3 providers."""
    print("Testing Auto search mode (all 3 providers in parallel)...")
    
    # Set provider to auto
    set_search_provider("auto")
    
    result = web_search.invoke({"query": "AI startup funding 2024", "max_results": 3})
    
    print("\n" + "="*60)
    print("RESULT:")
    print("="*60)
    print(result[:2000])  # First 2000 chars
    print("\n... (truncated)")
    
    # Validate
    assert "Combined Search Results" in result or "Tavily" in result or "DuckDuckGo" in result
    print("\n✅ Auto search test passed!")

if __name__ == "__main__":
    test_auto_search()
