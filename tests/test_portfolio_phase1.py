import asyncio
import sys
import os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.portfolio import PortfolioAgent

async def test_portfolio_agent():
    print("Initializing PortfolioAgent...")
    # This will likely fail to connect to Redis since we aren't running docker, 
    # but the agent should handle it gracefully (log error and continue/fail on cache).
    # Ideally, we'd mock redis, but let's see if the mock data generation works when redis fails.
    
    # We can mock the redis client to simple dict to test logic without actual redis
    class MockRedis:
        def __init__(self):
            self.cache = {}
        async def get(self, key):
            return self.cache.get(key)
        async def setex(self, key, time, value):
            self.cache[key] = value
            
    agent = PortfolioAgent()
    agent.redis = MockRedis() # Inject mock redis
    
    print("\n--- Test 1: Fetch Market Data (Mock) ---")
    df = await agent.get_market_data("AAPL", days=100)
    print(f"Data shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print(df.head(3))
    
    if df.empty:
        print("FAIL: No data returned")
        return
        
    print("\n--- Test 2: Calculate Metrics ---")
    returns = df['close'].pct_change().dropna()
    metrics = agent.calculate_metrics(returns)
    print("Metrics:", metrics)
    
    print("\n--- Test 3: Calculate VaR ---")
    var = agent.calculate_var(returns)
    print("VaR:", var)
    
    print("\n--- Test 4: Analyze Portfolio ---")
    holdings = [
        {"symbol": "AAPL", "quantity": 10, "purchase_price": 150},
        {"symbol": "MSFT", "quantity": 5, "purchase_price": 300},
        {"symbol": "GOOGL", "quantity": 20, "purchase_price": 120}
    ]
    
    # We interpret "NO Finnhub key" as triggering mock data generation
    result = await agent.analyze_portfolio(holdings)
    
    print("Portfolio Analysis Result Keys:", result.keys())
    print("Total Value:", result.get("summary", {}).get("total_value"))
    print("Projected p50 (30 days):", result.get("projections", {}).get("percentiles", {}).get("p50"))
    
    print("\nSUCCESS: Verification passed!")

if __name__ == "__main__":
    asyncio.run(test_portfolio_agent())
