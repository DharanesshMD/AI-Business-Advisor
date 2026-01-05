import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.portfolio import get_portfolio_agent

async def test_hybrid_data():
    agent = get_portfolio_agent()
    # Mock redis to avoid connection errors
    class MockRedis:
        async def get(self, k): return None
        async def setex(self, k, t, v): pass
    agent.redis = MockRedis()
    
    print("Testing Portfolio Analysis with Finnhub Hybrid (Real Quote + Mock History)...")
    
    # AAPL price should be around 230-240 currently if it works
    holdings = [{"symbol": "AAPL", "quantity": 1}]
    result = await agent.analyze_portfolio(holdings)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    aapl = result['holdings'][0]
    print(f"Symbol: {aapl['symbol']}")
    print(f"Current Price: ${aapl['current_price']}")
    
    # If the price is NOT a round number or within expected AAPL range, it's likely real.
    # The default mock price logic was 100 + seed%100 (which for AAPL seed 322 would be 100 + 22 = 122).
    # Current AAPL is > 200.
    if aapl['current_price'] > 150:
        print("SUCCESS: Real price likely retrieved from Finnhub quote!")
    else:
        print("INFO: Price seems to be mocked or we found a very low AAPL price.")

if __name__ == "__main__":
    asyncio.run(test_hybrid_data())
